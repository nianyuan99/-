"""
AI 评分服务

多评委交叉验证：选 2-3 个国产模型当评委，同时给被测模型的回答打分，
再算平均分和一致性（标准差）。评委和被测模型不能来自同一个提供商
（比如阿里的模型不能评阿里的模型），防止「护犊子」。

两条调用路径：
- `AIScoringServiceImpl.score_with_multiple_judges()`：异步版，用 `asyncio.gather()`
  并发调用多个评委（对应 Java 的 `CompletableFuture.supplyAsync()`）。
- `run_ai_scoring_sync()`：同步版，供批量测试 Worker 在**线程池**里调用。
  线程池里没有事件循环，硬调 async 函数轻则报错重则死锁，因此只能串行 `for` 循环。
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI, OpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.exceptions import BusinessException, ErrorCode
from app.models.model import Model
from app.schemas.evaluation import AIScoreResult, EvaluationResult, JudgeScore

logger = logging.getLogger(__name__)

settings = get_settings()

# 评委数量：先按推荐度和更新时间排出候选国产模型，取前 2-3 个当评委
MIN_JUDGES = 2
MAX_JUDGES = 3

# 单次评审的输出上限；评分结果是一小段 JSON，1024 足够
JUDGE_MAX_TOKENS = 1024
# 降低随机性，让评分更稳定
JUDGE_TEMPERATURE = 0.3

SCORING_PROMPT_TEMPLATE = """
你是一位专业的AI评测专家。请对以下AI模型的回答进行评分。

## 问题
{question}

## 模型回答
{model_response}

## 评分标准
1. 准确性（30分）：答案是否正确，事实是否准确
2. 相关性（20分）：是否切题，是否回答了问题
3. 完整性（20分）：是否全面，是否遗漏重要信息
4. 清晰度（15分）：表达是否清楚，逻辑是否连贯
5. 创意性（15分）：是否有独特见解或创新点

