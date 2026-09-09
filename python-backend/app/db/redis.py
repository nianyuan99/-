"""
Redis连接管理
"""

import redis
import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True
)

# 异步 Redis 客户端（供 Session 中间件等异步场景使用）
redis_async_client = aioredis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True
)


def get_redis():
    """获取Redis客户端"""
    return redis_client


def get_async_redis():
    """获取异步Redis客户端"""
    return redis_async_client
