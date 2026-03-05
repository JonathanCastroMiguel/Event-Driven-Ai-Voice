"""E2E test fixtures: FakeRealtime and OutputCapture (tasks 14.1-14.2)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.routing.policies import PoliciesRegistry
from src.routing.router import Router, RoutingResult
from src.voice_runtime.agent_fsm import AgentFSM
from src.voice_runtime.coordinator import Coordinator
from src.voice_runtime.events import (
    CancelAgentGeneration,
    EventEnvelope,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
)
from src.voice_runtime.realtime_client import StubRealtimeClient
from src.voice_runtime.tool_executor import ToolExecutor
from src.voice_runtime.turn_manager import TurnManager
from src.voice_runtime.types import (
    EventSource,
    PolicyKey,
    RouteALabel,
    RouteBLabel,
)


# ---------------------------------------------------------------------------
# 14.1 FakeRealtime — injects events, captures output
# ---------------------------------------------------------------------------


class FakeRealtime:
    """Injects speech/transcript events into a Coordinator and captures output."""

    def __init__(self, coordinator: Coordinator, stub_client: StubRealtimeClient) -> None:
        self._coord = coordinator
        self._stub = stub_client
        self._call_id = coordinator._call_id

    async def speech_started(self, ts: int = 1000) -> None:
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="speech_started",
            payload={},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)

    async def transcript_final(self, text: str, ts: int = 2000) -> None:
        from unittest.mock import patch

        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="transcript_final",
            payload={"text": text},
            source=EventSource.REALTIME,
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await self._coord.handle_event(env)

    async def voice_completed(self, voice_generation_id: UUID, ts: int = 3000) -> None:
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="voice_generation_completed",
            payload={"voice_generation_id": str(voice_generation_id)},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)

    async def voice_error(self, voice_generation_id: UUID, error: str = "fail", ts: int = 3000) -> None:
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="voice_generation_error",
            payload={"voice_generation_id": str(voice_generation_id), "error": error},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)

    async def tool_result(self, agent_generation_id: UUID, ts: int = 2500) -> None:
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="tool_result",
            payload={"agent_generation_id": str(agent_generation_id)},
            source=EventSource.TOOL_EXEC,
        )
        await self._coord.handle_event(env)

    async def inject_duplicate(self, event_id: UUID, ts: int = 1000) -> None:
        env = EventEnvelope(
            event_id=event_id,
            call_id=self._call_id,
            ts=ts,
            type="speech_started",
            payload={},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)


# ---------------------------------------------------------------------------
# 14.2 OutputCapture — waits for specific event types
# ---------------------------------------------------------------------------


class OutputCapture:
    """Captures and filters output events from the Coordinator."""

    def __init__(self, coordinator: Coordinator) -> None:
        self._coord = coordinator

    def drain(self) -> list[RealtimeVoiceStart | RealtimeVoiceCancel | CancelAgentGeneration]:
        return self._coord.drain_output_events()

    def drain_voice_starts(self) -> list[RealtimeVoiceStart]:
        return [e for e in self.drain() if isinstance(e, RealtimeVoiceStart)]

    def drain_voice_cancels(self) -> list[RealtimeVoiceCancel]:
        return [e for e in self.drain() if isinstance(e, RealtimeVoiceCancel)]

    def drain_gen_cancels(self) -> list[CancelAgentGeneration]:
        return [e for e in self.drain() if isinstance(e, CancelAgentGeneration)]

    async def wait_for_voice_start(self, timeout: float = 0.5) -> RealtimeVoiceStart | None:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            starts = self.drain_voice_starts()
            if starts:
                return starts[0]
            await asyncio.sleep(0.01)
        return None


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def make_policies() -> PoliciesRegistry:
    return PoliciesRegistry(
        base_system="You are a helpful agent.",
        policies={k.value: f"Instructions for {k.value}" for k in PolicyKey},
    )


def make_router(
    route_a: RouteALabel = RouteALabel.SIMPLE,
    confidence: float = 0.95,
    route_b: RouteBLabel | None = None,
    route_b_confidence: float | None = None,
) -> Router:
    mock = MagicMock(spec=Router)
    mock.classify = AsyncMock(
        return_value=RoutingResult(
            route_a_label=route_a,
            route_a_confidence=confidence,
            route_b_label=route_b,
            route_b_confidence=route_b_confidence,
        )
    )
    # Expose _registry for calibration logging
    mock._registry = MagicMock()
    mock._registry.thresholds.version = "test-v1"
    return mock


def make_e2e_stack(
    router: Router | None = None,
) -> tuple[Coordinator, FakeRealtime, OutputCapture, StubRealtimeClient]:
    call_id = uuid4()
    stub = StubRealtimeClient(delay_ms=10)
    coord = Coordinator(
        call_id=call_id,
        turn_manager=TurnManager(call_id),
        agent_fsm=AgentFSM(call_id),
        tool_executor=MagicMock(spec=ToolExecutor),
        router=router or make_router(),
        policies=make_policies(),
    )
    fake = FakeRealtime(coord, stub)
    capture = OutputCapture(coord)
    return coord, fake, capture, stub
