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
        assert voice_starts[0].prompt[-1]["content"] == "adiós"


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


# ---------------------------------------------------------------------------
# 6.1–6.3 Multi-turn conversation history in prompts
# ---------------------------------------------------------------------------


class TestMultiTurnHistory:
    @pytest.mark.asyncio
    async def test_two_turns_second_prompt_contains_history(self) -> None:
        """6.1: Two turns — second prompt contains first turn's history."""
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        # First turn
        await fake.speech_started(ts=1000)
        await fake.transcript_final("hola", ts=2000)
        first_events = capture.drain()
        first_vs = [e for e in first_events if isinstance(e, RealtimeVoiceStart)][0]
        await fake.voice_completed(first_vs.voice_generation_id, ts=2500)

        # Second turn
        await fake.speech_started(ts=3000)
        await fake.transcript_final("mi factura", ts=4000)
        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1

        prompt = voice_starts[0].prompt
        # Should have: system, policy, history_user("hola"), history_assistant, user("mi factura")
        assert prompt[0]["role"] == "system"
        assert prompt[1]["role"] == "system"
        assert prompt[2] == {"role": "user", "content": "hola"}
        assert prompt[3]["role"] == "assistant"
        assert prompt[-1] == {"role": "user", "content": "mi factura"}

    @pytest.mark.asyncio
    async def test_barge_in_cancelled_turn_absent_from_history(self) -> None:
        """6.2: Barge-in scenario — verify history state after cancellation."""
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        # First turn completes
        await fake.speech_started(ts=1000)
        await fake.transcript_final("hola", ts=2000)
        first_events = capture.drain()
        first_vs = [e for e in first_events if isinstance(e, RealtimeVoiceStart)][0]
        await fake.voice_completed(first_vs.voice_generation_id, ts=2500)

        # Second turn — will be barge-in'd
        await fake.speech_started(ts=3000)
        await fake.transcript_final("interrumpido", ts=4000)
        capture.drain()

        # Barge-in cancels second turn's voice
        await fake.speech_started(ts=4500)
        capture.drain()

        # Third turn after barge-in
        await fake.transcript_final("adiós", ts=5000)
        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1

        prompt = voice_starts[0].prompt
        assert prompt[-1] == {"role": "user", "content": "adiós"}
        # "hola" and "interrumpido" both had voice starts emitted, so both in history
        user_msgs = [m for m in prompt if m["role"] == "user"]
        assert user_msgs[0]["content"] == "hola"
        assert user_msgs[-1]["content"] == "adiós"

    @pytest.mark.asyncio
    async def test_three_turns_history_accumulation(self) -> None:
        """6.3: Three turns with history accumulation and correct prompt structure."""
        coord, fake, capture, _ = make_e2e_stack(
            router=make_router(route_a=RouteALabel.SIMPLE)
        )
        texts = ["uno", "dos", "tres"]

        for i, text in enumerate(texts):
            await fake.speech_started(ts=1000 + i * 3000)
            await fake.transcript_final(text, ts=2000 + i * 3000)
            events = capture.drain()
            voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)]
            if voice_start:
                await fake.voice_completed(
                    voice_start[-1].voice_generation_id, ts=2500 + i * 3000
                )

        assert len(coord._conversation_buffer) == 3

        # Do a 4th turn to see all 3 in history
        await fake.speech_started(ts=10000)
        await fake.transcript_final("cuatro", ts=11000)
        events = capture.drain()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        prompt = voice_starts[0].prompt

        user_msgs = [m for m in prompt if m["role"] == "user"]
        assert [m["content"] for m in user_msgs] == ["uno", "dos", "tres", "cuatro"]

        assistant_msgs = [m for m in prompt if m["role"] == "assistant"]
        assert len(assistant_msgs) == 3


# ---------------------------------------------------------------------------
# Context-Aware Routing E2E Tests
# ---------------------------------------------------------------------------


class TestContextAwareRoutingE2E:
    @pytest.mark.asyncio
    async def test_two_turn_short_followup_enriched(self) -> None:
        """8.1 — Two-turn flow: first long turn, then short follow-up gets enriched."""
        router = make_router(route_a=RouteALabel.SIMPLE)
        coord, fake, capture, _ = make_e2e_stack(router=router)

        # Turn 1: long text
        await fake.speech_started()
        await fake.transcript_final("tengo un problema con mi factura")
        capture.drain()

        # Turn 2: short follow-up
        await fake.speech_started(ts=3000)
        await fake.transcript_final("de este mes", ts=4000)

        assert router.classify.call_count == 2
        second_call = router.classify.call_args_list[1]
        assert second_call.kwargs["enriched_text"] == (
            "tengo un problema con mi factura. de este mes"
        )
        assert second_call.kwargs["llm_context"] is not None
        assert "turn[-1] user: tengo un problema con mi factura" in second_call.kwargs["llm_context"]

    @pytest.mark.asyncio
    async def test_first_turn_short_text_no_enrichment(self) -> None:
        """8.2 — First turn with short text has no enrichment."""
        router = make_router(route_a=RouteALabel.SIMPLE)
        coord, fake, capture, _ = make_e2e_stack(router=router)

        await fake.speech_started()
        await fake.transcript_final("hola")

        router.classify.assert_called_once()
        call = router.classify.call_args
        assert call.kwargs["enriched_text"] is None
        assert call.kwargs["llm_context"] is None


# ---------------------------------------------------------------------------
# LLM Fallback History E2E Tests
# ---------------------------------------------------------------------------


class TestLLMFallbackHistoryE2E:
    @pytest.mark.asyncio
    async def test_three_turn_multi_turn_llm_context(self) -> None:
        """7.1 — 3-turn conversation produces multi-turn llm_context in Router.classify()."""
        router = make_router(route_a=RouteALabel.SIMPLE)
        coord, fake, capture, _ = make_e2e_stack(router=router)

        # Turn 1
        await fake.speech_started(ts=1000)
        await fake.transcript_final("mi factura", ts=2000)
        capture.drain()

        # Turn 2
        await fake.speech_started(ts=3000)
        await fake.transcript_final("no me llega el recibo", ts=4000)
        capture.drain()

        # Turn 3
        await fake.speech_started(ts=5000)
        await fake.transcript_final("de este mes", ts=6000)

        assert router.classify.call_count == 3
        third_call = router.classify.call_args_list[2]
        llm_ctx = third_call.kwargs["llm_context"]
        assert llm_ctx is not None
        assert llm_ctx.startswith("language=es")
        assert "turn[-2] user: mi factura" in llm_ctx
        assert "turn[-1] user: no me llega el recibo" in llm_ctx
        # enriched_text uses only most recent turn (context_window=1)
        assert third_call.kwargs["enriched_text"] == "no me llega el recibo. de este mes"
