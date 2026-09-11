"""
AI 提示词优化服务

让一个更智能的模型分析用户的提示词，从角色设定、任务描述、输出格式、
思维链、Few-shot 示例 5 个维度给出问题清单、优化后的完整提示词和改进说明，
并给出 0-100 的质量评分（功能扩展 4）。

与 Java 版的差异：Spring AI 用 `.entity()` 自动做结构化输出，这里只能手动解析，
所以 `_extract_json_from_response` + `_parse_optimization_suggestion` 做了较宽的容错。
"""

import json
import logging
import re
import uuid
from typing import Any, List, Optional, Tuple

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.exceptions import BusinessException, ErrorCode
from app.models.prompt_optimization_history import PromptOptimizationHistory
from app.schemas.prompt import PromptOptimizationHistoryVO, PromptOptimizationVO
from app.services.prompt_template_service import calculate_quality_level

logger = logging.getLogger(__name__)

DEFAULT_EVALUATION_MODEL = "qwen/qwen-plus"

OPTIMIZATION_PROMPT_TEMPLATE = """
你是一位专业的提示词工程专家。请分析以下提示词，并提供优化建议。

## 原始提示词
{original_prompt}

{ai_response_section}

## 分析维度
请从以下5个维度分析提示词：
1. **角色设定**：是否明确指定了AI的角色和身份？
2. **任务描述**：任务目标是否清晰、具体？
3. **输出格式**：是否明确指定了期望的输出格式？
4. **思维链**：是否引导AI进行逐步思考？
5. **Few-shot示例**：是否提供了示例来帮助AI理解需求？

## 输出要求
请以JSON格式输出分析结果：
{{
  "issues": ["问题1", "问题2", ...],
  "optimized_prompt": "优化后的完整提示词",
  "improvements": ["改进点1", "改进点2", ...],
  "quality_score": 原始提示词的质量评分(0-100的整数)
}}

要求：
- issues: 列出当前提示词存在的问题（至少3个维度的问题）
- optimized_prompt: 提供优化后的完整提示词，保持原意但更加清晰、具体
- improvements: 说明每个优化带来的具体提升（至少3个改进点）
- quality_score: 综合 5 个维度的表现给出 0-100 的整数评分，60 分以下表示问题较多
"""


