from __future__ import annotations

import redis.asyncio as aioredis

from src.config import Settings

DEFAULT_TTL_SECONDS = 300


async def create_redis_pool(settings: Settings) -> aioredis.Redis:
    return aioredis.from_url(
        settings.redis_url,
        max_connections=settings.redis_pool_max,
        decode_responses=True,
    )


class TTLSet:
    """Set with per-key TTL for idempotency checks (e.g. seen_event_ids)."""

    def __init__(self, redis: aioredis.Redis, prefix: str, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self._redis = redis
        self._prefix = prefix
        self._ttl = ttl

    def _key(self, member: str) -> str:
        return f"{self._prefix}:{member}"

    async def add(self, member: str) -> bool:
        """Add member. Returns True if newly added, False if already existed."""
        result = await self._redis.set(self._key(member), "1", nx=True, ex=self._ttl)
        return result is not None

    async def contains(self, member: str) -> bool:
        return await self._redis.exists(self._key(member)) == 1


class TTLMap:
    """Key-value map with per-key TTL for caching (e.g. tool_results)."""

    def __init__(self, redis: aioredis.Redis, prefix: str, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self._redis = redis
        self._prefix = prefix
        self._ttl = ttl

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def get(self, key: str) -> str | None:
        return await self._redis.get(self._key(key))

    async def set(self, key: str, value: str) -> None:
        await self._redis.set(self._key(key), value, ex=self._ttl)

    async def delete(self, key: str) -> None:
        await self._redis.delete(self._key(key))
