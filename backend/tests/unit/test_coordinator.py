"""Unit tests for Coordinator (model-as-router architecture)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.routing.model_router import RouterPromptBuilder, RouterPromptTemplate
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
from src.voice_runtime.types import (
    AgentState,
    EventSource,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_policies() -> PoliciesRegistry:
    return PoliciesRegistry(
        base_system="You are a helpful agent.",
        policies={
            "greeting": "Instructions for greeting",
            "handoff_offer": "Instructions for handoff_offer",
            "guardrail_disallowed": "Instructions for guardrail_disallowed",
            "guardrail_out_of_scope": "Instructions for guardrail_out_of_scope",
            "clarify_department": "Instructions for clarify_department",
        },
    )


def _make_router_prompt_builder() -> RouterPromptBuilder:
    template = RouterPromptTemplate(
        identity="You are a call center agent.",
        decision_rules="Decide how to help.",
        departments="sales, billing, support, retention",
        guardrails="Be polite.",
        language_instruction="Respond in the same language.",
    )
    return RouterPromptBuilder(template)


def _make_coordinator(
    call_id: UUID | None = None,
    router_prompt_builder: RouterPromptBuilder | None = None,
    turn_repo: object = None,
    agent_gen_repo: object = None,
    voice_gen_repo: object = None,
) -> Coordinator:
    cid = call_id or uuid4()
    return Coordinator(
        call_id=cid,
        turn_manager=TurnManager(call_id=cid),
        agent_fsm=AgentFSM(call_id=cid),
        tool_executor=ToolExecutor(),
        router_prompt_builder=router_prompt_builder or _make_router_prompt_builder(),
        policies=_make_policies(),
        turn_repo=turn_repo,
        agent_gen_repo=agent_gen_repo,
        voice_gen_repo=voice_gen_repo,
    )


def _envelope(
    event_type: str,
    call_id: UUID,
    ts: int = 1000,
    payload: dict | None = None,
    source: EventSource = EventSource.REALTIME,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        call_id=call_id,
        ts=ts,
        type=event_type,
        payload=payload or {},
        source=source,
    )


# ---------------------------------------------------------------------------
# Audio committed handler (5.7)
# ---------------------------------------------------------------------------


class TestAudioCommitted:
    @pytest.mark.asyncio
    async def test_audio_committed_emits_voice_start(self) -> None:
        """audio_committed should finalize turn and emit voice start with router prompt."""
        coord = _make_coordinator()
        cid = coord._call_id

        # First, open a turn via speech_started
        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        # Then commit audio
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))

        events = coord.drain_output_events()
        assert len(events) == 1
        assert isinstance(events[0], RealtimeVoiceStart)
        # The prompt should be the response.create payload dict
        assert isinstance(events[0].prompt, dict)
        assert events[0].prompt["type"] == "response.create"

    @pytest.mark.asyncio
    async def test_audio_committed_transitions_fsm_to_routing(self) -> None:
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))

        assert coord._agent_fsm.state == AgentState.ROUTING

    @pytest.mark.asyncio
    async def test_audio_committed_sets_active_turn(self) -> None:
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))

        assert coord.state.active_turn_id is not None
        assert coord.state.active_agent_generation_id is not None
        assert coord.state.active_voice_generation_id is not None

    @pytest.mark.asyncio
    async def test_audio_committed_without_speech_ignored(self) -> None:
        """audio_committed without prior speech_started produces no events."""
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("audio_committed", cid, ts=1000))

        events = coord.drain_output_events()
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_first_turn_no_history_in_prompt(self) -> None:
        """First turn should have no input messages in the response.create payload."""
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))

        events = coord.drain_output_events()
        payload = events[0].prompt
        # No input since conversation buffer is empty
        assert "input" not in payload.get("response", {})

    @pytest.mark.asyncio
    async def test_second_turn_includes_history(self) -> None:
        """After transcript_final arrives, subsequent turns should include history."""
        coord = _make_coordinator()
        cid = coord._call_id

        # Turn 1
        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))
        coord.drain_output_events()

        # Transcript arrives async
        await coord.handle_event(
            _envelope("transcript_final", cid, ts=1700, payload={"text": "hola"})
        )

        # FSM needs reset for next turn
        coord._agent_fsm.voice_started(ts=1800)
        coord._agent_fsm.voice_completed(ts=1900)
        coord._agent_fsm.reset()

        # Turn 2
        await coord.handle_event(_envelope("speech_started", cid, ts=2000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=2500))

        events = coord.drain_output_events()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1
        payload = voice_starts[0].prompt
        # History should be embedded in instructions (not in response.input)
        instructions = payload.get("response", {}).get("instructions", "")
        assert "Conversation history:" in instructions
        assert "input" not in payload.get("response", {})


# ---------------------------------------------------------------------------
# Transcript final — async logging only (5.9)
# ---------------------------------------------------------------------------


class TestTranscriptFinalLogging:
    @pytest.mark.asyncio
    async def test_transcript_final_no_routing(self) -> None:
        """transcript_final should NOT emit any voice start or routing events."""
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(
            _envelope("transcript_final", cid, ts=1200, payload={"text": "hola"})
        )

        events = coord.drain_output_events()
        # No voice start events from transcript_final
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_transcript_final_stores_in_turn_manager(self) -> None:
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(
            _envelope("transcript_final", cid, ts=1200, payload={"text": "mi factura"})
        )

        assert coord._turn_manager.current_transcript == "mi factura"

    @pytest.mark.asyncio
    async def test_transcript_final_appends_to_buffer(self) -> None:
        """transcript_final should add to conversation buffer for future turns."""
        coord = _make_coordinator()
        cid = coord._call_id

        # Open a turn and commit it
        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))
        coord.drain_output_events()

        # Transcript arrives
        await coord.handle_event(
            _envelope("transcript_final", cid, ts=1700, payload={"text": "hola"})
        )

        # Buffer should have the entry (user + assistant pair)
        messages = coord._conversation_buffer.format_messages()
        assert len(messages) == 2  # user + assistant
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hola"


# ---------------------------------------------------------------------------
# Model router action — specialist dispatch (5.8)
# ---------------------------------------------------------------------------


class TestModelRouterAction:
    @pytest.mark.asyncio
    async def test_model_router_action_emits_specialist_voice(self) -> None:
        """model_router_action should trigger specialist tool and emit voice start."""
        coord = _make_coordinator()
        cid = coord._call_id

        # Setup: open turn, commit, enter routing state
        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))
        coord.drain_output_events()  # drain the router voice start

        # Simulate model_router_action
        await coord.handle_event(
            _envelope(
                "model_router_action",
                cid,
                ts=2000,
                payload={"department": "billing", "summary": "factura incorrecta"},
            )
        )

        events = coord.drain_output_events()
        # Should emit specialist voice start
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) >= 1

    @pytest.mark.asyncio
    async def test_model_router_action_fsm_transitions(self) -> None:
        """FSM should go routing → waiting_tools → speaking."""
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))
        coord.drain_output_events()

        assert coord._agent_fsm.state == AgentState.ROUTING

        await coord.handle_event(
            _envelope(
                "model_router_action",
                cid,
                ts=2000,
                payload={"department": "billing", "summary": "test"},
            )
        )

        # After tool execution and voice emission, FSM should be in SPEAKING
        assert coord._agent_fsm.state == AgentState.SPEAKING

    @pytest.mark.asyncio
    async def test_model_router_action_cancelled_gen_ignored(self) -> None:
        """Late model_router_action for cancelled generation should be ignored."""
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))
        coord.drain_output_events()

        # Cancel the generation
        gen_id = coord.state.active_agent_generation_id
        coord.state.cancel_active_generation()

        await coord.handle_event(
            _envelope(
                "model_router_action",
                cid,
                ts=2000,
                payload={"department": "billing", "summary": "test"},
            )
        )

        events = coord.drain_output_events()
        assert len(events) == 0


# ---------------------------------------------------------------------------
# Barge-in handling
# ---------------------------------------------------------------------------


class TestBargeIn:
    @pytest.mark.asyncio
    async def test_barge_in_cancels_voice_and_generation(self) -> None:
        coord = _make_coordinator()
        cid = coord._call_id

        # Start and commit a turn
        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))
        coord.drain_output_events()

        # Barge in with new speech
        await coord.handle_event(_envelope("speech_started", cid, ts=2000))

        events = coord.drain_output_events()
        cancel_events = [e for e in events if isinstance(e, (RealtimeVoiceCancel, CancelAgentGeneration))]
        assert len(cancel_events) >= 1

    @pytest.mark.asyncio
    async def test_barge_in_resets_fsm(self) -> None:
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))
        coord.drain_output_events()

        # Barge in
        await coord.handle_event(_envelope("speech_started", cid, ts=2000))

        # FSM should be reset to IDLE after cancellation
        assert coord._agent_fsm.state == AgentState.IDLE


# ---------------------------------------------------------------------------
# Voice completed
# ---------------------------------------------------------------------------


class TestVoiceCompleted:
    @pytest.mark.asyncio
    async def test_voice_completed_transitions_fsm_to_done(self) -> None:
        coord = _make_coordinator()
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))
        events = coord.drain_output_events()

        # Simulate direct voice: routing → speaking
        coord._agent_fsm.voice_started(ts=1600)

        voice_gen_id = events[0].voice_generation_id

        await coord.handle_event(
            _envelope(
                "voice_generation_completed",
                cid,
                ts=2000,
                payload={"voice_generation_id": str(voice_gen_id)},
            )
        )

        assert coord._agent_fsm.state == AgentState.DONE


# ---------------------------------------------------------------------------
# Persistence wiring
# ---------------------------------------------------------------------------


class TestPersistenceWiring:
    @pytest.mark.asyncio
    async def test_turn_persisted_on_committed(self) -> None:
        turn_repo = MagicMock()
        turn_repo.insert = AsyncMock()
        turn_repo.update = AsyncMock()

        coord = _make_coordinator(turn_repo=turn_repo)
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))

        turn_repo.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_gen_persisted_on_committed(self) -> None:
        agent_gen_repo = MagicMock()
        agent_gen_repo.insert = AsyncMock()

        coord = _make_coordinator(agent_gen_repo=agent_gen_repo)
        cid = coord._call_id

        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))

        agent_gen_repo.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_persistence_error_does_not_crash(self) -> None:
        turn_repo = MagicMock()
        turn_repo.insert = AsyncMock(side_effect=Exception("db error"))

        coord = _make_coordinator(turn_repo=turn_repo)
        cid = coord._call_id

        # Should not raise
        await coord.handle_event(_envelope("speech_started", cid, ts=1000))
        await coord.handle_event(_envelope("audio_committed", cid, ts=1500))

        events = coord.drain_output_events()
        assert len(events) == 1  # Voice start still emitted
