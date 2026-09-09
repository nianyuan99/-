"""
Redis Session 后端存储
"""

import json
import uuid
from typing import Dict, Optional

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()


class SessionProxy(dict):
    """
    Session 代理类

    继承 dict，数据被修改时自动标记为"已修改"，
    请求结束后由中间件调用 save() 保存到 Redis，使用起来和普通字典一样。
    """

    def __init__(self, data: Dict, backend: "RedisSessionBackend", session_id: str):
        super().__init__(data)
        self._backend = backend
        self._session_id = session_id
        self._modified = False

    def __setitem__(self, key, value):
        self._modified = True
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self._modified = True
        super().__delitem__(key)

    def pop(self, key, *args):
        self._modified = True
        return super().pop(key, *args)

    async def save(self) -> None:
        """请求结束时保存修改后的 Session 到 Redis"""
        if not self._modified:
            return
        if self:
            await self._backend.set(self._session_id, dict(self))
        else:
            # Session 数据为空时删除对应的 key
            await self._backend.delete(self._session_id)


class RedisSessionBackend:
    """
    Redis Session后端存储

    Session 数据以 JSON 格式存储，key 格式为 session:{uuid}
    """

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.prefix = "session:"
        self.expire = settings.SESSION_EXPIRE_SECONDS

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    async def get(self, session_id: str) -> Optional[Dict]:
        data = await self.redis.get(self._key(session_id))
        return json.loads(data) if data else None

    async def set(self, session_id: str, data: Dict) -> None:
        await self.redis.setex(
            self._key(session_id),
            self.expire,
            json.dumps(data, ensure_ascii=False),
        )

    async def delete(self, session_id: str) -> None:
        await self.redis.delete(self._key(session_id))

    async def exists(self, session_id: str) -> bool:
        return await self.redis.exists(self._key(session_id)) > 0

    def generate_session_id(self) -> str:
        return str(uuid.uuid4())
