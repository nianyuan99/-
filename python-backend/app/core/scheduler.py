"""
定时任务调度器

用 APScheduler 的 AsyncIOScheduler 挂载异步任务，随 FastAPI 的 startup / shutdown 生命周期启停。
当前只有一个任务：每天凌晨 2 点同步 OpenRouter 模型列表。
"""

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# 模型同步任务的执行时间：每天凌晨 2 点
MODEL_SYNC_HOUR = 2
MODEL_SYNC_MINUTE = 0

# 任务 ID，重复启动时用它覆盖旧任务，避免注册出多份
MODEL_SYNC_JOB_ID = "sync_model_job"

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """获取全局调度器实例（懒加载）"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    return _scheduler


def setup_scheduler() -> AsyncIOScheduler:
    """
    注册所有定时任务并启动调度器

    在 FastAPI 的 startup 事件中调用。
    """
    # 在函数内导入，避免 main → scheduler → job → service → ... 的循环导入
    from app.jobs.model_sync_job import SyncModelJob

    scheduler = get_scheduler()
    if scheduler.running:
        return scheduler

    scheduler.add_job(
        SyncModelJob.run,
        trigger=CronTrigger(hour=MODEL_SYNC_HOUR, minute=MODEL_SYNC_MINUTE),
        id=MODEL_SYNC_JOB_ID,
        name="同步 OpenRouter 模型列表",
        replace_existing=True,
        # 允许迟到 1 小时内补跑（例如服务重启错过了触发点）
        misfire_grace_time=3600,
        # 上一次还没跑完时不再并发触发
        max_instances=1,
    )

    scheduler.start()
    logger.info(
        "定时任务调度器已启动，模型同步任务将于每天 %02d:%02d 执行",
        MODEL_SYNC_HOUR,
        MODEL_SYNC_MINUTE,
    )
    return scheduler


def shutdown_scheduler() -> None:
    """关闭调度器（在 FastAPI 的 shutdown 事件中调用）"""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("定时任务调度器已关闭")
    _scheduler = None
