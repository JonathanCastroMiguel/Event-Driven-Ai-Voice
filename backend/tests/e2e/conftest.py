"""E2E test fixtures for model-as-router architecture."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from src.routing.model_router import (
    AgentConfig,
    RouterPromptBuilder,
    RouterPromptConfig,
    ToolConfig,
)
from src.routing.policies import PoliciesRegistry
from src.voice_runtime.agent_fsm import AgentFSM
from src.voice_runtime.coordinator import Coordinator
from src.voice_runtime.events import (
    CancelAgentGeneration,
    EventEnvelope,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
)
from src.voice_runtime.tool_executor import ToolExecutor
from src.voice_runtime.turn_manager import TurnManager
from src.voice_runtime.types import EventSource, PolicyKey


# ---------------------------------------------------------------------------
# FakeRealtime — injects events into Coordinator
# ---------------------------------------------------------------------------


class FakeRealtime:
    """Injects events into a Coordinator for E2E testing."""

    def __init__(self, coordinator: Coordinator) -> None:
        self._coord = coordinator
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

    async def audio_committed(self, ts: int = 2000) -> None:
        """Primary turn trigger in model-as-router architecture."""
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="audio_committed",
            payload={},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)

    async def transcript_final(self, text: str, ts: int = 2500) -> None:
        """Async logging only — does NOT trigger routing."""
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="transcript_final",
            payload={"text": text},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)

    async def model_router_action(
        self, department: str, summary: str, ts: int = 3000
    ) -> None:
        """Simulate the bridge detecting a JSON action from the model."""
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="model_router_action",
            payload={"department": department, "summary": summary},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)

    async def voice_completed(self, voice_generation_id: UUID, ts: int = 4000) -> None:
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="voice_generation_completed",
            payload={"voice_generation_id": str(voice_generation_id)},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)

    async def voice_error(
        self, voice_generation_id: UUID, error: str = "fail", ts: int = 4000
    ) -> None:
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="voice_generation_error",
            payload={"voice_generation_id": str(voice_generation_id), "error": error},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)

    async def tool_result(self, agent_generation_id: UUID, ts: int = 3500) -> None:
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="tool_result",
            payload={"agent_generation_id": str(agent_generation_id)},
            source=EventSource.TOOL_EXEC,
        )
        await self._coord.handle_event(env)

    async def speech_stopped(self, ts: int = 1500) -> None:
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="speech_stopped",
            payload={},
            source=EventSource.REALTIME,
        )
        await self._coord.handle_event(env)

    async def response_created(self, ts: int = 2800) -> None:
        """Simulate bridge emitting response.created envelope."""
        env = EventEnvelope(
            event_id=uuid4(),
            call_id=self._call_id,
            ts=ts,
            type="response_created",
            payload={"send_to_created_ms": 45},
            source=EventSource.REALTIME,
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
# OutputCapture — captures and filters output events
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


# ---------------------------------------------------------------------------
# DebugCapture — captures debug events emitted by Coordinator
# ---------------------------------------------------------------------------


class DebugCapture:
    """Captures debug_event messages emitted by the Coordinator."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def callback(self, event: dict[str, object]) -> None:
        self.events.append(event)

    def drain(self) -> list[dict[str, object]]:
        """Return all captured events and clear the buffer."""
        result = list(self.events)
        self.events.clear()
        return result

    @property
    def debug_events(self) -> list[dict[str, object]]:
        """Return only structured debug_event messages (from _send_debug)."""
        return [e for e in self.events if e.get("type") == "debug_event"]

    def stages(self) -> list[str]:
        """Return stage names from debug_event messages only."""
        return [str(e.get("stage", "")) for e in self.debug_events]

    def by_stage(self, stage: str) -> list[dict[str, object]]:
        """Filter debug_event messages by stage name."""
        return [e for e in self.debug_events if e.get("stage") == stage]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
def make_policies() -> PoliciesRegistry:
    return PoliciesRegistry(
        base_system="You are a helpful agent.",
        policies={k.value: f"Instructions for {k.value}" for k in PolicyKey},
    )


def make_router_prompt_builder() -> RouterPromptBuilder:
    config = RouterPromptConfig(
        identity="You are a voice assistant for a call center.",
        agents={
            "direct": AgentConfig(
                description="Handle directly",
                triggers=["Greetings"],
                fillers=[],
                tool=None,
            ),
            "billing": AgentConfig(
                description="Billing",
                triggers=["Invoices"],
                fillers=["One moment, checking billing."],
                tool=ToolConfig(type="internal", name="specialist_billing"),
            ),
            "sales": AgentConfig(
                description="Sales",
                triggers=["Plans"],
                fillers=["Let me get sales."],
                tool=ToolConfig(type="internal", name="specialist_sales"),
            ),
            "support": AgentConfig(
                description="Support",
                triggers=["Issues"],
                fillers=["Connecting to support."],
                tool=ToolConfig(type="internal", name="specialist_support"),
            ),
            "retention": AgentConfig(
                description="Retention",
                triggers=["Cancel"],
                fillers=["Let me help with that."],
                tool=ToolConfig(type="internal", name="specialist_retention"),
            ),
        },
        guardrails=["Do not discuss prohibited topics."],
        language_instruction="Respond in the user's language.",
    )
    return RouterPromptBuilder(config)


def make_e2e_stack() -> tuple[Coordinator, FakeRealtime, OutputCapture]:
    """Create a full E2E stack with model-as-router architecture."""
    call_id = uuid4()
    tool_executor = MagicMock(spec=ToolExecutor)

    coord = Coordinator(
        call_id=call_id,
        turn_manager=TurnManager(call_id),
        agent_fsm=AgentFSM(call_id),
        tool_executor=tool_executor,
        router_prompt_builder=make_router_prompt_builder(),
        policies=make_policies(),
    )
    fake = FakeRealtime(coord)
    capture = OutputCapture(coord)
    return coord, fake, capture


def make_debug_e2e_stack() -> tuple[Coordinator, FakeRealtime, OutputCapture, DebugCapture]:
    """Create an E2E stack with debug enabled and a DebugCapture."""
    coord, fake, capture = make_e2e_stack()
    debug = DebugCapture()
    coord.set_debug_callback(debug.callback)
    coord.set_debug_enabled(True)
    return coord, fake, capture, debug
