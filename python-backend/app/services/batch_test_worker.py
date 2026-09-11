"""
批量测试子任务执行器（Worker）

`run_subtask_sync` 是一个**同步函数**：OpenAI SDK 的同步调用方式更稳定，
线程池里也不需要事件循环。它由 BatchTestService 通过 asyncio.to_thread() 调度执行。

每个子任务负责：检查任务状态 → 调用模型 → 计算成本 → 保存结果 →
原子更新任务进度 → 累加用户-模型使用统计 → 推送进度。
"""

import json
import logging
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.constants import (
    PROGRESS_PUSH_INTERVAL,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
)
from app.core.config import get_settings
from app.core.openrouter_config import OPENROUTER_EXTRA_HEADERS
from app.db.redis import get_redis
from app.db.session import SessionLocal
from app.models.model import Model
from app.models.test_result import TestResult
from app.models.test_task import TestTask
from app.services.progress_service import publish_progress
from app.utils.cost_calculator import CostCalculator

logger = logging.getLogger(__name__)

settings = get_settings()

# 模型价格缓存：key = model:price:{modelId}，value = "inputPrice,outputPrice"
PRICE_CACHE_PREFIX = "model:price:"
PRICE_CACHE_TTL_SECONDS = 3600


def get_sync_session() -> Session:
    """获取同步数据库会话（线程池中执行，不能复用请求级的异步会话）"""
    return SessionLocal()


def run_subtask_sync(sub_task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行单个子任务：让某个模型回答某条提示词

    Args:
        sub_task_data: 子任务上下文（taskId / sceneId / promptId / promptTitle /
            promptContent / modelName / userId / temperature / maxTokens）

    Returns:
        执行结果摘要，失败时带 error 字段；任务已取消时返回 {"skipped": True}
    """
    task_id = sub_task_data.get("taskId")
    model_name = sub_task_data.get("modelName")
    session = get_sync_session()
    result_id = str(uuid.uuid4())

    try:
        # 1. 检查任务状态：用户已取消或任务已失败时直接跳过，不再浪费 API 额度
        task = session.execute(
            select(TestTask).where(TestTask.id == task_id, TestTask.is_delete == 0)
        ).scalar_one_or_none()
        if not task:
            logger.warning("子任务对应的任务不存在，已跳过: taskId=%s", task_id)
            return {"taskId": task_id, "modelName": model_name, "skipped": True}
        if task.status in (TASK_STATUS_CANCELLED, TASK_STATUS_FAILED):
            logger.info("任务已 %s，跳过后继子任务: taskId=%s", task.status, task_id)
            return {"taskId": task_id, "modelName": model_name, "skipped": True}

        # 2. 调用模型
        output_text, reasoning, input_tokens, output_tokens, response_time_ms = _call_model(
            model_name=model_name,
            prompt_content=sub_task_data.get("promptContent") or "",
            temperature=sub_task_data.get("temperature"),
            max_tokens=sub_task_data.get("maxTokens"),
        )

        # 3. 计算成本（价格先查 Redis 缓存，未命中再查数据库）
        input_price, output_price = _get_model_price(session, model_name)
        cost = CostCalculator.calculate_cost(
            model_name, input_tokens, output_tokens, input_price, output_price
        )

        # 4. 保存测试结果
        session.add(
            TestResult(
                id=result_id,
                task_id=task_id,
                user_id=sub_task_data["userId"],
                scene_id=sub_task_data.get("sceneId"),
                prompt_id=sub_task_data.get("promptId"),
                model_name=model_name,
                input_prompt=sub_task_data.get("promptContent") or "",
                output_text=output_text,
                reasoning=reasoning,
                response_time_ms=response_time_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=Decimal(str(cost)),
                is_delete=0,
            )
        )

        # 5. 原子更新任务进度：用 completedSubtasks = completedSubtasks + 1 自增，
        #    避免多个线程同时写导致计数丢失；状态流转用 CASE WHEN 在一条 SQL 里完成
        completed_subtasks, total_subtasks, status = _advance_task_progress(session, task_id)

        # 6. 累加用户-模型使用统计
        update_user_model_usage_sync(
            session, sub_task_data["userId"], model_name, (input_tokens or 0) + (output_tokens or 0), cost
        )

        session.commit()

        # 7. 推送进度：不是每个子任务都推，按间隔推送 + 任务结束时必推
        _push_subtask_progress(
            task_id=task_id,
            total_subtasks=total_subtasks,
            completed_subtasks=completed_subtasks,
            status=status,
            model_name=model_name,
            prompt_title=sub_task_data.get("promptTitle"),
            success=True,
            error_message=None,
            force=status == TASK_STATUS_COMPLETED,
        )

        return {
            "taskId": task_id,
            "modelName": model_name,
            "promptId": sub_task_data.get("promptId"),
            "resultId": result_id,
            "completedSubtasks": completed_subtasks,
            "totalSubtasks": total_subtasks,
            "status": status,
            "success": True,
        }

    except Exception as e:
        session.rollback()
        logger.exception("子任务执行失败: taskId=%s, model=%s, error=%s", task_id, model_name, str(e))
        return _handle_subtask_failure(session, sub_task_data, e)
    finally:
        session.close()


def update_user_model_usage_sync(
    session: Session, user_id: int, model_name: str, tokens: int, cost: Decimal
) -> None:
    """
    累加用户-模型使用统计（同步，调用方负责 commit）

    用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE 一条语句完成「有则累加、无则插入」，
    比「先查后写」少一次查询，也不会在多个子任务并发时撞唯一键 uk_user_model。

    注意不要用 VALUES(totalTokens) 之外的写法引用新值 —— MySQL 8.0.20 起
    VALUES() 在 ON DUPLICATE KEY UPDATE 中已不推荐但兼容性最好（8.4 起才移除），
    这里显式传参避免依赖该行为。
    """
    session.execute(
        text(
            """
            INSERT INTO user_model_usage
                (id, userId, modelName, totalTokens, totalCost, createTime, updateTime, isDelete)
            VALUES
                (:id, :user_id, :model_name, :tokens, :cost, NOW(), NOW(), 0)
            ON DUPLICATE KEY UPDATE
                totalTokens = totalTokens + :tokens,
                totalCost = totalCost + :cost,
                updateTime = NOW()
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "model_name": model_name,
            "tokens": int(tokens or 0),
            "cost": Decimal(str(cost or 0)),
        },
    )


