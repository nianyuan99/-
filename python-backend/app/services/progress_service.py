"""
任务进度推送服务

两种推送方式：
1）进程内直接推送：worker 跑在线程池里（同步函数），而 WebSocket 广播是异步的，
   所以用 asyncio.run_coroutine_threadsafe() 把广播协程提交回主事件循环执行；
2）Redis Pub/Sub 备用：多进程 / 多实例部署时，持有连接的那个进程可以订阅频道转发。
   本地单进程场景下这一路只是转发信号（progress_bridge），不影响主链路。
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from app.constants import PROGRESS_CHANNEL_PREFIX
from app.ws.stomp_handler import manager

logger = logging.getLogger(__name__)

# 主事件循环引用：在应用 startup 时记录，供线程池里的同步代码跨线程调度协程
_main_loop: Optional[asyncio.AbstractEventLoop] = None

# 跨线程推送的等待上限（秒）：推送是「尽力而为」，不能拖住正在执行的子任务
PUSH_TIMEOUT_SECONDS = 2


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """记录主事件循环（应用启动时调用）"""
    global _main_loop
    _main_loop = loop
    logger.info("进度推送服务已绑定主事件循环")


def clear_main_loop() -> None:
    """应用关闭时清除引用，避免 shutdown 期间继续往已停止的循环提交任务"""
    global _main_loop
    _main_loop = None


def publish_progress(task_id: str, progress_data: Dict[str, Any]) -> None:
    """
    发布任务进度（同步函数，可在任意线程调用）

    推送失败只记日志，不影响测试任务本身的执行 —— 进度只是展示，
    真正的结果已经落库，前端进入详情页仍能看到完整数据。
    """
    _publish_in_process(task_id, progress_data)
    _publish_to_redis(task_id, progress_data)


def _publish_in_process(task_id: str, progress_data: Dict[str, Any]) -> None:
    """方式一：直接让主事件循环广播给当前进程内的 WebSocket 连接"""
    if _main_loop is None or not _main_loop.is_running():
        return
    try:
        future = asyncio.run_coroutine_threadsafe(
            manager.broadcast_to_task(task_id, progress_data), _main_loop
        )
        future.result(timeout=PUSH_TIMEOUT_SECONDS)
    except Exception as e:
        logger.warning("进程内进度推送失败: taskId=%s, error=%s", task_id, e)


def _publish_to_redis(task_id: str, progress_data: Dict[str, Any]) -> None:
    """方式二：发到 Redis 频道（多实例部署时的备用通道）"""
    try:
        from app.db.redis import get_redis

        redis_client = get_redis()
        if not redis_client:
            return
        redis_client.publish(
            f"{PROGRESS_CHANNEL_PREFIX}{task_id}",
            json.dumps(progress_data, ensure_ascii=False, default=str),
        )
    except Exception as e:
        # Redis 不可用不影响主流程，降级为仅进程内推送
        logger.debug("Redis 进度频道发布失败: taskId=%s, error=%s", task_id, e)


async def send_current_progress(task_id: str) -> None:
    """
    订阅成功时补推一次当前进度

    解决竞态：任务可能在前端建立连接之前就已经跑完（或已经跑了一部分），
    此时光等后续推送会让页面一直停在 0%。
    """
    try:
        from app.db.session import AsyncSessionLocal
        from app.services.batch_test_service import BatchTestService

        async with AsyncSessionLocal() as db:
            progress = await BatchTestService.build_progress_snapshot(db, task_id)
        if progress is not None:
            await manager.broadcast_to_task(task_id, progress)
    except Exception as e:
        logger.warning("补推任务当前进度失败: taskId=%s, error=%s", task_id, e)