请以JSON格式输出评分结果：
{{
  "scores": {{
    "accuracy": 分数,
    "relevance": 分数,
    "completeness": 分数,
    "clarity": 分数,
    "creativity": 分数
  }},
  "total_score": 总分（100分制）,
  "rating": 评级（1-10分）,
  "comment": "简短评价（50字以内）"
}}
"""


def build_scoring_prompt(question: str, model_response: str) -> str:
    """把问题和模型回答填进评分提示词模板"""
    return (
        SCORING_PROMPT_TEMPLATE.replace("{question}", question or "").replace(
            "{model_response}", model_response or ""
        )
    )


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


def _parse_evaluation_result(text: str) -> Optional[EvaluationResult]:
    """
    解析单个评委返回的评分 JSON

    模型返回的是自由文本，数值可能是 88、88.0 甚至 "88"，这里统一取整后再构造
    EvaluationResult；任何一步不合预期就返回 None，由调用方当作「该评委评分失败」跳过。
    """
    json_text = _extract_json_from_response(text)
    if not json_text:
        return None

    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    try:
        raw_scores = data.get("scores") or {}
        if not isinstance(raw_scores, dict):
            raw_scores = {}
        scores = {
            str(key): int(round(float(value)))
            for key, value in raw_scores.items()
            if value is not None
        }

        raw_total = data.get("total_score", data.get("totalScore"))
        total_score = (
            int(round(float(raw_total))) if raw_total is not None else sum(scores.values())
        )

        raw_rating = data.get("rating")
        if raw_rating is None:
            # rating 是必填项，缺失说明这次返回不可用
            return None
        rating = int(round(float(raw_rating)))
    except (TypeError, ValueError):
        return None

    return EvaluationResult(
        scores=scores,
        total_score=total_score,
        rating=rating,
        comment=str(data.get("comment") or ""),
    )


def _is_same_provider(model_id1: Optional[str], model_id2: Optional[str]) -> bool:
    """
    判断两个模型是否来自同一提供商
    """
    if not model_id1 or not model_id2:
        return False
    p1 = model_id1.split("/")[0] if "/" in model_id1 else ""
    p2 = model_id2.split("/")[0] if "/" in model_id2 else ""
    return bool(p1 and p2 and p1 == p2)


def _calculate_average_rating(judge_scores: List[JudgeScore]) -> float:
    """计算平均评级"""
    if not judge_scores:
        return 0.0
    total = sum(js.rating for js in judge_scores if js.rating is not None)
    return total / len(judge_scores)


def _calculate_consistency(judge_scores: List[JudgeScore]) -> float:
    """计算评分一致性（标准差）"""
    if len(judge_scores) < 2:
        return 0.0
    avg = _calculate_average_rating(judge_scores)
    variance = sum(
        (js.rating - avg) ** 2 for js in judge_scores if js.rating is not None
    ) / len(judge_scores)
    return variance ** 0.5


def _build_judge_score(model_name: str, ev: EvaluationResult) -> JudgeScore:
    """把单评委的解析结果转成对外的评委评分对象"""
    return JudgeScore(
        model=model_name,
        scores=ev.scores,
        total_score=ev.total_score,
        rating=ev.rating,
        comment=ev.comment,
    )


async def _select_judge_models(
    db: AsyncSession, tested_model_name: Optional[str]
) -> List[str]:
    """
    选择评委模型：国内模型、排除被测模型及同提供商
    """
    stmt = (
        select(Model.id)
        .where(Model.is_delete == 0, Model.is_china == 1)
        .order_by(Model.recommended.desc(), Model.update_time.desc())
    )
    result = await db.execute(stmt)
    ids = [row[0] for row in result.fetchall()]
    candidates = [
        mid
        for mid in ids
        if mid != tested_model_name and not _is_same_provider(mid, tested_model_name)
    ]
    count = min(MAX_JUDGES, max(MIN_JUDGES, len(candidates)))
    return candidates[:count]


def _select_judge_models_sync(
    sync_session: Session, tested_model_name: Optional[str]
) -> List[str]:
    """选择评委模型（同步版，供线程池中的 Worker 调用），逻辑与异步版一致"""
    stmt = (
        select(Model.id)
        .where(Model.is_delete == 0, Model.is_china == 1)
        .order_by(Model.recommended.desc(), Model.update_time.desc())
    )
    ids = [row[0] for row in sync_session.execute(stmt).fetchall()]
    candidates = [
        mid
        for mid in ids
        if mid != tested_model_name and not _is_same_provider(mid, tested_model_name)
    ]
    count = min(MAX_JUDGES, max(MIN_JUDGES, len(candidates)))
    return candidates[:count]


def _invoke_judge_sync(
    openai_sync_client: OpenAI,
    prompt: str,
    model_name: str,
    extra_headers: Optional[dict] = None,
) -> Tuple[Optional[EvaluationResult], int, int]:
    """
    调用单个评委模型（同步版），返回 (解析结果, input_tokens, output_tokens)
    """
    try:
        resp = openai_sync_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=JUDGE_TEMPERATURE,
            max_tokens=JUDGE_MAX_TOKENS,
            extra_headers=extra_headers,
        )
        content = ""
        if resp.choices and len(resp.choices) > 0:
            content = (resp.choices[0].message.content or "").strip()
        input_tokens = resp.usage.prompt_tokens if resp.usage else 0
        output_tokens = resp.usage.completion_tokens if resp.usage else 0
        ev = _parse_evaluation_result(content)
        return ev, input_tokens, output_tokens
    except Exception as e:
        logger.error("评委 %s 评分失败: %s", model_name, e)
        return None, 0, 0


class AIScoringService:
    """
    AI 评分服务接口（对应 Java 版的 AIScoringService 接口）
    """

    async def score_with_multiple_judges(
        self,
        question: str,
        model_response: str,
        tested_model_name: str,
        user_id: Optional[int] = None,
        db: Optional[AsyncSession] = None,
        redis_client: Any = None,
    ) -> AIScoreResult:
        raise NotImplementedError


class AIScoringServiceImpl(AIScoringService):
    """
    AI 评分服务实现：单评委与多评委交叉验证
    """

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

    async def _invoke_judge(
        self, prompt: str, model_name: str
    ) -> tuple[Optional[EvaluationResult], int, int]:
        """
        调用单个评委模型，返回 (解析结果, input_tokens, output_tokens)
        """
        try:
            resp = await self._client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=JUDGE_TEMPERATURE,
                max_tokens=JUDGE_MAX_TOKENS,
                extra_headers=self._extra_headers,
            )
            content = ""
            if resp.choices and len(resp.choices) > 0:
                content = (resp.choices[0].message.content or "").strip()
            input_tokens = resp.usage.prompt_tokens if resp.usage else 0
            output_tokens = resp.usage.completion_tokens if resp.usage else 0
            ev = _parse_evaluation_result(content)
            return ev, input_tokens, output_tokens
        except Exception as e:
            logger.error("评委 %s 评分失败: %s", model_name, e)
            return None, 0, 0

    async def score_with_multiple_judges(
        self,
        question: str,
        model_response: str,
        tested_model_name: str,
        user_id: Optional[int] = None,
        db: Optional[AsyncSession] = None,
        redis_client: Any = None,
    ) -> AIScoreResult:
        """多评委交叉验证：并行调用评委 → 汇总平均分与一致性"""
        if not question or not str(question).strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "问题不能为空")
        if not model_response or not str(model_response).strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "模型回答不能为空")
        if not tested_model_name or not str(tested_model_name).strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "被测模型不能为空")
        if db is None:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "数据库会话不能为空")

        judge_models = await _select_judge_models(db, tested_model_name)
        prompt = build_scoring_prompt(question, model_response)

        async def one_judge(model_name: str) -> Optional[JudgeScore]:
            ev, inp_tok, out_tok = await self._invoke_judge(prompt, model_name)
            if ev is None:
                return None
            return _build_judge_score(model_name, ev)

        tasks = [one_judge(m) for m in judge_models]
        results = await asyncio.gather(*tasks)
        judge_scores = [r for r in results if r is not None]

        if not judge_scores:
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "所有评委评分都失败了")

        average_rating = _calculate_average_rating(judge_scores)
        consistency = _calculate_consistency(judge_scores)
        return AIScoreResult(
            judges=judge_scores,
            average_rating=average_rating,
            consistency=consistency,
        )


# 进程内单例（对应 Java 版容器管理的 @Service），异步评分入口直接复用
ai_scoring_service = AIScoringServiceImpl()


def run_ai_scoring_sync(
    sync_session: Session,
    openai_sync_client: OpenAI,
    question: str,
    model_response: str,
    tested_model_name: str,
    extra_headers: Optional[dict] = None,
    user_id: Optional[int] = None,
    redis_client: Any = None,
) -> Optional[AIScoreResult]:
    """
    同步执行多评委 AI 评分，供批量测试 worker 在子线程中调用

    线程池里没有事件循环，因此这里用 `for` 串行调用评委模型，而不是 `asyncio.gather()`。
    评分失败返回 None 而不是抛异常：即使评分出了问题，测试结果本身不受影响。
    """
    if not question or not str(question).strip():
        logger.warning("AI 评分的提示词为空，跳过评分: model=%s", tested_model_name)
        return None
    if not model_response or not str(model_response).strip():
        logger.warning("AI 评分的模型回答为空，跳过评分: model=%s", tested_model_name)
        return None

    prompt = build_scoring_prompt(question, model_response)

    judge_models = _select_judge_models_sync(sync_session, tested_model_name)
    if not judge_models:
        logger.warning("没有可用的评委模型，跳过评分: model=%s", tested_model_name)
        return None

    judge_scores: List[JudgeScore] = []
    for model_name in judge_models:
        ev, inp_tok, out_tok = _invoke_judge_sync(
            openai_sync_client, prompt, model_name, extra_headers
        )
        if ev is not None:
            judge_scores.append(_build_judge_score(model_name, ev))

    if not judge_scores:
        return None

    average_rating = _calculate_average_rating(judge_scores)
    consistency = _calculate_consistency(judge_scores)
    return AIScoreResult(
        judges=judge_scores,
        average_rating=average_rating,
        consistency=consistency,
    )


__all__ = [
    "AIScoringService",
    "AIScoringServiceImpl",
    "ai_scoring_service",
    "build_scoring_prompt",
    "run_ai_scoring_sync",
    "SCORING_PROMPT_TEMPLATE",
]