def _call_model(
    model_name: str,
    prompt_content: str,
    temperature: Optional[float],
    max_tokens: Optional[int],
) -> Tuple[str, Optional[str], int, int, int]:
    """
    调用 OpenRouter 对话接口

    每个子任务独立创建 client：worker 跑在线程池里，共享一个 client 会引入
    线程安全问题，而客户端创建本身几乎无开销（真正耗时的是网络请求）。

    Returns:
        (输出内容, 思考过程, 输入Token, 输出Token, 响应时间毫秒)
    """
    timeout_seconds = settings_batch_timeout()
    client = OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        default_headers=OPENROUTER_EXTRA_HEADERS,
        timeout=timeout_seconds,
        max_retries=0,
    )

    start_time = time.time()
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt_content}],
        temperature=float(temperature) if temperature is not None else 0.7,
        max_tokens=int(max_tokens) if max_tokens else 2000,
    )
    response_time_ms = int((time.time() - start_time) * 1000)

    message = response.choices[0].message if response.choices else None
    output_text = (getattr(message, "content", None) or "") if message else ""

    # reasoning 是 OpenRouter 对推理模型（DeepSeek R1、o1 等）返回的思考过程，
    # OpenAI SDK 会把它放在 model_extra 里；普通模型该字段为空
    reasoning = None
    if message is not None:
        reasoning = getattr(message, "reasoning", None) or (message.model_extra or {}).get("reasoning")

    usage = response.usage
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0

    if not output_text and not reasoning:
        raise RuntimeError("模型返回了空内容")

    return output_text, reasoning, input_tokens, output_tokens, response_time_ms


def settings_batch_timeout() -> int:
    """单次子任务超时时间（秒）"""
    from app.constants import BATCH_TEST_TIMEOUT_SECONDS

    return BATCH_TEST_TIMEOUT_SECONDS


