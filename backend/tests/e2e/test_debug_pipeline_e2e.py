"""E2E tests for the debug event pipeline through the real Coordinator.

These tests exercise the full event flow: FakeRealtime injects events into
the Coordinator, which processes them through its real handlers, and the
DebugCapture collects the resulting debug_event messages. This verifies that
debug events are emitted at the correct points with correct timing data.
"""

from __future__ import annotations

import pytest

from src.voice_runtime.events import RealtimeVoiceStart

from .conftest import make_debug_e2e_stack, make_e2e_stack


# ---------------------------------------------------------------------------
# Direct route — full turn lifecycle debug events
# ---------------------------------------------------------------------------


class TestDirectRouteDebugFlow:
    @pytest.mark.asyncio
    async def test_direct_turn_emits_speech_and_committed_stages(self) -> None:
        """speech_started + speech_stopped + audio_committed produce debug stages."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)

        stages = debug.stages()
        assert "speech_start" in stages
        assert "speech_stop" in stages
        assert "audio_committed" in stages

    @pytest.mark.asyncio
    async def test_direct_turn_emits_prompt_sent_after_audio_committed(self) -> None:
        """audio_committed triggers routing which emits prompt_sent."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        stages = debug.stages()
        assert "prompt_sent" in stages
        committed_idx = stages.index("audio_committed")
        prompt_idx = stages.index("prompt_sent")
        assert prompt_idx > committed_idx

    @pytest.mark.asyncio
    async def test_direct_turn_consistent_turn_id(self) -> None:
        """All debug_event messages in a turn share the same turn_id."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        turn_ids = {str(e.get("turn_id")) for e in debug.debug_events}
        turn_ids.discard("")
        assert len(turn_ids) == 1, f"Expected 1 turn_id, got {turn_ids}"

    @pytest.mark.asyncio
    async def test_direct_turn_timing_monotonic(self) -> None:
        """total_ms is monotonically non-decreasing within a turn."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        totals = [int(e.get("total_ms", 0)) for e in debug.debug_events]
        for i in range(1, len(totals)):
            assert totals[i] >= totals[i - 1], (
                f"total_ms not monotonic: {totals}"
            )

    @pytest.mark.asyncio
    async def test_voice_completed_emits_generation_finish(self) -> None:
        """voice_generation_completed emits generation_finish debug event."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        events = capture.drain()
        voice_start = [e for e in events if isinstance(e, RealtimeVoiceStart)][0]

        await fake.voice_completed(voice_start.voice_generation_id, ts=3000)

        stages = debug.stages()
        assert "route_result" in stages  # Retroactive for direct route
        # generation_start no longer emitted from backend (now audio_playback_start from frontend)
        assert "generation_finish" in stages  # Fallback when no audio_playback_end from frontend


# ---------------------------------------------------------------------------
# Delegate route — specialist sub-flow debug events
# ---------------------------------------------------------------------------


class TestDelegateRouteDebugFlow:
    @pytest.mark.asyncio
    async def test_delegate_emits_route_result_with_department(self) -> None:
        """model_router_action emits route_result with label and route_type=delegate."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        await fake.model_router_action(department="billing", summary="invoice", ts=2500)

        route_events = debug.by_stage("route_result")
        assert len(route_events) >= 1
        route = route_events[0]
        assert route["label"] == "billing"
        assert route["route_type"] == "delegate"

    @pytest.mark.asyncio
    async def test_delegate_emits_fill_silence(self) -> None:
        """Delegate route emits fill_silence when Coordinator launches silence-filling."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        await fake.model_router_action(department="sales", summary="purchase", ts=2500)

        stages = debug.stages()
        assert "fill_silence" in stages

    @pytest.mark.asyncio
    async def test_delegate_emits_specialist_stages(self) -> None:
        """Delegate route emits specialist_sent and specialist_ready."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        await fake.model_router_action(department="support", summary="help", ts=2500)

        stages = debug.stages()
        assert "specialist_sent" in stages
        assert "specialist_ready" in stages

    @pytest.mark.asyncio
    async def test_delegate_emits_generation_start(self) -> None:
        """Delegate route emits generation_start when specialist voice begins."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        await fake.model_router_action(department="billing", summary="question", ts=2500)

        stages = debug.stages()
        assert "generation_start" in stages

    @pytest.mark.asyncio
    async def test_delegate_full_specialist_flow_completes(self) -> None:
        """Full delegate flow: route_result → fill_silence → specialist_* → gen_start → gen_finish."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        await fake.model_router_action(department="retention", summary="cancel", ts=2500)
        specialist_events = capture.drain()
        specialist_voice = [e for e in specialist_events if isinstance(e, RealtimeVoiceStart)][-1]

        await fake.voice_completed(specialist_voice.voice_generation_id, ts=4000)

        stages = debug.stages()
        assert "route_result" in stages
        assert "fill_silence" in stages
        assert "specialist_sent" in stages
        assert "specialist_ready" in stages
        assert "generation_start" in stages
        assert "generation_finish" in stages

        # Verify ordering
        route_idx = stages.index("route_result")
        specialist_idx = stages.index("specialist_sent")
        gen_finish_idx = stages.index("generation_finish")
        assert specialist_idx > route_idx
        assert gen_finish_idx > specialist_idx


