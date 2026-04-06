"""E2E integration tests for model-as-router event pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.voice_runtime.events import (
    CancelAgentGeneration,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
)
from src.voice_runtime.types import AgentState

from .conftest import make_e2e_stack


# ---------------------------------------------------------------------------
# Simple turn lifecycle (audio_committed triggers response.create)
# ---------------------------------------------------------------------------


class TestSimpleTurnLifecycle:
    @pytest.mark.asyncio
    async def test_audio_committed_produces_voice_start(self) -> None:
        """audio_committed triggers router prompt and emits RealtimeVoiceStart."""
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started()
        await fake.audio_committed()

        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1
        # prompt is a response.create payload (dict) from RouterPromptBuilder
        assert isinstance(voice_starts[0].prompt, dict)
        assert voice_starts[0].prompt["type"] == "response.create"

    @pytest.mark.asyncio
    async def test_voice_completed_keeps_voice_id_until_playback_end(self) -> None:
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started()
        await fake.audio_committed()

        events = capture.drain()
        voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)][0]

        await fake.voice_completed(voice_start.voice_generation_id)
        # voice_generation_id stays set until audio_playback_end from frontend
        # so barge-in detection works during browser audio playback.
        assert coord.state.active_voice_generation_id is not None

    @pytest.mark.asyncio
    async def test_fsm_transitions_through_lifecycle(self) -> None:
        """FSM: idle → routing → (voice_started by bridge) → done on voice_completed."""
        coord, fake, capture = make_e2e_stack()
        assert coord._agent_fsm.state == AgentState.IDLE

        await fake.speech_started()
        await fake.audio_committed()
        assert coord._agent_fsm.state == AgentState.ROUTING

        capture.drain()

    @pytest.mark.asyncio
    async def test_turn_seq_increments(self) -> None:
        coord, fake, capture = make_e2e_stack()
        assert coord.state.turn_seq == 0

        await fake.speech_started()
        await fake.audio_committed()
        assert coord.state.turn_seq == 1

        capture.drain()


# ---------------------------------------------------------------------------
# Transcript final — async logging only (no routing trigger)
# ---------------------------------------------------------------------------


class TestTranscriptAsyncLogging:
    @pytest.mark.asyncio
    async def test_transcript_final_does_not_trigger_routing(self) -> None:
        """transcript_final alone should NOT produce any voice events."""
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started()
        await fake.transcript_final("hello world")

        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 0

    @pytest.mark.asyncio
    async def test_transcript_appends_to_conversation_buffer(self) -> None:
        """transcript_final adds text to conversation buffer for history."""
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started()
        await fake.audio_committed()
        capture.drain()

        await fake.transcript_final("hello world")
        assert len(coord._conversation_buffer) == 1


# ---------------------------------------------------------------------------
# Model router action — specialist dispatch
# ---------------------------------------------------------------------------


class TestModelRouterAction:
    @pytest.mark.asyncio
    async def test_specialist_action_emits_specialist_voice(self) -> None:
        """model_router_action triggers filler + specialist tool + specialist voice response."""
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started()
        await fake.audio_committed()
        capture.drain()  # Clear the initial voice start

        await fake.model_router_action(department="billing", summary="invoice issue")
        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        # Expect filler + specialist = at least 2 voice starts (billing has fillers configured)
        assert len(voice_starts) >= 2
        # First voice start is the per-department filler
        filler = voice_starts[0]
        assert isinstance(filler.prompt, str)
        # Last voice start is the specialist response
        specialist = voice_starts[-1]
        assert specialist.response_source == "specialist"

    @pytest.mark.asyncio
    async def test_specialist_action_transitions_fsm(self) -> None:
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started()
        await fake.audio_committed()
        assert coord._agent_fsm.state == AgentState.ROUTING
        capture.drain()

        await fake.model_router_action(department="support", summary="help needed")
        # After specialist: routing → waiting_tools → speaking (tool completes inline)
        assert coord._agent_fsm.state == AgentState.SPEAKING

    @pytest.mark.asyncio
    async def test_str_payload_wrapped_in_directive(self) -> None:
        """When specialist tool returns str, coordinator wraps in 'say exactly' directive."""
        from src.voice_runtime.events import ToolResult

        coord, fake, capture = make_e2e_stack()
        # Configure mock to return str payload (text model success)
        coord._tool_executor.execute = AsyncMock(
            return_value=ToolResult(
                call_id=coord._call_id,
                agent_generation_id=uuid4(),
                tool_request_id=uuid4(),
                ok=True,
                payload="Entiendo. ¿Podrías darme tu número de factura?",
                ts=3000,
            )
        )
        await fake.speech_started()
        await fake.audio_committed()
        capture.drain()

        await fake.model_router_action(department="billing", summary="refund")
        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        specialist = [v for v in voice_starts if v.response_source == "specialist"][0]
        assert isinstance(specialist.prompt, dict)
        assert specialist.prompt["type"] == "response.create"
        instructions = specialist.prompt["response"]["instructions"]
        assert "Say exactly" in instructions
        assert "Entiendo. ¿Podrías darme tu número de factura?" in instructions

    @pytest.mark.asyncio
    async def test_dict_payload_forwarded_directly(self) -> None:
        """When specialist tool returns dict (fallback), coordinator forwards it directly."""
        from src.voice_runtime.events import ToolResult

        coord, fake, capture = make_e2e_stack()
        fallback_dict = {
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"],
                "instructions": "You are a billing specialist...",
                "temperature": 0.8,
            },
        }
        coord._tool_executor.execute = AsyncMock(
            return_value=ToolResult(
                call_id=coord._call_id,
                agent_generation_id=uuid4(),
                tool_request_id=uuid4(),
                ok=True,
                payload=fallback_dict,
                ts=3000,
            )
        )
        await fake.speech_started()
        await fake.audio_committed()
        capture.drain()

        await fake.model_router_action(department="billing", summary="refund")
        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        specialist = [v for v in voice_starts if v.response_source == "specialist"][0]
        assert specialist.prompt == fallback_dict


# ---------------------------------------------------------------------------
# Barge-in during voice output
# ---------------------------------------------------------------------------


class TestBargeInDuringVoice:
    @pytest.mark.asyncio
    async def test_barge_in_cancels_voice_and_agent(self) -> None:
        coord, fake, capture = make_e2e_stack()
        # First turn
        await fake.speech_started(ts=1000)
        await fake.audio_committed(ts=2000)
        first_events = capture.drain()
        voice_start = [e for e in first_events if isinstance(e, RealtimeVoiceStart)][0]

        # Barge-in
        await fake.speech_started(ts=2500)
        barge_events = capture.drain()

        voice_cancels = [e for e in barge_events if isinstance(e, RealtimeVoiceCancel)]
        assert len(voice_cancels) == 1
        assert voice_cancels[0].voice_generation_id == voice_start.voice_generation_id
        assert voice_cancels[0].reason == "barge_in"

    @pytest.mark.asyncio
    async def test_barge_in_then_new_turn(self) -> None:
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started(ts=1000)
        await fake.audio_committed(ts=2000)
        capture.drain()

        # Barge-in + new turn
        await fake.speech_started(ts=2500)
        capture.drain()
        await fake.audio_committed(ts=3000)

        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1


# ---------------------------------------------------------------------------
# Barge-in during tool execution (late tool_result ignored)
# ---------------------------------------------------------------------------


class TestBargeInDuringTool:
    @pytest.mark.asyncio
    async def test_late_tool_result_ignored_after_cancel(self) -> None:
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started(ts=1000)
        await fake.audio_committed(ts=2000)
        first_gen_id = coord.state.active_agent_generation_id
        capture.drain()

        # Barge-in cancels the generation
        await fake.speech_started(ts=2500)
        capture.drain()

        # Late tool_result arrives — should be ignored
        await fake.tool_result(first_gen_id, ts=3000)
        events = capture.drain()
        assert len(events) == 0


# ---------------------------------------------------------------------------
# Filler strategy
# ---------------------------------------------------------------------------


class TestFillerStrategy:
    @pytest.mark.asyncio
    async def test_filler_disabled_by_default(self) -> None:
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started()
        await fake.audio_committed()
        capture.drain()

        # Trigger specialist action — filler should NOT emit
        await fake.model_router_action(department="sales", summary="purchase")
        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        filler_events = [
            e for e in voice_starts
            if isinstance(e.prompt, str) and "momento" in e.prompt.lower()
        ]
        assert len(filler_events) == 0


# ---------------------------------------------------------------------------
# Idempotency — duplicate event_id ignored
# ---------------------------------------------------------------------------


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_event_id_ignored(self) -> None:
        coord, fake, capture = make_e2e_stack()
        event_id = uuid4()

        await fake.inject_duplicate(event_id, ts=1000)
        first_events = capture.drain()

        await fake.inject_duplicate(event_id, ts=1000)
        second_events = capture.drain()

        assert len(second_events) == 0


# ---------------------------------------------------------------------------
# Rapid successive turns — previous generation cancelled
# ---------------------------------------------------------------------------


class TestRapidSuccessiveTurns:
    @pytest.mark.asyncio
    async def test_second_turn_cancels_first_generation(self) -> None:
        coord, fake, capture = make_e2e_stack()
        # First turn
        await fake.speech_started(ts=1000)
        await fake.audio_committed(ts=2000)
        first_gen_id = coord.state.active_agent_generation_id
        capture.drain()

        # Second turn (barge-in + new audio_committed)
        await fake.speech_started(ts=2500)
        await fake.audio_committed(ts=3000)

        second_gen_id = coord.state.active_agent_generation_id
        assert second_gen_id != first_gen_id
        assert coord.state.is_generation_cancelled(first_gen_id)


# ---------------------------------------------------------------------------
# Voice generation error
# ---------------------------------------------------------------------------


class TestVoiceGenerationError:
    @pytest.mark.asyncio
    async def test_voice_error_clears_active_voice(self) -> None:
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started()
        await fake.audio_committed()

        events = capture.drain()
        voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)][0]

        await fake.voice_error(voice_start.voice_generation_id, error="provider_timeout")
        assert coord.state.active_voice_generation_id is None

    @pytest.mark.asyncio
    async def test_cancelled_voice_error_ignored(self) -> None:
        coord, fake, capture = make_e2e_stack()
        voice_id = uuid4()
        coord.state.cancelled_voice_generations.add(voice_id)
        await fake.voice_error(voice_id)
        # Should not crash or change state


# ---------------------------------------------------------------------------
# Call cleanup — state clean, no orphaned tasks
# ---------------------------------------------------------------------------


class TestCallCleanup:
    @pytest.mark.asyncio
    async def test_state_clean_after_full_lifecycle(self) -> None:
        coord, fake, capture = make_e2e_stack()
        # Full turn
        await fake.speech_started()
        await fake.audio_committed()
        events = capture.drain()
        voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)][0]

        await fake.voice_completed(voice_start.voice_generation_id)
        assert coord.state.active_voice_generation_id is not None
        assert coord._filler_task is None

    @pytest.mark.asyncio
    async def test_no_orphaned_filler_task(self) -> None:
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started(ts=1000)
        await fake.audio_committed(ts=2000)
        capture.drain()

        await fake.speech_started(ts=2500)
        assert coord._filler_task is None

    @pytest.mark.asyncio
    async def test_multiple_turns_all_tracked(self) -> None:
        coord, fake, capture = make_e2e_stack()
        for i in range(3):
            await fake.speech_started(ts=1000 + i * 3000)
            await fake.audio_committed(ts=2000 + i * 3000)
            events = capture.drain()
            voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)]
            if voice_start:
                await fake.voice_completed(
                    voice_start[-1].voice_generation_id, ts=2500 + i * 3000
                )

        assert coord.state.turn_seq == 3


# ---------------------------------------------------------------------------
# Multi-turn conversation history
# ---------------------------------------------------------------------------


class TestMultiTurnHistory:
    @pytest.mark.asyncio
    async def test_second_turn_includes_history_in_prompt(self) -> None:
        """Second turn's response.create includes conversation history."""
        coord, fake, capture = make_e2e_stack()
        # Turn 1
        await fake.speech_started(ts=1000)
        await fake.audio_committed(ts=2000)
        capture.drain()
        # Transcript arrives async
        await fake.transcript_final("hola", ts=2500)
        # Complete voice
        voice_id = coord.state.active_voice_generation_id
        await fake.voice_completed(voice_id, ts=3000)

        # Turn 2
        await fake.speech_started(ts=4000)
        await fake.audio_committed(ts=5000)
        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1

        # The response.create payload should include history in instructions
        payload = voice_starts[0].prompt
        assert payload["type"] == "response.create"
        response = payload["response"]
        assert "instructions" in response
        # History is embedded as "User: hola" in the instructions string
        instructions = response["instructions"]
        assert "User: hola" in instructions

    @pytest.mark.asyncio
    async def test_three_turns_history_accumulation(self) -> None:
        """Three turns accumulate history correctly."""
        coord, fake, capture = make_e2e_stack()
        texts = ["uno", "dos", "tres"]

        for i, text in enumerate(texts):
            await fake.speech_started(ts=1000 + i * 4000)
            await fake.audio_committed(ts=2000 + i * 4000)
            capture.drain()
            await fake.transcript_final(text, ts=2500 + i * 4000)
            voice_id = coord.state.active_voice_generation_id
            await fake.voice_completed(voice_id, ts=3000 + i * 4000)

        assert len(coord._conversation_buffer) == 3

        # Fourth turn should see all 3 in history (embedded in instructions)
        await fake.speech_started(ts=13000)
        await fake.audio_committed(ts=14000)
        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        payload = voice_starts[0].prompt
        instructions = payload["response"]["instructions"]
        assert "User: uno" in instructions
        assert "User: dos" in instructions
        assert "User: tres" in instructions