def _get_model_price(session: Session, model_name: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    获取模型价格（每百万 tokens，美元）

    先查 Redis 缓存，未命中再查数据库并回写缓存。
    价格是低频变更数据，缓存 1 小时可以显著减少批量测试时的数据库查询。
    """
    cache_key = f"{PRICE_CACHE_PREFIX}{model_name}"
    try:
        redis_client = get_redis()
        cached = redis_client.get(cache_key)
        if cached:
            input_price, output_price = _parse_cached_price(cached)
            return input_price, output_price
    except Exception as e:
        # Redis 不可用时静默降级为直接查库
        logger.debug("读取模型价格缓存失败: model=%s, error=%s", model_name, e)

    model = session.execute(
        select(Model).where(Model.id == model_name, Model.is_delete == 0)
    ).scalar_one_or_none()

    if not model:
        logger.warning("模型不存在于模型表，成本按 0 计: model=%s", model_name)
        return None, None

    input_price = Decimal(str(model.input_price)) if model.input_price is not None else None
    output_price = Decimal(str(model.output_price)) if model.output_price is not None else None

    try:
        redis_client = get_redis()
        redis_client.setex(
            cache_key,
            PRICE_CACHE_TTL_SECONDS,
            json.dumps(
                {
                    "input": str(input_price) if input_price is not None else None,
                    "output": str(output_price) if output_price is not None else None,
                }
            ),
        )
    except Exception as e:
        logger.debug("写入模型价格缓存失败: model=%s, error=%s", model_name, e)

    return input_price, output_price


def _parse_cached_price(cached: Any) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """解析缓存中的价格，格式异常时返回 (None, None) 让调用方回退查库"""
    try:
        data = json.loads(cached)
    except (ValueError, TypeError):
        return None, None
    input_price = Decimal(data["input"]) if data.get("input") is not None else None
    output_price = Decimal(data["output"]) if data.get("output") is not None else None
    return input_price, output_price


def _advance_task_progress(session: Session, task_id: str) -> Tuple[int, int, str]:
    """
    原子推进任务进度

    一条 SQL 同时完成三件事：完成数自增、状态流转（pending → running → completed）、
    起止时间打点。这样并发执行子任务时不会出现计数错误或状态反复横跳。

    ⚠️ 赋值顺序很关键（踩过的坑）：MySQL 的 UPDATE 按 SET 中从左到右的顺序求值，
    如果先写 `completedSubtasks = completedSubtasks + 1`，那么后续 CASE 里的
    `completedSubtasks + 1` 读到的已经是自增后的值（MySQL 把 `col = col + 1` 视为
    自增并更新了行内值），于是 5/6 就会被判定成 6>=6 而提前标记 completed。
    因此这里把 status / completedAt 放在自增之前赋值，`completedSubtasks + 1`
    表达式在所有分支里都读到的是自增前的旧值。
    """
    session.execute(
        text(
            """
            UPDATE test_task
            SET status = CASE
                    WHEN completedSubtasks + 1 >= totalSubtasks THEN 'completed'
                    WHEN status = 'pending' THEN 'running'
                    ELSE status
                END,
                completedAt = CASE
                    WHEN completedSubtasks + 1 >= totalSubtasks THEN NOW()
                    ELSE completedAt
                END,
                completedSubtasks = completedSubtasks + 1,
                startedAt = CASE WHEN startedAt IS NULL THEN NOW() ELSE startedAt END
            WHERE id = :task_id AND isDelete = 0
            """
        ),
        {"task_id": task_id},
    )
    # 上面的 UPDATE 在同一事务内，这里读到的就是自增后的最新值。
    # 先 expire_all() 是为了拿到数据库真实值：如果前面加载过 task 对象，
    # 原生 SQL 不会同步 ORM 身份映射里的旧状态。
    session.expire_all()
    task = session.execute(
        select(TestTask).where(TestTask.id == task_id, TestTask.is_delete == 0)
    ).scalar_one()
    return task.completed_subtasks or 0, task.total_subtasks or 0, task.status


def _handle_subtask_failure(
    session: Session, sub_task_data: Dict[str, Any], error: Exception
) -> Dict[str, Any]:
    """
    子任务失败处理

    单个子任务失败不影响整个任务：仍然推进进度（否则进度永远到不了 100%），
    只是在推送里带上 success=false 和错误原因。
    """
    task_id = sub_task_data.get("taskId")
    model_name = sub_task_data.get("modelName")
    error_message = str(error)[:500]

    try:
        completed_subtasks, total_subtasks, status = _advance_task_progress(session, task_id)
        # 全部子任务都失败时把任务标记为 failed，方便前端一眼看出任务异常
        if status == TASK_STATUS_COMPLETED and _all_subtasks_failed(session, task_id):
            task = session.execute(
                select(TestTask).where(TestTask.id == task_id, TestTask.is_delete == 0)
            ).scalar_one()
            task.status = TASK_STATUS_FAILED
            status = TASK_STATUS_FAILED
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception("子任务失败后推进进度也失败了: taskId=%s, error=%s", task_id, str(e))
        return {"taskId": task_id, "modelName": model_name, "success": False, "error": error_message}

    _push_subtask_progress(
        task_id=task_id,
        total_subtasks=total_subtasks,
        completed_subtasks=completed_subtasks,
        status=status,
        model_name=model_name,
        prompt_title=sub_task_data.get("promptTitle"),
        success=False,
        error_message=error_message,
        force=status in (TASK_STATUS_COMPLETED, TASK_STATUS_FAILED),
    )

    return {
        "taskId": task_id,
        "modelName": model_name,
        "promptId": sub_task_data.get("promptId"),
        "completedSubtasks": completed_subtasks,
        "totalSubtasks": total_subtasks,
        "status": status,
        "success": False,
        "error": error_message,
    }


def _all_subtasks_failed(session: Session, task_id: str) -> bool:
    """判断该任务是否一条成功的结果都没有（用于标记整体失败）"""
    success_count = session.execute(
        select(TestResult.id).where(TestResult.task_id == task_id, TestResult.is_delete == 0).limit(1)
    ).first()
    return success_count is None


def _push_subtask_progress(
    task_id: str,
    total_subtasks: int,
    completed_subtasks: int,
    status: str,
    model_name: str,
    prompt_title: Optional[str],
    success: bool,
    error_message: Optional[str],
    force: bool = False,
) -> None:
    """
    按策略推送进度

    每完成 PROGRESS_PUSH_INTERVAL 个子任务推一次，任务状态变化（完成 / 失败）时无条件推送，
    避免 50 个子任务推 50 次把 WebSocket 打满。
    """
    should_push = force or completed_subtasks % PROGRESS_PUSH_INTERVAL == 0
    if not should_push:
        return

    percentage = int(completed_subtasks * 100 / total_subtasks) if total_subtasks > 0 else 0
    publish_progress(
        task_id,
        {
            "taskId": task_id,
            "status": status,
            "totalSubtasks": total_subtasks,
            "completedSubtasks": completed_subtasks,
            "percentage": percentage,
            "currentModel": model_name,
            "currentPrompt": prompt_title,
            "modelName": model_name,
            "promptTitle": prompt_title,
            "success": success,
            "errorMessage": error_message,
            "message": f"已完成 {completed_subtasks}/{total_subtasks}",
            "updateTime": datetime.now().isoformat(),
        },
    )


def list_subtask_result_ids(session: Session, task_id: str) -> List[str]:
    """查询任务下已有的结果 ID（供本地验证脚本判断子任务是否落库）"""
    result = session.execute(
        select(TestResult.id).where(TestResult.task_id == task_id, TestResult.is_delete == 0)
    )
    return [row[0] for row in result.all()]


def mark_task_failed(task_id: str, reason: str) -> None:
    """
    任务级失败兜底：调度阶段就出错（比如提示词为空）时把任务标记为 failed

    独立成一个同步函数，方便在异步调度代码里用 to_thread 调用。
    """
    session = get_sync_session()
    try:
        task = session.execute(
            select(TestTask).where(TestTask.id == task_id, TestTask.is_delete == 0)
        ).scalar_one_or_none()
        if not task or task.status in (TASK_STATUS_COMPLETED, TASK_STATUS_CANCELLED):
            return
        task.status = TASK_STATUS_FAILED
        task.completed_at = datetime.now()
        session.commit()
        logger.error("任务已标记为失败: taskId=%s, reason=%s", task_id, reason)
    except Exception as e:
        session.rollback()
        logger.exception("标记任务失败时出错: taskId=%s, error=%s", task_id, str(e))
    finally:
        session.close()
