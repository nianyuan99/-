"""
模型同步定时任务

每天凌晨 2 点从 OpenRouter 拉取最新的模型列表，更新价格、上下文长度、是否国内模型等信息，
保证前端模型选择器里的数据不会长期停留在旧版本。
"""

import logging

from app.db.session import AsyncSessionLocal
from app.services.model_service import ModelService

logger = logging.getLogger(__name__)


class SyncModelJob:
    """OpenRouter 模型列表同步任务"""

    @staticmethod
    async def run() -> int:
        """
        执行一次模型同步

        定时任务不在 HTTP 请求上下文中，没有现成的数据库会话，
        因此这里自己创建独立的 AsyncSessionLocal。

        Returns:
            同步的模型数量（失败时返回 0）
        """
        logger.info("开始执行模型同步定时任务")
        try:
            async with AsyncSessionLocal() as db:
                count = await ModelService(db).sync_models_from_openrouter()
        except Exception:
            # 定时任务失败不应该把整个调度器带崩，记录日志后正常返回
            logger.exception("模型同步定时任务执行失败")
            return 0

        logger.info("模型同步定时任务完成，共同步 %s 个模型", count)
        return count
