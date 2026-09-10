"""
接口限流工具

基于 Redis 的固定窗口计数器实现，用于保护 AI 调用这类高成本接口。
与 Java 版 Redisson 的 RRateLimiter 思路一致：按维度（用户 / IP）计数，
超过阈值直接抛出业务异常。
"""

import logging
import time
from enum import Enum
from typing import Optional

from fastapi import Request
from redis.asyncio import Redis

from app.constants import USER_LOGIN_STATE
from app.exceptions import BusinessException, ErrorCode

logger = logging.getLogger(__name__)


class RateLimitType(Enum):
    """限流维度"""

    USER = "user"
    IP = "ip"


def _get_identifier(request: Request, limit_type: RateLimitType) -> str:
    """
    获取限流标识

    用户维度优先取登录态里的用户 ID，匿名访问时退化为 IP 维度；
    IP 维度直接取客户端地址。
    """
    if limit_type == RateLimitType.USER:
        session = getattr(request.state, "session", None) or {}
        user_info = session.get(USER_LOGIN_STATE) if session else None
        if user_info and user_info.get("id"):
            return f"user:{user_info['id']}"

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


async def check_rate_limit(
    redis_client: Redis,
    request: Request,
    limit_type: RateLimitType,
    limit: int,
    window_seconds: int,
    message: Optional[str] = None,
) -> None:
    """
    检查并累加限流计数

    Args:
        redis_client: 异步 Redis 客户端
        request: 当前请求对象
        limit_type: 限流维度（USER / IP）
        limit: 窗口内允许的最大请求次数
        window_seconds: 窗口时长（秒）
        message: 触发限流时的提示文案

    Raises:
        BusinessException: 超过限流阈值时抛出
    """
    identifier = _get_identifier(request, limit_type)
    window_index = int(time.time()) // window_seconds
    key = f"rate_limit:{limit_type.value}:{identifier}:{window_index}"

    try:
        current = await redis_client.incr(key)
        if current == 1:
            # 首次进入该窗口，设置过期时间，避免 key 无限堆积
            await redis_client.expire(key, window_seconds + 1)
    except Exception as e:
        # 限流属于保护措施，Redis 异常时不应阻断正常业务，放行并记录告警
        logger.warning("限流检查失败，已放行: %s", str(e))
        return

    if current > limit:
        logger.warning("触发限流: type=%s, identifier=%s, count=%s", limit_type.value, identifier, current)
        raise BusinessException(
            ErrorCode.OPERATION_ERROR, message or "请求过于频繁，请稍后再试"
        )
