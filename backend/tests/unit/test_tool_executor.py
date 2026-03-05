from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.voice_runtime.tool_executor import ToolExecutor, compute_tool_request_id


# ---------------------------------------------------------------------------
# Deterministic tool_request_id (9.3)
# ---------------------------------------------------------------------------


class TestToolRequestId:
    def test_same_inputs_same_id(self) -> None:
        gen_id = uuid4()
        id1 = compute_tool_request_id(gen_id, "lookup", {"account": "A-1"})
        id2 = compute_tool_request_id(gen_id, "lookup", {"account": "A-1"})
        assert id1 == id2

    def test_different_args_different_id(self) -> None:
        gen_id = uuid4()
        id1 = compute_tool_request_id(gen_id, "lookup", {"account": "A-1"})
        id2 = compute_tool_request_id(gen_id, "lookup", {"account": "A-2"})
        assert id1 != id2

    def test_different_tool_name_different_id(self) -> None:
        gen_id = uuid4()
        id1 = compute_tool_request_id(gen_id, "lookup", {"account": "A-1"})
        id2 = compute_tool_request_id(gen_id, "search", {"account": "A-1"})
        assert id1 != id2

    def test_different_generation_different_id(self) -> None:
        id1 = compute_tool_request_id(uuid4(), "lookup", {"account": "A-1"})
        id2 = compute_tool_request_id(uuid4(), "lookup", {"account": "A-1"})
        assert id1 != id2


# ---------------------------------------------------------------------------
# Tool Execution (9.3)
# ---------------------------------------------------------------------------


class TestToolExecutor:
    async def test_successful_execution(self) -> None:
        executor = ToolExecutor()

        async def fake_tool(account_id: str) -> dict[str, object]:
            return {"balance": 100.0}

        executor.register_tool("lookup", fake_tool)
        result = await executor.execute(
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            tool_request_id=uuid4(),
            tool_name="lookup",
            args={"account_id": "A-1"},
            timeout_ms=5000,
        )
        assert result.ok is True
        assert result.payload == {"balance": 100.0}

    async def test_unknown_tool_rejected(self) -> None:
        executor = ToolExecutor()
        result = await executor.execute(
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            tool_request_id=uuid4(),
            tool_name="nonexistent",
            args={},
            timeout_ms=5000,
        )
        assert result.ok is False
        assert result.payload == {"error": "unknown_tool"}

    async def test_timeout(self) -> None:
        executor = ToolExecutor()

        async def slow_tool() -> dict[str, object]:
            await asyncio.sleep(10)
            return {"done": True}

        executor.register_tool("slow", slow_tool)
        result = await executor.execute(
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            tool_request_id=uuid4(),
            tool_name="slow",
            args={},
            timeout_ms=100,
        )
        assert result.ok is False
        assert result.payload == {"error": "timeout"}

    async def test_cancellation(self) -> None:
        executor = ToolExecutor()
        started = asyncio.Event()

        async def blocking_tool() -> dict[str, object]:
            started.set()
            await asyncio.sleep(10)
            return {"done": True}

        executor.register_tool("blocking", blocking_tool)

        async def run_and_cancel():
            task = asyncio.create_task(
                executor.execute(
                    call_id=uuid4(),
                    agent_generation_id=uuid4(),
                    tool_request_id=uuid4(),
                    tool_name="blocking",
                    args={},
                    timeout_ms=10000,
                )
            )
            await started.wait()
            # Find the running task and cancel it
            for tid in list(executor._running_tasks.keys()):
                executor.cancel(tid)
            return await task

        result = await run_and_cancel()
        assert result.ok is False
        assert result.payload == {"error": "cancelled"}

    async def test_tool_error(self) -> None:
        executor = ToolExecutor()

        async def failing_tool() -> dict[str, object]:
            msg = "database connection failed"
            raise RuntimeError(msg)

        executor.register_tool("failing", failing_tool)
        result = await executor.execute(
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            tool_request_id=uuid4(),
            tool_name="failing",
            args={},
            timeout_ms=5000,
        )
        assert result.ok is False
        assert "database connection failed" in str(result.payload)

    async def test_cache_hit(self) -> None:
        cache = AsyncMock()
        cache.get.return_value = '{"balance": 200.0}'
        executor = ToolExecutor(tool_cache=cache)

        async def tool() -> dict[str, object]:
            return {"balance": 100.0}

        executor.register_tool("lookup", tool)
        result = await executor.execute(
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            tool_request_id=uuid4(),
            tool_name="lookup",
            args={},
            timeout_ms=5000,
        )
        assert result.ok is True
        assert result.payload == {"balance": 200.0}

    async def test_cache_miss_then_cached(self) -> None:
        cache = AsyncMock()
        cache.get.return_value = None  # miss

        async def tool() -> dict[str, object]:
            return {"balance": 100.0}

        executor = ToolExecutor(tool_cache=cache)
        executor.register_tool("lookup", tool)
        result = await executor.execute(
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            tool_request_id=uuid4(),
            tool_name="lookup",
            args={},
            timeout_ms=5000,
        )
        assert result.ok is True
        # Verify it was cached
        cache.set.assert_called_once()

    async def test_registered_tools(self) -> None:
        executor = ToolExecutor()

        async def t1() -> dict[str, object]:
            return {}

        async def t2() -> dict[str, object]:
            return {}

        executor.register_tool("tool_a", t1)
        executor.register_tool("tool_b", t2)
        assert executor.registered_tools == {"tool_a", "tool_b"}
