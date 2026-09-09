"""
自定义 Redis Session 中间件
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.db.redis import redis_async_client
from app.db.redis_session import RedisSessionBackend, SessionProxy

logger = logging.getLogger(__name__)

settings = get_settings()

# 全局唯一的 Session 后端实例
session_backend = RedisSessionBackend(redis_async_client)


class RedisSessionMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. 从Cookie中获取session_id
        session_id = request.cookies.get("session_id")

        # 2. 从Redis加载Session数据，不存在则生成新的session_id
        if session_id and await session_backend.exists(session_id):
            session_data = await session_backend.get(session_id)
        else:
            session_id = session_backend.generate_session_id()
            session_data = {}

        # 3. 将Session挂载到request.state上
        request.state.session = SessionProxy(session_data, session_backend, session_id)

        # 4. 处理请求
        response = await call_next(request)

        # 5. 保存修改后的Session到Redis
        await request.state.session.save()

        # 6. 设置Cookie
        response.set_cookie(
            key="session_id",
            value=session_id,
            max_age=settings.COOKIE_MAX_AGE,
            httponly=True,
            path="/",
        )
        return response