# ---------------------------------------------------------------------------
# Specialist turn with tool execution
# ---------------------------------------------------------------------------


class TestSpecialistTurnE2E:
    @pytest.mark.asyncio
    async def test_full_specialist_flow(self) -> None:
        """audio_committed → voice_start → model_router_action → specialist voice."""
        coord, fake, capture = make_e2e_stack()

        # Turn starts
        await fake.speech_started()
        await fake.audio_committed()
        initial_events = capture.drain()
        # First voice_start is the router prompt
        assert len([e for e in initial_events if isinstance(e, RealtimeVoiceStart)]) == 1

        # Model detects specialist need
        await fake.model_router_action(department="billing", summary="invoice problem")
        specialist_events = capture.drain()
        specialist_starts = [e for e in specialist_events if isinstance(e, RealtimeVoiceStart)]
        assert len(specialist_starts) >= 1

    @pytest.mark.asyncio
    async def test_specialist_voice_completed(self) -> None:
        """Complete specialist flow cleans up state."""
        coord, fake, capture = make_e2e_stack()
        await fake.speech_started()
        await fake.audio_committed()
        capture.drain()

        await fake.model_router_action(department="support", summary="help")
        events = capture.drain()
        specialist_voice = [e for e in events if isinstance(e, RealtimeVoiceStart)][-1]

        await fake.voice_completed(specialist_voice.voice_generation_id)
        assert coord.state.active_voice_generation_id is not None