# ---------------------------------------------------------------------------
# Barge-in debug events
# ---------------------------------------------------------------------------


class TestBargeInDebugFlow:
    @pytest.mark.asyncio
    async def test_barge_in_emits_debug_event(self) -> None:
        """Barge-in during generation emits barge_in debug stage."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        # Barge-in
        await fake.speech_started(ts=2000)

        stages = debug.stages()
        assert "barge_in" in stages

    @pytest.mark.asyncio
    async def test_barge_in_emitted_in_new_turn(self) -> None:
        """barge_in is emitted after speech_start resets turn_id, so it belongs to the new turn."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        first_turn_id = str(debug.debug_events[0].get("turn_id"))

        await fake.speech_started(ts=2000)

        barge_events = debug.by_stage("barge_in")
        assert len(barge_events) == 1
        # barge_in is emitted AFTER speech_start resets turn_id → new turn
        new_speech_starts = [
            e for e in debug.debug_events
            if e.get("stage") == "speech_start" and str(e.get("turn_id")) != first_turn_id
        ]
        assert len(new_speech_starts) == 1
        new_turn_id = str(new_speech_starts[0]["turn_id"])
        assert str(barge_events[0]["turn_id"]) == new_turn_id


# ---------------------------------------------------------------------------
# Debug disabled — zero overhead
# ---------------------------------------------------------------------------


class TestDebugDisabled:
    @pytest.mark.asyncio
    async def test_no_debug_events_when_disabled(self) -> None:
        """No debug_event messages emitted when debug is off (default)."""
        coord, fake, capture = make_e2e_stack()
        received: list[dict] = []

        async def debug_cb(event: dict) -> None:
            received.append(event)

        coord.set_debug_callback(debug_cb)
        # NOT calling set_debug_enabled(True)

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        # _send_debug is gated by _debug_enabled, so no debug_event messages
        debug_events = [e for e in received if e.get("type") == "debug_event"]
        assert len(debug_events) == 0

    @pytest.mark.asyncio
    async def test_disable_mid_session_stops_debug_events(self) -> None:
        """Disabling debug mid-session stops further debug_event messages."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        count_after_start = len(debug.debug_events)
        assert count_after_start > 0

        # Disable debug
        coord.set_debug_enabled(False)

        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        # No new debug_event messages after disabling
        assert len(debug.debug_events) == count_after_start


# ---------------------------------------------------------------------------
# Multi-turn debug events
# ---------------------------------------------------------------------------


class TestMultiTurnDebug:
    @pytest.mark.asyncio
    async def test_two_turns_have_different_turn_ids(self) -> None:
        """Each turn gets a unique turn_id for grouping."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        # Turn 1
        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        events_t1 = capture.drain()
        voice_start = [e for e in events_t1 if isinstance(e, RealtimeVoiceStart)][0]
        await fake.voice_completed(voice_start.voice_generation_id, ts=3000)

        turn1_ids = {str(e["turn_id"]) for e in debug.debug_events}

        # Turn 2
        await fake.speech_started(ts=4000)
        await fake.speech_stopped(ts=4600)
        await fake.audio_committed(ts=4620)
        capture.drain()

        all_ids = {str(e["turn_id"]) for e in debug.debug_events}
        assert len(all_ids) >= 2

    @pytest.mark.asyncio
    async def test_response_created_emits_model_processing(self) -> None:
        """response_created event from bridge emits model_processing debug stage."""
        coord, fake, capture, debug = make_debug_e2e_stack()

        await fake.speech_started(ts=1000)
        await fake.speech_stopped(ts=1600)
        await fake.audio_committed(ts=1620)
        capture.drain()

        await fake.response_created(ts=2800)

        stages = debug.stages()
        assert "model_processing" in stages
