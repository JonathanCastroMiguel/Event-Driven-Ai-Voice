from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import redis.asyncio as aioredis
from testcontainers.redis import RedisContainer

from src.infrastructure.redis_client import TTLMap, TTLSet
from src.infrastructure.session_registry import RedisSessionRegistry


@pytest.fixture(scope="session")
def redis_url() -> str:
    with RedisContainer("redis:7-alpine") as r:
        host = r.get_container_host_ip()
        port = r.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"  # type: ignore[misc]


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()


# ---------------------------------------------------------------------------
# TTLSet
# ---------------------------------------------------------------------------


class TestTTLSet:
    async def test_add_returns_true_for_new(self, redis_client: aioredis.Redis) -> None:
        s = TTLSet(redis_client, "test_set", ttl=60)
        assert await s.add("event_1") is True

    async def test_add_returns_false_for_duplicate(self, redis_client: aioredis.Redis) -> None:
        s = TTLSet(redis_client, "test_set_dup", ttl=60)
        await s.add("event_1")
        assert await s.add("event_1") is False

    async def test_contains(self, redis_client: aioredis.Redis) -> None:
        s = TTLSet(redis_client, "test_set_contains", ttl=60)
        assert await s.contains("missing") is False
        await s.add("present")
        assert await s.contains("present") is True

    async def test_ttl_expiry(self, redis_client: aioredis.Redis) -> None:
        s = TTLSet(redis_client, "test_set_ttl", ttl=1)
        await s.add("short_lived")
        import asyncio
        await asyncio.sleep(1.5)
        assert await s.contains("short_lived") is False


# ---------------------------------------------------------------------------
# TTLMap
# ---------------------------------------------------------------------------


class TestTTLMap:
    async def test_set_and_get(self, redis_client: aioredis.Redis) -> None:
        m = TTLMap(redis_client, "test_map", ttl=60)
        await m.set("key1", '{"result": "ok"}')
        assert await m.get("key1") == '{"result": "ok"}'

    async def test_get_missing_returns_none(self, redis_client: aioredis.Redis) -> None:
        m = TTLMap(redis_client, "test_map_miss", ttl=60)
        assert await m.get("nonexistent") is None

    async def test_delete(self, redis_client: aioredis.Redis) -> None:
        m = TTLMap(redis_client, "test_map_del", ttl=60)
        await m.set("key1", "value1")
        await m.delete("key1")
        assert await m.get("key1") is None

    async def test_ttl_expiry(self, redis_client: aioredis.Redis) -> None:
        m = TTLMap(redis_client, "test_map_ttl", ttl=1)
        await m.set("short", "lived")
        import asyncio
        await asyncio.sleep(1.5)
        assert await m.get("short") is None


# ---------------------------------------------------------------------------
# Session Registry
# ---------------------------------------------------------------------------


class TestRedisSessionRegistry:
    async def test_register_and_get(self, redis_client: aioredis.Redis) -> None:
        reg = RedisSessionRegistry(redis_client, ttl=60)
        call_id = uuid4()
        await reg.register(call_id, {"status": "active", "locale": "es"})

        result = await reg.get(call_id)
        assert result is not None
        assert result["status"] == "active"
        assert result["locale"] == "es"

    async def test_get_nonexistent_returns_none(self, redis_client: aioredis.Redis) -> None:
        reg = RedisSessionRegistry(redis_client, ttl=60)
        assert await reg.get(uuid4()) is None

    async def test_update_field(self, redis_client: aioredis.Redis) -> None:
        reg = RedisSessionRegistry(redis_client, ttl=60)
        call_id = uuid4()
        await reg.register(call_id, {"status": "active"})
        await reg.update_field(call_id, "status", "ended")

        result = await reg.get(call_id)
        assert result is not None
        assert result["status"] == "ended"

    async def test_remove(self, redis_client: aioredis.Redis) -> None:
        reg = RedisSessionRegistry(redis_client, ttl=60)
        call_id = uuid4()
        await reg.register(call_id, {"status": "active"})
        await reg.remove(call_id)
        assert await reg.exists(call_id) is False

    async def test_exists(self, redis_client: aioredis.Redis) -> None:
        reg = RedisSessionRegistry(redis_client, ttl=60)
        call_id = uuid4()
        assert await reg.exists(call_id) is False
        await reg.register(call_id, {"status": "active"})
        assert await reg.exists(call_id) is True
