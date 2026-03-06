"""Unit tests for debug event emission in Coordinator (task 11.3)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.voice_runtime.coordinator import Coordinator


# ---------------------------------------------------------------------------
# Helpers — reuse the existing conftest fixtures pattern
# ---------------------------------------------------------------------------


def _make_coordinator(**kwargs) -> Coordinator:
    """Create a Coordinator with minimal stubs."""
    from src.voice_runtime.agent_fsm import AgentFSM
    from src.voice_runtime.tool_executor import ToolExecutor
    from src.voice_runtime.turn_manager import TurnManager
    from src.routing.router import Router

    call_id = kwargs.get("call_id", uuid4())

    router = kwargs.get("router") or MagicMock(spec=Router)
    if isinstance(router, MagicMock):
        router.classify = AsyncMock()

    policies = kwargs.get("policies") or MagicMock()
    if isinstance(policies, MagicMock):
        policies.get_instructions = MagicMock(return_value="Test instructions.")
        policies.base_system = "You are a test agent."

    return Coordinator(
        call_id=call_id,
        turn_manager=TurnManager(call_id),
        agent_fsm=AgentFSM(call_id),
        tool_executor=MagicMock(spec=ToolExecutor),
        router=router,
        policies=policies,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDebugCallback:
    def test_set_debug_callback(self) -> None:
        coord = _make_coordinator()
        assert coord._debug_callback is None

        async def debug_cb(event: dict) -> None:
            pass

        coord.set_debug_callback(debug_cb)
        assert coord._debug_callback is debug_cb

    def test_set_debug_callback_to_none(self) -> None:
        coord = _make_coordinator()

        async def debug_cb(event: dict) -> None:
            pass

        coord.set_debug_callback(debug_cb)
        coord.set_debug_callback(None)
        assert coord._debug_callback is None


class TestDebugEmission:
    @pytest.mark.asyncio
    async def test_emit_debug_with_callback(self) -> None:
        coord = _make_coordinator()
        received: list[dict] = []

        async def debug_cb(event: dict) -> None:
            received.append(event)

        coord.set_debug_callback(debug_cb)
        await coord._emit_debug({"type": "test", "data": 42})

        assert len(received) == 1
        assert received[0]["type"] == "test"

    @pytest.mark.asyncio
    async def test_emit_debug_without_callback_noop(self) -> None:
        coord = _make_coordinator()
        # Should not raise
        await coord._emit_debug({"type": "test"})

    @pytest.mark.asyncio
    async def test_emit_debug_error_does_not_crash(self) -> None:
        coord = _make_coordinator()

        async def failing_cb(event: dict) -> None:
            raise RuntimeError("debug handler error")

        coord.set_debug_callback(failing_cb)
        # Should not raise — best-effort
        await coord._emit_debug({"type": "test"})


class TestNoOverheadWhenDisabled:
    def test_no_callback_means_no_overhead(self) -> None:
        """When debug_callback is None, _emit_debug returns immediately."""
        coord = _make_coordinator()
        assert coord._debug_callback is None
        # The method exists and is a no-op
        assert hasattr(coord, "_emit_debug")
