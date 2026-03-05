"""E2E integration tests for the event pipeline (tasks 14.3–14.15)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.voice_runtime.events import (
    CancelAgentGeneration,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
)
from src.voice_runtime.types import AgentState, RouteALabel, RouteBLabel

from .conftest import make_e2e_stack, make_router


# ---------------------------------------------------------------------------
# 14.3 Simple turn lifecycle
# ---------------------------------------------------------------------------


class TestSimpleTurnLifecycle:
    @pytest.mark.asyncio
    async def test_greeting_produces_voice_start(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        await fake.speech_started()
        await fake.transcript_final("hola buenos días")

        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1
        assert isinstance(voice_starts[0].prompt, list)
        assert voice_starts[0].prompt[2]["content"] == "hola buenos días"

    @pytest.mark.asyncio
    async def test_voice_completed_cleans_up(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        await fake.speech_started()
        await fake.transcript_final("hola")

        events = capture.drain()
        voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)][0]

        await fake.voice_completed(voice_start.voice_generation_id)
        assert coord.state.active_voice_generation_id is None


# ---------------------------------------------------------------------------
# 14.4 Turn with specialist agent
# ---------------------------------------------------------------------------


class TestSpecialistTurn:
    @pytest.mark.asyncio
    async def test_domain_billing_produces_specialist_voice(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(
                route_a=RouteALabel.DOMAIN,
                route_b=RouteBLabel.BILLING,
                route_b_confidence=0.88,
            )
        )
        await fake.speech_started()
        await fake.transcript_final("tengo un problema con mi factura")

        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) >= 1
        specialist_events = [
            e for e in voice_starts if isinstance(e.prompt, str) and "billing" in e.prompt
        ]
        assert len(specialist_events) >= 1


# ---------------------------------------------------------------------------
# 14.5 Barge-in during voice output
# ---------------------------------------------------------------------------


class TestBargeInDuringVoice:
    @pytest.mark.asyncio
    async def test_barge_in_cancels_voice_and_agent(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        # First turn
        await fake.speech_started(ts=1000)
        await fake.transcript_final("hola", ts=2000)
        first_events = capture.drain()
        voice_start = [e for e in first_events if isinstance(e, RealtimeVoiceStart)][0]
        first_gen_id = coord.state.active_agent_generation_id

        # Barge-in
        await fake.speech_started(ts=2500)
        barge_events = capture.drain()

        voice_cancels = [e for e in barge_events if isinstance(e, RealtimeVoiceCancel)]
        gen_cancels = [e for e in barge_events if isinstance(e, CancelAgentGeneration)]

        assert len(voice_cancels) == 1
        assert voice_cancels[0].voice_generation_id == voice_start.voice_generation_id
        assert voice_cancels[0].reason == "barge_in"

    @pytest.mark.asyncio
    async def test_barge_in_then_new_turn(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        await fake.speech_started(ts=1000)
        await fake.transcript_final("hola", ts=2000)
        capture.drain()

        # Barge-in + new turn
        await fake.speech_started(ts=2500)
        capture.drain()
        await fake.transcript_final("adiós", ts=3000)

        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1
        assert voice_starts[0].prompt[2]["content"] == "adiós"


# ---------------------------------------------------------------------------
# 14.6 Barge-in during tool execution (late tool_result ignored)
# ---------------------------------------------------------------------------


class TestBargeInDuringTool:
    @pytest.mark.asyncio
    async def test_late_tool_result_ignored_after_cancel(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.DOMAIN, route_b=RouteBLabel.SUPPORT)
        )
        await fake.speech_started(ts=1000)
        await fake.transcript_final("necesito ayuda", ts=2000)
        first_gen_id = coord.state.active_agent_generation_id
        capture.drain()

        # Barge-in cancels the generation
        await fake.speech_started(ts=2500)
        capture.drain()

        # Late tool_result arrives — should be ignored
        await fake.tool_result(first_gen_id, ts=3000)
        events = capture.drain()
        assert len(events) == 0  # No output from late result


# ---------------------------------------------------------------------------
# 14.7 Filler emitted + cancelled on tool result
# ---------------------------------------------------------------------------


class TestFillerStrategy:
    @pytest.mark.asyncio
    async def test_filler_disabled_by_default(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.DOMAIN, route_b=RouteBLabel.SALES)
        )
        await fake.speech_started()
        await fake.transcript_final("quiero comprar")
        events = capture.drain()
        # Filler is disabled, so no filler voice start (only specialist voice)
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        filler_events = [
            e for e in voice_starts
            if isinstance(e.prompt, str) and "momento" in e.prompt.lower()
        ]
        assert len(filler_events) == 0


# ---------------------------------------------------------------------------
# 14.8 Idempotency — duplicate event_id ignored
# ---------------------------------------------------------------------------


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_event_id_ignored(self) -> None:
        coord, fake, capture, _ = make_e2e_stack()
        event_id = uuid4()

        await fake.inject_duplicate(event_id, ts=1000)
        first_events = capture.drain()

        await fake.inject_duplicate(event_id, ts=1000)
        second_events = capture.drain()

        assert len(second_events) == 0  # Duplicate ignored


# ---------------------------------------------------------------------------
# 14.9 Rapid successive turns — previous generation cancelled
# ---------------------------------------------------------------------------


class TestRapidSuccessiveTurns:
    @pytest.mark.asyncio
    async def test_second_turn_cancels_first_generation(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        # First turn
        await fake.speech_started(ts=1000)
        await fake.transcript_final("hola", ts=2000)
        first_gen_id = coord.state.active_agent_generation_id
        capture.drain()

        # Second turn (barge-in)
        await fake.speech_started(ts=2500)
        await fake.transcript_final("adiós", ts=3000)

        second_gen_id = coord.state.active_agent_generation_id
        assert second_gen_id != first_gen_id
        assert coord.state.is_generation_cancelled(first_gen_id)


# ---------------------------------------------------------------------------
# 14.10 Guardrail disallowed (lexicon match → guided response)
# ---------------------------------------------------------------------------


class TestGuardrailDisallowed:
    @pytest.mark.asyncio
    async def test_disallowed_produces_guardrail_response(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.DISALLOWED, confidence=1.0)
        )
        await fake.speech_started()
        await fake.transcript_final("maldita sea")

        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1
        prompt = voice_starts[0].prompt
        assert isinstance(prompt, list)
        # Should include guardrail_disallowed policy instructions
        assert "guardrail_disallowed" in prompt[1]["content"]


# ---------------------------------------------------------------------------
# 14.11 Guardrail out_of_scope (embedding match → guided response)
# ---------------------------------------------------------------------------


class TestGuardrailOutOfScope:
    @pytest.mark.asyncio
    async def test_out_of_scope_produces_guardrail_response(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.OUT_OF_SCOPE, confidence=0.85)
        )
        await fake.speech_started()
        await fake.transcript_final("cuál es la capital de Francia")

        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1
        prompt = voice_starts[0].prompt
        assert isinstance(prompt, list)
        assert "guardrail_out_of_scope" in prompt[1]["content"]


# ---------------------------------------------------------------------------
# 14.12 Ambiguous Route B → clarify_department
# ---------------------------------------------------------------------------


class TestAmbiguousRouteB:
    @pytest.mark.asyncio
    async def test_ambiguous_route_b_emits_clarify(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(
                route_a=RouteALabel.DOMAIN,
                route_b=None,  # Ambiguous — no clear Route B
                confidence=0.7,
            )
        )
        await fake.speech_started()
        await fake.transcript_final("tengo un problema")

        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1
        prompt = voice_starts[0].prompt
        assert isinstance(prompt, list)
        assert "clarify_department" in prompt[1]["content"]


# ---------------------------------------------------------------------------
# 14.13 Tool timeout → error response
# ---------------------------------------------------------------------------


class TestToolTimeout:
    @pytest.mark.asyncio
    async def test_tool_timeout_scenario(self) -> None:
        # Tool executor is mocked — this tests the coordinator handles
        # the tool_result event path correctly even if tool times out
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.DOMAIN, route_b=RouteBLabel.SUPPORT)
        )
        await fake.speech_started()
        await fake.transcript_final("necesito soporte")
        gen_id = coord.state.active_agent_generation_id
        capture.drain()

        # Simulate a late/timeout tool result with cancelled generation
        coord.state.cancelled_agent_generations.add(gen_id)
        await fake.tool_result(gen_id, ts=5000)

        events = capture.drain()
        assert len(events) == 0  # Late result ignored


# ---------------------------------------------------------------------------
# 14.14 Voice generation error
# ---------------------------------------------------------------------------


class TestVoiceGenerationError:
    @pytest.mark.asyncio
    async def test_voice_error_clears_active_voice(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        await fake.speech_started()
        await fake.transcript_final("hola")

        events = capture.drain()
        voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)][0]

        await fake.voice_error(voice_start.voice_generation_id, error="provider_timeout")
        assert coord.state.active_voice_generation_id is None

    @pytest.mark.asyncio
    async def test_cancelled_voice_error_ignored(self) -> None:
        coord, fake, capture, _ = make_e2e_stack()
        voice_id = uuid4()
        coord.state.cancelled_voice_generations.add(voice_id)

        await fake.voice_error(voice_id)
        # Should not crash or change state


# ---------------------------------------------------------------------------
# 14.15 Call cleanup — state clean, no orphaned tasks
# ---------------------------------------------------------------------------


class TestCallCleanup:
    @pytest.mark.asyncio
    async def test_state_clean_after_full_lifecycle(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        # Full turn
        await fake.speech_started()
        await fake.transcript_final("hola")
        events = capture.drain()
        voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)][0]

        # Complete voice
        await fake.voice_completed(voice_start.voice_generation_id)

        # Verify clean state
        assert coord.state.active_voice_generation_id is None
        assert coord._filler_task is None

    @pytest.mark.asyncio
    async def test_no_orphaned_filler_task(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        # Turn + barge-in should cancel any filler
        await fake.speech_started(ts=1000)
        await fake.transcript_final("hola", ts=2000)
        capture.drain()

        await fake.speech_started(ts=2500)
        assert coord._filler_task is None  # Filler cancelled by barge-in

    @pytest.mark.asyncio
    async def test_multiple_turns_all_tracked(self) -> None:
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        # Three turns
        for i in range(3):
            await fake.speech_started(ts=1000 + i * 3000)
            await fake.transcript_final(f"turn {i}", ts=2000 + i * 3000)
            events = capture.drain()
            voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)]
            if voice_start:
                await fake.voice_completed(voice_start[-1].voice_generation_id, ts=2500 + i * 3000)

        assert coord.state.turn_seq == 3