def _extract_json_from_response(text: str) -> Optional[str]:
    """
    从模型返回中提取 JSON 字符串（可能被 ```json ... ``` 包裹）
    """
    if not text or not text.strip():
        return None
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _parse_quality_score(data: dict) -> Optional[int]:
    """
    从解析出的 JSON 里取质量评分，裁剪到 0-100

    模型可能返回 88、88.0、"88" 甚至超出范围的 105，统一取整后夹紧。
    """
    raw = data.get("quality_score", data.get("qualityScore"))
    if raw is None:
        return None
    try:
        score = int(round(float(raw)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def _parse_optimization_suggestion(
    raw: str,
) -> Tuple[List[str], str, List[str], Optional[int]]:
    """
    解析优化建议 JSON，返回 (issues, optimized_prompt, improvements, quality_score)
    """
    json_str = _extract_json_from_response(raw)
    if not json_str:
        return [], "", [], None

    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return [], "", [], None

        issues = data.get("issues")
        if not isinstance(issues, list):
            issues = []
        optimized_prompt = data.get("optimized_prompt") or ""
        improvements = data.get("improvements")
        if not isinstance(improvements, list):
            improvements = []
        return issues, optimized_prompt, improvements, _parse_quality_score(data)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("解析提示词优化 JSON 失败: %s", e)
        return [], "", [], None


class PromptOptimizationService:

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        self._extra_headers = {
            "HTTP-Referer": "https://codefather.cn",
            "X-Title": "AI Evaluation Platform",
        }

    async def optimize_prompt(
        self,
        original_prompt: str,
        ai_response: Optional[str] = None,
        evaluation_model: Optional[str] = None,
        user_id: Optional[int] = None,
        db: Optional[AsyncSession] = None,
        redis_client: Any = None,
    ) -> PromptOptimizationVO:
        if not original_prompt or not original_prompt.strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "原始提示词不能为空")

        model = (evaluation_model or "").strip() or DEFAULT_EVALUATION_MODEL

        ai_response_section = ""
        if ai_response and ai_response.strip():
            ai_response_section = "\n## AI回答\n" + ai_response.strip() + "\n"

        analysis_prompt = OPTIMIZATION_PROMPT_TEMPLATE.replace(
            "{original_prompt}", original_prompt.strip()
        ).replace("{ai_response_section}", ai_response_section)

        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=0.3,
                max_tokens=2048,
                extra_headers=self._extra_headers,
            )
            content = ""
            if resp.choices and len(resp.choices) > 0:
                content = (resp.choices[0].message.content or "").strip()

            issues, optimized_prompt, improvements, quality_score = (
                _parse_optimization_suggestion(content)
            )

            result = PromptOptimizationVO(
                issues=issues,
                optimizedPrompt=optimized_prompt,
                improvements=improvements,
                qualityScore=quality_score,
                qualityLevel=calculate_quality_level(quality_score),
            )

            # 功能扩展 3：优化成功后落一条历史记录
            await self._save_history(
                db=db,
                user_id=user_id,
                original_prompt=original_prompt.strip(),
                result=result,
                evaluation_model=model,
            )
            return result
        except BusinessException:
            raise
        except Exception as e:
            logger.error(
                "提示词优化分析失败: prompt=%s, error=%s",
                original_prompt[:100],
                e,
                exc_info=True,
            )
            raise BusinessException(
                ErrorCode.SYSTEM_ERROR,
                "提示词优化分析失败: " + str(e),
            )

    @staticmethod
    async def _save_history(
        db: Optional[AsyncSession],
        user_id: Optional[int],
        original_prompt: str,
        result: PromptOptimizationVO,
        evaluation_model: str,
    ) -> None:
        """
        保存优化历史（功能扩展 3）

        落库失败不影响本次优化结果的返回，只记日志 —— 历史是附属能力，
        不应该因为它把主流程搞挂。
        """
        if db is None or user_id is None:
            return
        try:
            db.add(
                PromptOptimizationHistory(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    original_prompt=original_prompt,
                    optimized_prompt=result.optimized_prompt or None,
                    issues=json.dumps(result.issues, ensure_ascii=False)
                    if result.issues
                    else None,
                    improvements=json.dumps(result.improvements, ensure_ascii=False)
                    if result.improvements
                    else None,
                    quality_score=result.quality_score,
                    evaluation_model=evaluation_model,
                    is_delete=0,
                )
            )
            await db.commit()
        except Exception as e:
            logger.warning("保存优化历史失败（不影响优化结果）: %s", e)
            try:
                await db.rollback()
            except Exception:
                pass


def _history_to_vo(record: PromptOptimizationHistory) -> PromptOptimizationHistoryVO:
    """优化历史实体转 VO"""

    def _load_list(raw: Optional[str]) -> List[str]:
        if not raw or not str(raw).strip():
            return []
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    return PromptOptimizationHistoryVO(
        id=record.id,
        originalPrompt=record.original_prompt,
        optimizedPrompt=record.optimized_prompt,
        issues=_load_list(record.issues),
        improvements=_load_list(record.improvements),
        qualityScore=record.quality_score,
        qualityLevel=calculate_quality_level(record.quality_score),
        evaluationModel=record.evaluation_model,
        createTime=record.create_time.isoformat() if record.create_time else None,
    )


async def list_optimization_history(
    db: AsyncSession, user_id: int, limit: int = 20
) -> List[PromptOptimizationHistoryVO]:
    """
    查询当前用户的优化历史（功能扩展 3），按时间倒序
    """
    from sqlalchemy import select

    result = await db.execute(
        select(PromptOptimizationHistory)
        .where(
            PromptOptimizationHistory.user_id == user_id,
            PromptOptimizationHistory.is_delete == 0,
        )
        .order_by(PromptOptimizationHistory.create_time.desc())
        .limit(limit)
    )
    return [_history_to_vo(r) for r in result.scalars().all()]


async def delete_optimization_history(
    db: AsyncSession, history_id: str, user_id: int
) -> bool:
    """删除一条优化历史（逻辑删除，仅限本人）"""
    from sqlalchemy import select

    if not history_id or not history_id.strip():
        raise BusinessException(ErrorCode.PARAMS_ERROR, "记录ID不能为空")

    result = await db.execute(
        select(PromptOptimizationHistory).where(
            PromptOptimizationHistory.id == history_id.strip(),
            PromptOptimizationHistory.is_delete == 0,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "优化记录不存在")
    if record.user_id != user_id:
        raise BusinessException(ErrorCode.NO_AUTH_ERROR, "无权限操作")

    record.is_delete = 1
    await db.commit()
    return True
