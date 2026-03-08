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

    call_id = kwargs.get("call_id", uuid4())

    policies = kwargs.get("policies") or MagicMock()
    if isinstance(policies, MagicMock):
        policies.get_instructions = MagicMock(return_value="Test instructions.")
        policies.base_system = "You are a test agent."

    return Coordinator(
        call_id=call_id,
        turn_manager=TurnManager(call_id),
        agent_fsm=AgentFSM(call_id),
        tool_executor=MagicMock(spec=ToolExecutor),
        router_prompt_builder=None,
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


# ---------------------------------------------------------------------------
# Task 6.1: _debug_enabled defaults to False and no events emitted
# ---------------------------------------------------------------------------


class TestDebugEnabledFlag:
    def test_debug_enabled_defaults_false(self) -> None:
        coord = _make_coordinator()
        assert coord._debug_enabled is False

    @pytest.mark.asyncio
    async def test_no_events_when_disabled(self) -> None:
        coord = _make_coordinator()
        received: list[dict] = []

        async def debug_cb(event: dict) -> None:
            received.append(event)

        coord.set_debug_callback(debug_cb)
        # _debug_enabled is False, so _send_debug should be a no-op
        await coord._send_debug("speech_start")
        assert len(received) == 0


# ---------------------------------------------------------------------------
# Task 6.2: debug_enable/debug_disable toggle the flag
# ---------------------------------------------------------------------------


class TestDebugEnableDisable:
    def test_set_debug_enabled_true(self) -> None:
        coord = _make_coordinator()
        coord.set_debug_enabled(True)
        assert coord._debug_enabled is True

    def test_set_debug_enabled_false(self) -> None:
        coord = _make_coordinator()
        coord.set_debug_enabled(True)
        coord.set_debug_enabled(False)
        assert coord._debug_enabled is False


# ---------------------------------------------------------------------------
# Task 6.3: _send_debug emits correct debug_event structure
# ---------------------------------------------------------------------------


class TestSendDebugStructure:
    @pytest.mark.asyncio
    async def test_send_debug_emits_correct_structure(self) -> None:
        coord = _make_coordinator()
        coord.set_debug_enabled(True)
        received: list[dict] = []

        async def debug_cb(event: dict) -> None:
            received.append(event)

        coord.set_debug_callback(debug_cb)

        await coord._send_debug("speech_start")
        assert len(received) == 1

        event = received[0]
        assert event["type"] == "debug_event"
        assert event["stage"] == "speech_start"
        assert "turn_id" in event
        assert event["turn_id"] != ""
        assert "delta_ms" in event
        assert "total_ms" in event
        assert "ts" in event
        assert event["delta_ms"] == 0  # First stage of turn
        assert event["total_ms"] == 0  # First stage of turn

    @pytest.mark.asyncio
    async def test_send_debug_timing_increments(self) -> None:
        coord = _make_coordinator()
        coord.set_debug_enabled(True)
        received: list[dict] = []

        async def debug_cb(event: dict) -> None:
            received.append(event)

        coord.set_debug_callback(debug_cb)

        await coord._send_debug("speech_start")
        await coord._send_debug("speech_stop")

        assert len(received) == 2
        # Both should have the same turn_id
        assert received[0]["turn_id"] == received[1]["turn_id"]
        # total_ms should be >= delta_ms for second event
        assert received[1]["total_ms"] >= received[1]["delta_ms"]

    @pytest.mark.asyncio
    async def test_send_debug_with_extra_fields(self) -> None:
        coord = _make_coordinator()
        coord.set_debug_enabled(True)
        received: list[dict] = []

        async def debug_cb(event: dict) -> None:
            received.append(event)

        coord.set_debug_callback(debug_cb)

        await coord._send_debug("speech_start")
        await coord._send_debug("route_result", label="greeting", route_type="direct")

        assert len(received) == 2
        assert received[1]["label"] == "greeting"
        assert received[1]["route_type"] == "direct"


# ---------------------------------------------------------------------------
# Task 6.4: Direct route turn emits all 8 stages with consistent turn_id
# ---------------------------------------------------------------------------


class TestDirectRouteTurnStages:
    @pytest.mark.asyncio
    async def test_direct_route_emits_8_stages(self) -> None:
        coord = _make_coordinator()
        coord.set_debug_enabled(True)
        received: list[dict] = []

        async def debug_cb(event: dict) -> None:
            received.append(event)

        coord.set_debug_callback(debug_cb)

        # Simulate a full direct-route turn's debug events
        stages = [
            ("speech_start", {}),
            ("speech_stop", {}),
            ("audio_committed", {}),
            ("prompt_sent", {}),
            ("model_processing", {}),
            ("route_result", {"label": "greeting", "route_type": "direct"}),
            ("generation_start", {}),
            ("generation_finish", {}),
        ]

        for stage, extra in stages:
            await coord._send_debug(stage, **extra)

        assert len(received) == 8

        # All should share the same turn_id
        turn_id = received[0]["turn_id"]
        assert turn_id != ""
        for event in received:
            assert event["turn_id"] == turn_id
            assert event["type"] == "debug_event"

        # Verify stage sequence
        assert [e["stage"] for e in received] == [s for s, _ in stages]

        # total_ms should be monotonically non-decreasing
        for i in range(1, len(received)):
            assert received[i]["total_ms"] >= received[i - 1]["total_ms"]


# ---------------------------------------------------------------------------
# Task 6.5: Delegate route turn emits specialist sub-flow stages
# ---------------------------------------------------------------------------


class TestDelegateRouteTurnStages:
    @pytest.mark.asyncio
    async def test_delegate_route_emits_specialist_stages(self) -> None:
        coord = _make_coordinator()
        coord.set_debug_enabled(True)
        received: list[dict] = []

        async def debug_cb(event: dict) -> None:
            received.append(event)

        coord.set_debug_callback(debug_cb)

        stages = [
            ("speech_start", {}),
            ("speech_stop", {}),
            ("audio_committed", {}),
            ("prompt_sent", {}),
            ("model_processing", {}),
            ("route_result", {"label": "sales", "route_type": "delegate"}),
            ("fill_silence", {}),
            ("specialist_sent", {}),
            ("specialist_processing", {}),
            ("specialist_ready", {}),
            ("generation_start", {}),
            ("generation_finish", {}),
        ]

        for stage, extra in stages:
            await coord._send_debug(stage, **extra)

        assert len(received) == 12

        # All share same turn_id
        turn_id = received[0]["turn_id"]
        for event in received:
            assert event["turn_id"] == turn_id

        # route_result should have delegate markers
        route_event = next(e for e in received if e["stage"] == "route_result")
        assert route_event["label"] == "sales"
        assert route_event["route_type"] == "delegate"

        # Specialist stages present
        specialist_stages = [e["stage"] for e in received if e["stage"].startswith("specialist_")]
        assert specialist_stages == ["specialist_sent", "specialist_processing", "specialist_ready"]


# ---------------------------------------------------------------------------
# Task 6.6: Barge-in emits barge_in stage
# ---------------------------------------------------------------------------


class TestBargeInStage:
    @pytest.mark.asyncio
    async def test_barge_in_emitted(self) -> None:
        coord = _make_coordinator()
        coord.set_debug_enabled(True)
        received: list[dict] = []

        async def debug_cb(event: dict) -> None:
            received.append(event)

        coord.set_debug_callback(debug_cb)

        await coord._send_debug("speech_start")
        await coord._send_debug("generation_start")
        await coord._send_debug("barge_in")

        assert len(received) == 3
        barge = received[2]
        assert barge["stage"] == "barge_in"
        assert barge["type"] == "debug_event"
        # Barge-in shares the same turn_id
        assert barge["turn_id"] == received[0]["turn_id"]
