from __future__ import annotations

from uuid import UUID

import orjson
import redis.asyncio as aioredis

SESSION_PREFIX = "session"
DEFAULT_SESSION_TTL = 3600  # 1 hour


class RedisSessionRegistry:
    """Tracks active call sessions in Redis using hashes."""

    def __init__(self, redis: aioredis.Redis, ttl: int = DEFAULT_SESSION_TTL) -> None:
        self._redis = redis
        self._ttl = ttl

    def _key(self, call_id: UUID) -> str:
        return f"{SESSION_PREFIX}:{call_id}"

    async def register(self, call_id: UUID, data: dict[str, object]) -> None:
        key = self._key(call_id)
        await self._redis.hset(key, mapping={k: _serialize(v) for k, v in data.items()})
        await self._redis.expire(key, self._ttl)

    async def get(self, call_id: UUID) -> dict[str, str] | None:
        key = self._key(call_id)
        result = await self._redis.hgetall(key)
        if not result:
            return None
        return result

    async def update_field(self, call_id: UUID, field: str, value: object) -> None:
        key = self._key(call_id)
        await self._redis.hset(key, field, _serialize(value))

    async def remove(self, call_id: UUID) -> None:
        await self._redis.delete(self._key(call_id))

    async def exists(self, call_id: UUID) -> bool:
        return await self._redis.exists(self._key(call_id)) == 1


def _serialize(value: object) -> str:
    if isinstance(value, str):
        return value
    return orjson.dumps(value).decode()
