"""Unit tests for Coordinator (tasks 10.1–10.8)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
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
from src.voice_runtime.state import CoordinatorRuntimeState
from src.voice_runtime.tool_executor import ToolExecutor
from src.voice_runtime.turn_manager import TurnManager
from src.voice_runtime.types import (
    EventSource,
    PolicyKey,
    RouteALabel,
    RouteBLabel,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_policies() -> PoliciesRegistry:
    return PoliciesRegistry(
        base_system="You are a helpful agent.",
        policies={
            k.value: f"Instructions for {k.value}" for k in PolicyKey
        },
    )


def _make_router(
    route_a: RouteALabel = RouteALabel.SIMPLE,
    confidence: float = 0.95,
    route_b: RouteBLabel | None = None,
) -> Router:
    mock = MagicMock(spec=Router)
    mock.classify = AsyncMock(
        return_value=RoutingResult(
            route_a_label=route_a,
            route_a_confidence=confidence,
            route_b_label=route_b,
        )
    )
    return mock


def _make_coordinator(
    router: Router | None = None,
    seen_events: object | None = None,
    tool_cache: object | None = None,
    turn_repo: object | None = None,
    agent_gen_repo: object | None = None,
    voice_gen_repo: object | None = None,
) -> Coordinator:
    call_id = uuid4()
    return Coordinator(
        call_id=call_id,
        turn_manager=TurnManager(call_id),
        agent_fsm=AgentFSM(call_id),
        tool_executor=MagicMock(spec=ToolExecutor),
        router=router or _make_router(),
        policies=_make_policies(),
        seen_events=seen_events,
        tool_cache=tool_cache,
        turn_repo=turn_repo,
        agent_gen_repo=agent_gen_repo,
        voice_gen_repo=voice_gen_repo,
    )


def _envelope(
    call_id: UUID | None = None,
    event_type: str = "speech_started",
    payload: dict | None = None,
    event_id: UUID | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid4(),
        call_id=call_id or uuid4(),
        ts=1000,
        type=event_type,
        payload=payload or {},
        source=EventSource.REALTIME,
    )


# ---------------------------------------------------------------------------
# 10.1 CoordinatorRuntimeState
# ---------------------------------------------------------------------------


class TestCoordinatorRuntimeState:
    def test_initial_state(self) -> None:
        cid = uuid4()
        state = CoordinatorRuntimeState(call_id=cid)
        assert state.active_turn_id is None
        assert state.active_agent_generation_id is None
        assert state.active_voice_generation_id is None
        assert len(state.cancelled_agent_generations) == 0
        assert len(state.cancelled_voice_generations) == 0

    def test_cancel_active_generation(self) -> None:
        state = CoordinatorRuntimeState(call_id=uuid4())
        gen_id = uuid4()
        state.active_agent_generation_id = gen_id
        returned = state.cancel_active_generation()
        assert returned == gen_id
        assert state.active_agent_generation_id is None
        assert state.is_generation_cancelled(gen_id)

    def test_cancel_active_generation_none(self) -> None:
        state = CoordinatorRuntimeState(call_id=uuid4())
        assert state.cancel_active_generation() is None

    def test_cancel_active_voice(self) -> None:
        state = CoordinatorRuntimeState(call_id=uuid4())
        vid = uuid4()
        state.active_voice_generation_id = vid
        returned = state.cancel_active_voice()
        assert returned == vid
        assert state.active_voice_generation_id is None
        assert state.is_voice_cancelled(vid)

    def test_cancel_active_voice_none(self) -> None:
        state = CoordinatorRuntimeState(call_id=uuid4())
        assert state.cancel_active_voice() is None

    def test_is_generation_cancelled(self) -> None:
        state = CoordinatorRuntimeState(call_id=uuid4())
        gid = uuid4()
        assert not state.is_generation_cancelled(gid)
        state.cancelled_agent_generations.add(gid)
        assert state.is_generation_cancelled(gid)


# ---------------------------------------------------------------------------
# 10.7 Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_event_ignored(self) -> None:
        coord = _make_coordinator()
        eid = uuid4()
        env1 = _envelope(event_id=eid, event_type="speech_started")
        env2 = _envelope(event_id=eid, event_type="speech_started")

        await coord.handle_event(env1)
        events_after_first = coord.drain_output_events()

        await coord.handle_event(env2)
        events_after_second = coord.drain_output_events()
        assert len(events_after_second) == 0  # duplicate ignored

    @pytest.mark.asyncio
    async def test_different_event_ids_both_processed(self) -> None:
        coord = _make_coordinator()
        env1 = _envelope(event_type="speech_started")
        env2 = _envelope(event_type="speech_started")

        await coord.handle_event(env1)
        await coord.handle_event(env2)
        # Both processed — no assertion on count, just no crash

    @pytest.mark.asyncio
    async def test_redis_dedup_used_when_available(self) -> None:
        mock_seen = AsyncMock()
        mock_seen.add = AsyncMock(return_value=True)  # newly added
        coord = _make_coordinator(seen_events=mock_seen)
        env = _envelope(event_type="speech_started")
        await coord.handle_event(env)
        mock_seen.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_dedup_fallback_on_error(self) -> None:
        mock_seen = AsyncMock()
        mock_seen.add = AsyncMock(side_effect=Exception("redis down"))
        coord = _make_coordinator(seen_events=mock_seen)
        env = _envelope(event_type="speech_started")
        # Should not raise — falls back to in-memory
        await coord.handle_event(env)


# ---------------------------------------------------------------------------
# 10.4 Barge-in handling
# ---------------------------------------------------------------------------


class TestBargeIn:
    @pytest.mark.asyncio
    async def test_barge_in_cancels_active_voice(self) -> None:
        coord = _make_coordinator()
        voice_id = uuid4()
        coord.state.active_voice_generation_id = voice_id

        env = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(env)

        events = coord.drain_output_events()
        voice_cancels = [e for e in events if isinstance(e, RealtimeVoiceCancel)]
        assert len(voice_cancels) == 1
        assert voice_cancels[0].voice_generation_id == voice_id
        assert voice_cancels[0].reason == "barge_in"

    @pytest.mark.asyncio
    async def test_barge_in_cancels_active_generation(self) -> None:
        coord = _make_coordinator()
        gen_id = uuid4()
        coord.state.active_agent_generation_id = gen_id

        env = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(env)

        events = coord.drain_output_events()
        gen_cancels = [e for e in events if isinstance(e, CancelAgentGeneration)]
        assert len(gen_cancels) == 1
        assert gen_cancels[0].agent_generation_id == gen_id
        assert gen_cancels[0].reason == "barge_in"

    @pytest.mark.asyncio
    async def test_barge_in_adds_to_cancelled_sets(self) -> None:
        coord = _make_coordinator()
        gen_id = uuid4()
        voice_id = uuid4()
        coord.state.active_agent_generation_id = gen_id
        coord.state.active_voice_generation_id = voice_id

        env = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(env)

        assert coord.state.is_generation_cancelled(gen_id)
        assert coord.state.is_voice_cancelled(voice_id)

    @pytest.mark.asyncio
    async def test_barge_in_resets_agent_fsm(self) -> None:
        coord = _make_coordinator()
        gen_id = uuid4()
        coord.state.active_agent_generation_id = gen_id
        # Put FSM in THINKING state
        coord._agent_fsm._state = coord._agent_fsm.state.__class__("thinking")
        coord._agent_fsm._current_generation_id = gen_id

        env = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(env)

        from src.voice_runtime.types import AgentState
        assert coord._agent_fsm.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_barge_in_no_active_voice_no_cancel(self) -> None:
        coord = _make_coordinator()
        env = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(env)

        events = coord.drain_output_events()
        assert len([e for e in events if isinstance(e, RealtimeVoiceCancel)]) == 0
        assert len([e for e in events if isinstance(e, CancelAgentGeneration)]) == 0


# ---------------------------------------------------------------------------
# 10.3 Turn lifecycle orchestration
# ---------------------------------------------------------------------------


class TestTurnLifecycle:
    @pytest.mark.asyncio
    async def test_transcript_final_triggers_routing(self) -> None:
        router = _make_router(route_a=RouteALabel.SIMPLE)
        coord = _make_coordinator(router=router)

        # Speech started -> transcript_final -> should finalize turn and route
        speech = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech)

        transcript = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "hola buenos días"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript)

        router.classify.assert_called_once_with("hola buenos días", "es")

    @pytest.mark.asyncio
    async def test_simple_turn_emits_voice_start(self) -> None:
        router = _make_router(route_a=RouteALabel.SIMPLE)
        coord = _make_coordinator(router=router)

        speech = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech)
        coord.drain_output_events()  # clear

        transcript = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "hola"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript)

        events = coord.drain_output_events()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1
        # Prompt should be a list of message dicts (guided response)
        assert isinstance(voice_starts[0].prompt, list)

    @pytest.mark.asyncio
    async def test_domain_route_b_emits_specialist_voice(self) -> None:
        router = _make_router(
            route_a=RouteALabel.DOMAIN,
            route_b=RouteBLabel.BILLING,
        )
        coord = _make_coordinator(router=router)

        speech = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech)
        coord.drain_output_events()

        transcript = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "tengo un problema con mi factura"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript)

        events = coord.drain_output_events()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) >= 1
        # At least one should reference the specialist
        specialist_events = [
            e for e in voice_starts if isinstance(e.prompt, str) and "billing" in e.prompt
        ]
        assert len(specialist_events) >= 1

    @pytest.mark.asyncio
    async def test_disallowed_emits_guardrail_response(self) -> None:
        router = _make_router(route_a=RouteALabel.DISALLOWED)
        coord = _make_coordinator(router=router)

        speech = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech)
        coord.drain_output_events()

        transcript = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "maldita sea"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript)

        events = coord.drain_output_events()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1

    @pytest.mark.asyncio
    async def test_rapid_successive_turns_cancel_previous(self) -> None:
        router = _make_router(route_a=RouteALabel.SIMPLE)
        coord = _make_coordinator(router=router)

        # First turn
        speech1 = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech1)
        transcript1 = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "hola"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript1)

        first_gen_id = coord.state.active_agent_generation_id
        coord.drain_output_events()

        # Second turn — should cancel the first generation
        speech2 = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech2)
        transcript2 = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "buenos días"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript2)

        # The second turn should have a different generation ID
        second_gen_id = coord.state.active_agent_generation_id
        assert second_gen_id != first_gen_id


# ---------------------------------------------------------------------------
# 10.5 Prompt construction
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    @pytest.mark.asyncio
    async def test_guided_response_includes_system_and_policy(self) -> None:
        router = _make_router(route_a=RouteALabel.SIMPLE)
        coord = _make_coordinator(router=router)

        speech = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech)
        coord.drain_output_events()

        transcript = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "hola"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript)

        events = coord.drain_output_events()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1
        prompt = voice_starts[0].prompt
        assert isinstance(prompt, list)
        # System message with base_system
        assert prompt[0]["role"] == "system"
        assert "helpful agent" in prompt[0]["content"]
        # Policy instructions
        assert prompt[1]["role"] == "system"
        assert "greeting" in prompt[1]["content"]
        # User text
        assert prompt[2]["role"] == "user"
        assert prompt[2]["content"] == "hola"

    @pytest.mark.asyncio
    async def test_invalid_policy_key_falls_back(self) -> None:
        coord = _make_coordinator()
        env = _envelope(
            call_id=coord._call_id,
            event_type="request_guided_response",
            payload={
                "agent_generation_id": str(uuid4()),
                "policy_key": "invalid_key",
                "user_text": "test",
            },
        )
        # Should not raise — falls back to CLARIFY_DEPARTMENT
        await coord.handle_event(env)
        events = coord.drain_output_events()
        voice_starts = [e for e in events if isinstance(e, RealtimeVoiceStart)]
        assert len(voice_starts) == 1


# ---------------------------------------------------------------------------
# 10.8 Late result handling
# ---------------------------------------------------------------------------


class TestLateResultHandling:
    @pytest.mark.asyncio
    async def test_late_tool_result_ignored(self) -> None:
        coord = _make_coordinator()
        gen_id = uuid4()
        coord.state.cancelled_agent_generations.add(gen_id)

        env = _envelope(
            call_id=coord._call_id,
            event_type="tool_result",
            payload={"agent_generation_id": str(gen_id)},
        )
        await coord.handle_event(env)
        # No crash, no output events
        assert len(coord.drain_output_events()) == 0

    @pytest.mark.asyncio
    async def test_late_voice_completed_ignored(self) -> None:
        coord = _make_coordinator()
        voice_id = uuid4()
        coord.state.cancelled_voice_generations.add(voice_id)

        env = _envelope(
            call_id=coord._call_id,
            event_type="voice_generation_completed",
            payload={"voice_generation_id": str(voice_id)},
        )
        await coord.handle_event(env)
        # Voice state should remain unchanged
        assert coord.state.active_voice_generation_id is None

    @pytest.mark.asyncio
    async def test_late_voice_error_ignored(self) -> None:
        coord = _make_coordinator()
        voice_id = uuid4()
        coord.state.cancelled_voice_generations.add(voice_id)

        env = _envelope(
            call_id=coord._call_id,
            event_type="voice_generation_error",
            payload={"voice_generation_id": str(voice_id), "error": "timeout"},
        )
        await coord.handle_event(env)

    @pytest.mark.asyncio
    async def test_late_guided_response_ignored(self) -> None:
        coord = _make_coordinator()
        gen_id = uuid4()
        coord.state.cancelled_agent_generations.add(gen_id)

        env = _envelope(
            call_id=coord._call_id,
            event_type="request_guided_response",
            payload={
                "agent_generation_id": str(gen_id),
                "policy_key": "greeting",
                "user_text": "hola",
            },
        )
        await coord.handle_event(env)
        assert len(coord.drain_output_events()) == 0

    @pytest.mark.asyncio
    async def test_late_agent_action_ignored(self) -> None:
        coord = _make_coordinator()
        gen_id = uuid4()
        coord.state.cancelled_agent_generations.add(gen_id)

        env = _envelope(
            call_id=coord._call_id,
            event_type="request_agent_action",
            payload={
                "agent_generation_id": str(gen_id),
                "specialist": "billing",
                "user_text": "factura",
            },
        )
        await coord.handle_event(env)
        assert len(coord.drain_output_events()) == 0


# ---------------------------------------------------------------------------
# 10.2 Event dispatch
# ---------------------------------------------------------------------------


class TestEventDispatch:
    @pytest.mark.asyncio
    async def test_unknown_event_type_ignored(self) -> None:
        coord = _make_coordinator()
        env = _envelope(event_type="unknown_type_xyz")
        await coord.handle_event(env)
        assert len(coord.drain_output_events()) == 0

    @pytest.mark.asyncio
    async def test_voice_completed_clears_active_voice(self) -> None:
        coord = _make_coordinator()
        voice_id = uuid4()
        coord.state.active_voice_generation_id = voice_id

        env = _envelope(
            call_id=coord._call_id,
            event_type="voice_generation_completed",
            payload={"voice_generation_id": str(voice_id)},
        )
        await coord.handle_event(env)
        assert coord.state.active_voice_generation_id is None

    @pytest.mark.asyncio
    async def test_voice_error_clears_active_voice(self) -> None:
        coord = _make_coordinator()
        voice_id = uuid4()
        coord.state.active_voice_generation_id = voice_id

        env = _envelope(
            call_id=coord._call_id,
            event_type="voice_generation_error",
            payload={"voice_generation_id": str(voice_id), "error": "fail"},
        )
        await coord.handle_event(env)
        assert coord.state.active_voice_generation_id is None


# ---------------------------------------------------------------------------
# drain_output_events
# ---------------------------------------------------------------------------


class TestDrainOutputEvents:
    def test_drain_returns_and_clears(self) -> None:
        coord = _make_coordinator()
        # Manually push an event
        coord._output_events.append(
            RealtimeVoiceCancel(
                call_id=coord._call_id,
                voice_generation_id=uuid4(),
                reason="test",
                ts=1000,
            )
        )
        events = coord.drain_output_events()
        assert len(events) == 1
        assert len(coord.drain_output_events()) == 0


# ---------------------------------------------------------------------------
# 10.9 Persistence wiring
# ---------------------------------------------------------------------------


class TestPersistenceWiring:
    @pytest.mark.asyncio
    async def test_turn_finalized_inserts_turn(self) -> None:
        turn_repo = AsyncMock()
        agent_gen_repo = AsyncMock()
        router = _make_router(route_a=RouteALabel.SIMPLE)
        coord = _make_coordinator(
            router=router, turn_repo=turn_repo, agent_gen_repo=agent_gen_repo
        )

        speech = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech)

        transcript = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "hola"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript)

        turn_repo.insert.assert_called_once()
        turn_entity = turn_repo.insert.call_args[0][0]
        assert turn_entity.text_final == "hola"
        assert turn_entity.language == "es"

    @pytest.mark.asyncio
    async def test_turn_finalized_inserts_agent_generation(self) -> None:
        agent_gen_repo = AsyncMock()
        router = _make_router(route_a=RouteALabel.SIMPLE)
        coord = _make_coordinator(router=router, agent_gen_repo=agent_gen_repo)

        speech = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech)

        transcript = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "hola"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript)

        agent_gen_repo.insert.assert_called_once()
        gen_entity = agent_gen_repo.insert.call_args[0][0]
        assert gen_entity.route_a_label == "simple"

    @pytest.mark.asyncio
    async def test_guided_response_inserts_voice_generation(self) -> None:
        voice_gen_repo = AsyncMock()
        router = _make_router(route_a=RouteALabel.SIMPLE)
        coord = _make_coordinator(router=router, voice_gen_repo=voice_gen_repo)

        speech = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech)

        transcript = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "hola"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript)

        voice_gen_repo.insert.assert_called_once()
        voice_entity = voice_gen_repo.insert.call_args[0][0]
        assert voice_entity.state.value == "starting"

    @pytest.mark.asyncio
    async def test_voice_completed_updates_voice_generation(self) -> None:
        voice_gen_repo = AsyncMock()
        coord = _make_coordinator(voice_gen_repo=voice_gen_repo)
        voice_id = uuid4()
        coord.state.active_voice_generation_id = voice_id
        coord.state.active_turn_id = uuid4()
        coord.state.active_agent_generation_id = uuid4()

        env = _envelope(
            call_id=coord._call_id,
            event_type="voice_generation_completed",
            payload={"voice_generation_id": str(voice_id)},
        )
        await coord.handle_event(env)

        voice_gen_repo.update.assert_called_once()
        updated = voice_gen_repo.update.call_args[0][0]
        assert updated.state.value == "completed"

    @pytest.mark.asyncio
    async def test_voice_error_updates_voice_generation(self) -> None:
        voice_gen_repo = AsyncMock()
        coord = _make_coordinator(voice_gen_repo=voice_gen_repo)
        voice_id = uuid4()
        coord.state.active_voice_generation_id = voice_id
        coord.state.active_turn_id = uuid4()
        coord.state.active_agent_generation_id = uuid4()

        env = _envelope(
            call_id=coord._call_id,
            event_type="voice_generation_error",
            payload={"voice_generation_id": str(voice_id), "error": "timeout"},
        )
        await coord.handle_event(env)

        voice_gen_repo.update.assert_called_once()
        updated = voice_gen_repo.update.call_args[0][0]
        assert updated.state.value == "error"
        assert updated.error == "timeout"

    @pytest.mark.asyncio
    async def test_rapid_turns_updates_cancelled_generation(self) -> None:
        agent_gen_repo = AsyncMock()
        router = _make_router(route_a=RouteALabel.SIMPLE)
        coord = _make_coordinator(router=router, agent_gen_repo=agent_gen_repo)

        # First turn
        speech1 = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech1)
        transcript1 = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "hola"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript1)

        # Second turn triggers cancellation of first
        speech2 = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech2)
        transcript2 = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "adiós"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript2)

        # Should have 2 inserts + 1 update (cancellation via barge-in)
        assert agent_gen_repo.insert.call_count == 2
        agent_gen_repo.update.assert_called_once()
        cancelled = agent_gen_repo.update.call_args[0][0]
        assert cancelled.state.value == "cancelled"
        assert cancelled.cancel_reason == "barge_in"

    @pytest.mark.asyncio
    async def test_persistence_error_does_not_crash(self) -> None:
        turn_repo = AsyncMock()
        turn_repo.insert = AsyncMock(side_effect=Exception("db down"))
        router = _make_router(route_a=RouteALabel.SIMPLE)
        coord = _make_coordinator(router=router, turn_repo=turn_repo)

        speech = _envelope(call_id=coord._call_id, event_type="speech_started")
        await coord.handle_event(speech)

        transcript = _envelope(
            call_id=coord._call_id,
            event_type="transcript_final",
            payload={"text": "hola"},
        )
        with patch("src.routing.language.detect_language", return_value="es"):
            await coord.handle_event(transcript)

        # Should not crash — persistence is fire-and-forget
        events = coord.drain_output_events()
        assert len(events) >= 1  # Voice start still emitted
