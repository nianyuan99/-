"""
批量测试服务层

负责批量测试任务的创建与调度、结果查询、任务管理与评分。
执行模型：一个任务（模型数 × 提示词数）被拆成 N 个子任务，
用 asyncio.Semaphore 限制并发数，通过 asyncio.to_thread 把同步的模型调用丢进线程池，
这样既不阻塞 FastAPI 主事件循环，也不需要额外部署消息队列（对应 Java 版的 RabbitMQ + Worker）。
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    BATCH_TEST_DEFAULT_MAX_TOKENS,
    BATCH_TEST_DEFAULT_TEMPERATURE,
    MAX_BATCH_TEST_SUBTASKS,
    MAX_CONCURRENT_SUBTASKS,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUSES,
    USER_RATING_MAX,
    USER_RATING_MIN,
)
from app.exceptions import BusinessException, ErrorCode
from app.models.model import Model
from app.models.scene import Scene
from app.models.scene_prompt import ScenePrompt
from app.models.test_result import TestResult
from app.models.test_task import TestTask
from app.models.user_model_usage import UserModelUsage
from app.schemas.batch_test import (
    BatchTestTaskQueryRequest,
    ModelUsageStatVO,
    StatisticsOverviewVO,
    TestResultVO,
    TestTaskVO,
    UserModelUsageVO,
)
from app.services.batch_test_worker import mark_task_failed, run_subtask_sync
from app.services.progress_service import publish_progress
from app.services.scene_service import SceneService

logger = logging.getLogger(__name__)

# 正在执行的子任务协程引用
#
# asyncio.create_task() 创建的协程如果没有被引用，可能被垃圾回收导致任务中途消失，
# 因此这里按 taskId 持有引用，全部完成后清理。
_running_tasks: Dict[str, List[asyncio.Task]] = {}


class BatchTestService:
    """批量测试服务类"""

    # ============ 任务创建与调度 ============

    @staticmethod
    async def create_batch_test_task(db: AsyncSession, request_data: dict, user_id: int) -> str:
        """
        创建批量测试任务并启动异步执行

        五步：参数校验 → 查询场景与提示词 → 创建任务记录 → 推送初始进度 → 异步启动子任务。
        """
        # 第一步：参数校验
        scene_id = request_data.get("scene_id") or request_data.get("sceneId")
        if not scene_id or not str(scene_id).strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "场景ID不能为空")

        models = request_data.get("models")
        if not models or not isinstance(models, list) or len(models) == 0:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "模型列表不能为空")
        # 去重并保持顺序：同一个模型出现在列表里两次没有意义，只会白花 API 额度
        models = list(dict.fromkeys(str(model).strip() for model in models if str(model).strip()))
        if not models:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "模型列表不能为空")

        temperature = request_data.get("temperature")
        if temperature is None:
            temperature = BATCH_TEST_DEFAULT_TEMPERATURE
        max_tokens = request_data.get("max_tokens") or request_data.get("maxTokens")
        if max_tokens is None:
            max_tokens = BATCH_TEST_DEFAULT_MAX_TOKENS
        # 是否启用 AI 评分（高级参数，默认关闭）：启用后 Worker 会在保存每条结果时
        # 顺带跑一次多评委交叉评分，写进 test_result.aiScore
        enable_ai_scoring = bool(
            request_data.get("enable_ai_scoring") or request_data.get("enableAiScoring")
        )

        # 校验模型是否真实存在，避免任务创建成功但每个子任务都失败
        await BatchTestService._validate_models(db, models)

        # 第二步：查询场景和提示词（场景不可见 / 无提示词都会在这里抛业务异常）
        scene_id = str(scene_id).strip()
        prompts = await SceneService.get_scene_prompts_for_test(db, scene_id, user_id)

        total_subtasks = len(models) * len(prompts)
        if total_subtasks > MAX_BATCH_TEST_SUBTASKS:
            raise BusinessException(
                ErrorCode.PARAMS_ERROR,
                f"子任务总数不能超过 {MAX_BATCH_TEST_SUBTASKS}（当前 {len(models)} 个模型 × {len(prompts)} 条提示词）",
            )

        # 第三步：创建任务记录
        task_id = str(uuid.uuid4())
        name = (request_data.get("name") or "").strip() or None
        task = TestTask(
            id=task_id,
            user_id=user_id,
            name=name,
            scene_id=scene_id,
            models=json.dumps(models, ensure_ascii=False),
            status="pending",
            total_subtasks=total_subtasks,
            completed_subtasks=0,
            is_delete=0,
        )
        db.add(task)
        await db.commit()

        # 第四步：推送初始进度
        publish_progress(
            task_id,
            {
                "taskId": task_id,
                "status": "pending",
                "totalSubtasks": total_subtasks,
                "completedSubtasks": 0,
                "percentage": 0,
                "message": f"任务已创建，共 {total_subtasks} 个子任务",
            },
        )

        # 第五步：异步启动所有子任务
        BatchTestService._schedule_subtasks(
            task_id=task_id,
            scene_id=scene_id,
            models=models,
            prompts=prompts,
            user_id=user_id,
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            enable_ai_scoring=enable_ai_scoring,
        )

        logger.info(
            "批量测试任务已创建: taskId=%s, models=%s, prompts=%s, total=%s, aiScoring=%s",
            task_id,
            models,
            len(prompts),
            total_subtasks,
            enable_ai_scoring,
        )
        return task_id

    @staticmethod
    def _schedule_subtasks(
        task_id: str,
        scene_id: str,
        models: List[str],
        prompts: List[ScenePrompt],
        user_id: int,
        temperature: float,
        max_tokens: int,
        enable_ai_scoring: bool = False,
    ) -> None:
        """
        拆分并异步调度子任务

        - asyncio.Semaphore(5) 相当于令牌桶，最多 5 个子任务同时执行，超出的自动排队；
        - asyncio.to_thread() 把同步的模型调用放到线程池，不阻塞主事件循环；
        - asyncio.create_task() 不会阻塞当前请求，任务创建接口能立刻返回 taskId。
        """
        sem = asyncio.Semaphore(MAX_CONCURRENT_SUBTASKS)

        # 提前把提示词的关键信息取出来：ORM 对象绑定在请求期的 AsyncSession 上，
        # 请求结束后继续在线程里访问会触发懒加载异常
        prompt_payloads = [
            {"promptId": prompt.id, "promptTitle": prompt.title, "promptContent": prompt.content}
            for prompt in prompts
        ]

        async def run_subtask_with_semaphore(sub_task_data: Dict[str, Any]) -> None:
            async with sem:
                await asyncio.to_thread(run_subtask_sync, sub_task_data)

        scheduled: List[asyncio.Task] = []
        for model_name in models:
            for prompt_payload in prompt_payloads:
                sub_task_data = {
                    "taskId": task_id,
                    "sceneId": scene_id,
                    "promptId": prompt_payload["promptId"],
                    "promptTitle": prompt_payload["promptTitle"],
                    "promptContent": prompt_payload["promptContent"],
                    "modelName": model_name,
                    "userId": user_id,
                    "temperature": temperature,
                    "maxTokens": max_tokens,
                    "enableAiScoring": enable_ai_scoring,
                }
                scheduled.append(asyncio.create_task(run_subtask_with_semaphore(sub_task_data)))

        _running_tasks[task_id] = scheduled
        # 所有子任务结束后清理引用；任务级异常兜底标记为 failed
        asyncio.create_task(BatchTestService._finalize_when_done(task_id, scheduled))

    @staticmethod
    async def _finalize_when_done(task_id: str, scheduled: List[asyncio.Task]) -> None:
        """等待任务的所有子任务结束，清理引用并处理调度层的意外异常"""
        try:
            results = await asyncio.gather(*scheduled, return_exceptions=True)
        except Exception as e:
            logger.exception("等待子任务结束时异常: taskId=%s, error=%s", task_id, str(e))
            return
        finally:
            _running_tasks.pop(task_id, None)

        for item in results:
            if isinstance(item, BaseException):
                # run_subtask_sync 内部已捕获业务异常，走到这里说明是调度层错误
                logger.error("子任务协程异常: taskId=%s, error=%s", task_id, str(item))
                await asyncio.to_thread(mark_task_failed, task_id, str(item))

    # ============ 任务查询与管理 ============

    @staticmethod
    async def get_task(db: AsyncSession, task_id: str, user_id: int) -> TestTaskVO:
        """获取任务详情（仅任务创建者可查看）"""
        task = await BatchTestService._get_owned_task(db, task_id, user_id)
        vo = TestTaskVO.model_validate(task)
        vo.scene_name = await BatchTestService._get_scene_name(db, task.scene_id)
        return vo

    @staticmethod
    async def list_tasks_by_page(
        db: AsyncSession, query: BatchTestTaskQueryRequest, user_id: int
    ) -> Dict[str, Any]:
        """分页查询当前用户的批量测试任务"""
        conditions = [TestTask.user_id == user_id, TestTask.is_delete == 0]
        if query.scene_id:
            conditions.append(TestTask.scene_id == query.scene_id)
        if query.status:
            if query.status not in TASK_STATUSES:
                raise BusinessException(ErrorCode.PARAMS_ERROR, "任务状态取值非法")
            conditions.append(TestTask.status == query.status)

        count_result = await db.execute(select(func.count()).select_from(TestTask).where(*conditions))
        total = count_result.scalar() or 0

        result = await db.execute(
            select(TestTask)
            .where(*conditions)
            .order_by(TestTask.create_time.desc())
            .offset((query.current - 1) * query.page_size)
            .limit(query.page_size)
        )
        tasks = result.scalars().all()

        scene_names = await BatchTestService._get_scene_names(db, [task.scene_id for task in tasks])
        records: List[TestTaskVO] = []
        for task in tasks:
            vo = TestTaskVO.model_validate(task)
            vo.scene_name = scene_names.get(task.scene_id)
            records.append(vo)

        return {
            "records": [vo.model_dump(by_alias=True, mode="json") for vo in records],
            "total": total,
            "current": query.current,
            "pageSize": query.page_size,
        }

    @staticmethod
    async def delete_task(db: AsyncSession, task_id: str, user_id: int) -> bool:
        """删除任务（逻辑删除，同时逻辑删除其测试结果）"""
        task = await BatchTestService._get_owned_task(db, task_id, user_id)
        task.is_delete = 1

        results = await db.execute(
            select(TestResult).where(TestResult.task_id == task.id, TestResult.is_delete == 0)
        )
        for test_result in results.scalars().all():
            test_result.is_delete = 1

        await db.commit()
        logger.info("删除批量测试任务: taskId=%s, userId=%s", task.id, user_id)
        return True

    @staticmethod
    async def cancel_task(db: AsyncSession, task_id: str, user_id: int) -> bool:
        """
        取消任务

        Worker 在执行每个子任务前会检查任务状态，发现 cancelled 就跳过，
        因此取消是「尽快停止」，已经发出去的请求仍会跑完并落库。
        """
        task = await BatchTestService._get_owned_task(db, task_id, user_id)
        if task.status in (TASK_STATUS_COMPLETED, TASK_STATUS_CANCELLED):
            raise BusinessException(ErrorCode.OPERATION_ERROR, "任务已结束，无法取消")

        task.status = TASK_STATUS_CANCELLED
        task.completed_at = datetime.now()
        await db.commit()

        publish_progress(
            task.id,
            {
                "taskId": task.id,
                "status": TASK_STATUS_CANCELLED,
                "totalSubtasks": task.total_subtasks or 0,
                "completedSubtasks": task.completed_subtasks or 0,
                "percentage": BatchTestService.calc_percentage(
                    task.completed_subtasks or 0, task.total_subtasks or 0
                ),
                "message": "任务已取消",
            },
        )
        logger.info("取消批量测试任务: taskId=%s, userId=%s", task.id, user_id)
        return True

    # ============ 结果查询与评分 ============

    @staticmethod
    async def list_task_results(
        db: AsyncSession, task_id: str, user_id: int, model_name: Optional[str] = None
    ) -> List[TestResultVO]:
        """查询任务的测试结果（可按模型筛选），带上提示词标题与序号便于前端展示"""
        task = await BatchTestService._get_owned_task(db, task_id, user_id)

        conditions = [TestResult.task_id == task.id, TestResult.is_delete == 0]
        if model_name:
            conditions.append(TestResult.model_name == model_name)

        result = await db.execute(
            select(TestResult, ScenePrompt.title, ScenePrompt.prompt_index)
            .join(ScenePrompt, ScenePrompt.id == TestResult.prompt_id, isouter=True)
            .where(*conditions)
            .order_by(ScenePrompt.prompt_index.asc(), TestResult.model_name.asc())
        )

        items: List[TestResultVO] = []
        for test_result, prompt_title, prompt_index in result.all():
            vo = TestResultVO.model_validate(test_result)
            vo.prompt_title = prompt_title
            vo.prompt_index = prompt_index
            items.append(vo)
        return items

    @staticmethod
    async def update_result_rating(
        db: AsyncSession, result_id: str, user_rating: int, user_id: int
    ) -> bool:
        """更新测试结果的用户评分（1-5 分）"""
        if user_rating < USER_RATING_MIN or user_rating > USER_RATING_MAX:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "评分必须在 1-5 之间")

        result = await db.execute(
            select(TestResult).where(TestResult.id == result_id, TestResult.is_delete == 0)
        )
        test_result = result.scalar_one_or_none()
        if not test_result:
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "测试结果不存在")
        if test_result.user_id != user_id:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "无权操作该测试结果")

        test_result.user_rating = user_rating
        await db.commit()
        return True

    # ============ 数据统计概览 ============

    @staticmethod
    async def get_statistics_overview(db: AsyncSession, user_id: int) -> StatisticsOverviewVO:
        """当前用户的数据统计概览：任务/结果/Token/成本，以及按模型维度的明细"""
        task_stats = (
            await db.execute(
                select(
                    func.count(),
                    func.sum(func.if_(TestTask.status == TASK_STATUS_COMPLETED, 1, 0)),
                    func.sum(
                        func.if_(
                            TestTask.status.in_(("pending", "running")),
                            1,
                            0,
                        )
                    ),
                )
                .select_from(TestTask)
                .where(TestTask.user_id == user_id, TestTask.is_delete == 0)
            )
        ).one()

        result_stats = (
            await db.execute(
                select(
                    func.count(),
                    func.count(func.distinct(TestResult.model_name)),
                    func.coalesce(func.sum(TestResult.input_tokens), 0),
                    func.coalesce(func.sum(TestResult.output_tokens), 0),
                    func.coalesce(func.sum(TestResult.cost), 0),
                    func.avg(TestResult.response_time_ms),
                )
                .select_from(TestResult)
                .where(TestResult.user_id == user_id, TestResult.is_delete == 0)
            )
        ).one()

        scene_count = (
            await db.execute(
                select(func.count())
                .select_from(Scene)
                .where(
                    Scene.is_delete == 0,
                    or_(Scene.user_id == user_id, Scene.is_preset == 1),
                )
            )
        ).scalar() or 0

        model_usage = await BatchTestService._list_user_model_usage(db, user_id)
        model_stats = await BatchTestService._list_model_stats(db, user_id)

        return StatisticsOverviewVO(
            task_count=int(task_stats[0] or 0),
            completed_task_count=int(task_stats[1] or 0),
            running_task_count=int(task_stats[2] or 0),
            result_count=int(result_stats[0] or 0),
            model_count=int(result_stats[1] or 0),
            scene_count=int(scene_count),
            total_tokens=int(result_stats[2] or 0) + int(result_stats[3] or 0),
            total_cost=float(result_stats[4] or 0),
            avg_response_time_ms=int(result_stats[5]) if result_stats[5] is not None else None,
            model_usage=model_usage,
            model_stats=model_stats,
        )

    @staticmethod
    async def build_progress_snapshot(db: AsyncSession, task_id: str) -> Optional[Dict[str, Any]]:
        """
        构造任务当前进度的快照（订阅 WebSocket 时补推一次，解决「连上时任务已跑完」的竞态）
        """
        result = await db.execute(
            select(TestTask).where(TestTask.id == task_id, TestTask.is_delete == 0)
        )
        task = result.scalar_one_or_none()
        if not task:
            return None

        models = task.model_list
        total = task.total_subtasks or 0
        completed = task.completed_subtasks or 0

        return {
            "taskId": task.id,
            "status": task.status,
            "totalSubtasks": total,
            "completedSubtasks": completed,
            "percentage": BatchTestService.calc_percentage(completed, total),
            "currentModel": models[-1] if models else None,
            "message": f"已完成 {completed}/{total}",
        }

    # ============ 内部方法 ============

    @staticmethod
    def calc_percentage(completed: int, total: int) -> int:
        """计算完成百分比（0-100），总数为 0 时返回 0"""
        if not total or total <= 0:
            return 0
        return min(100, int(completed * 100 / total))

    @staticmethod
    async def _validate_models(db: AsyncSession, models: List[str]) -> None:
        """校验模型是否都在模型表中且未被逻辑删除"""
        result = await db.execute(
            select(Model.id).where(Model.id.in_(models), Model.is_delete == 0)
        )
        existed = {row[0] for row in result.all()}
        missing = [model for model in models if model not in existed]
        if missing:
            raise BusinessException(ErrorCode.PARAMS_ERROR, f"以下模型不存在或已下线: {', '.join(missing)}")

    @staticmethod
    async def _get_owned_task(db: AsyncSession, task_id: str, user_id: int) -> TestTask:
        """查询属于当前用户的任务"""
        if not task_id or not str(task_id).strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "任务ID不能为空")

        result = await db.execute(
            select(TestTask).where(
                TestTask.id == str(task_id).strip(),
                TestTask.is_delete == 0,
                TestTask.user_id == user_id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "任务不存在")
        return task

    @staticmethod
    async def _get_scene_name(db: AsyncSession, scene_id: str) -> Optional[str]:
        """查询场景名称"""
        result = await db.execute(select(Scene.name).where(Scene.id == scene_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def _get_scene_names(db: AsyncSession, scene_ids: List[str]) -> Dict[str, str]:
        """批量查询场景名称（含已逻辑删除的场景，保证历史任务也能显示名称）"""
        if not scene_ids:
            return {}
        result = await db.execute(
            select(Scene.id, Scene.name).where(Scene.id.in_(set(scene_ids)))
        )
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    async def _list_user_model_usage(db: AsyncSession, user_id: int) -> List[UserModelUsageVO]:
        """按模型汇总 Token 与花费（来自 user_model_usage 统计表）"""
        result = await db.execute(
            select(UserModelUsage)
            .where(UserModelUsage.user_id == user_id, UserModelUsage.is_delete == 0)
            .order_by(UserModelUsage.total_cost.desc())
        )
        usages = result.scalars().all()
        model_names = await BatchTestService._get_model_labels(db, [usage.model_name for usage in usages])

        items: List[UserModelUsageVO] = []
        for usage in usages:
            vo = UserModelUsageVO.model_validate(usage)
            vo.model_label = model_names.get(usage.model_name)
            items.append(vo)
        return items

    @staticmethod
    async def _list_model_stats(db: AsyncSession, user_id: int) -> List[ModelUsageStatVO]:
        """按模型统计测试结果（调用次数、Token、成本、平均响应时间）"""
        result = await db.execute(
            select(
                TestResult.model_name,
                func.count(),
                func.coalesce(func.sum(TestResult.input_tokens), 0)
                + func.coalesce(func.sum(TestResult.output_tokens), 0),
                func.coalesce(func.sum(TestResult.cost), 0),
                func.avg(TestResult.response_time_ms),
            )
            .where(TestResult.user_id == user_id, TestResult.is_delete == 0)
            .group_by(TestResult.model_name)
            .order_by(func.count().desc())
        )
        rows = result.all()
        model_names = await BatchTestService._get_model_labels(db, [row[0] for row in rows])

        items: List[ModelUsageStatVO] = []
        for model_name, call_count, total_tokens, total_cost, avg_time in rows:
            items.append(
                ModelUsageStatVO(
                    model_name=model_name,
                    model_label=model_names.get(model_name),
                    call_count=int(call_count or 0),
                    total_tokens=int(total_tokens or 0),
                    total_cost=float(total_cost or 0),
                    avg_response_time_ms=int(avg_time) if avg_time is not None else None,
                )
            )
        return items

    @staticmethod
    async def _get_model_labels(db: AsyncSession, model_ids: List[str]) -> Dict[str, str]:
        """批量查询模型显示名称"""
        if not model_ids:
            return {}
        result = await db.execute(
            select(Model.id, Model.name).where(Model.id.in_(set(model_ids)))
        )
        return {row[0]: row[1] for row in result.all()}
