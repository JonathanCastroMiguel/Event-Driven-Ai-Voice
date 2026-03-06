from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Coroutine
from uuid import UUID, uuid4

import time

import structlog

from src.infrastructure.redis_client import TTLMap, TTLSet
from src.infrastructure.telemetry import (
    BARGE_IN_TOTAL,
    FILLER_EMITTED_TOTAL,
    ROUTE_A_CONFIDENCE,
    ROUTE_B_CONFIDENCE,
    TURN_LATENCY,
    get_tracer,
)
from src.routing.context import RoutingContextBuilder
from src.routing.policies import PoliciesRegistry
from src.routing.router import Router

if TYPE_CHECKING:
    from src.domain.repositories.protocols import (
        AgentGenerationRepository,
        TurnRepository,
        VoiceGenerationRepository,
    )
from src.voice_runtime.agent_fsm import AgentFSM
from src.voice_runtime.conversation_buffer import ConversationBuffer, TurnEntry
from src.voice_runtime.events import (
    CancelAgentGeneration,
    EventEnvelope,
    HumanTurnFinalized,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
    SpeechStarted,
    ToolResult,
    VoiceGenerationCompleted,
    VoiceGenerationError,
)
from src.voice_runtime.state import CoordinatorRuntimeState
from src.voice_runtime.tool_executor import ToolExecutor
from src.voice_runtime.turn_manager import TurnManager
from src.voice_runtime.types import (
    AgentGenerationOutcome,
    AgentState,
    PolicyKey,
    RouteALabel,
    TurnState,
    VoiceKind,
    VoiceState,
)

logger = structlog.get_logger()


class Coordinator:
    """Central orchestrator: consumes events, dispatches to actors, manages state."""

    def __init__(
        self,
        call_id: UUID,
        turn_manager: TurnManager,
        agent_fsm: AgentFSM,
        tool_executor: ToolExecutor,
        router: Router,
        policies: PoliciesRegistry,
        seen_events: TTLSet | None = None,
        tool_cache: TTLMap | None = None,
        turn_repo: TurnRepository | None = None,
        agent_gen_repo: AgentGenerationRepository | None = None,
        voice_gen_repo: VoiceGenerationRepository | None = None,
        max_history_turns: int = 10,
        max_history_chars: int = 2000,
        routing_context_window: int = 1,
        routing_short_text_chars: int = 20,
        llm_context_window: int = 3,
    ) -> None:
        self._call_id = call_id
        self._turn_manager = turn_manager
        self._agent_fsm = agent_fsm
        self._tool_executor = tool_executor
        self._router = router
        self._policies = policies
        self._seen_events = seen_events
        self._tool_cache = tool_cache
        self._turn_repo = turn_repo
        self._agent_gen_repo = agent_gen_repo
        self._voice_gen_repo = voice_gen_repo
        self._state = CoordinatorRuntimeState(call_id=call_id)
        self._conversation_buffer = ConversationBuffer(
            max_turns=max_history_turns, max_chars=max_history_chars
        )
        self._routing_context_builder = RoutingContextBuilder(
            short_text_chars=routing_short_text_chars,
            context_window=routing_context_window,
            llm_context_window=llm_context_window,
        )
        self._seen_ids_fallback: set[str] = set()
        self._filler_task: asyncio.Task[None] | None = None
        self._output_events: list[
            RealtimeVoiceStart | RealtimeVoiceCancel | CancelAgentGeneration
        ] = []
        self._debug_callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None

    @property
    def state(self) -> CoordinatorRuntimeState:
        return self._state

    def drain_output_events(
        self,
    ) -> list[RealtimeVoiceStart | RealtimeVoiceCancel | CancelAgentGeneration]:
        events = self._output_events
        self._output_events = []
        return events

    # ------------------------------------------------------------------
    # Debug event emission
    # ------------------------------------------------------------------

    def set_debug_callback(
        self,
        callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None,
    ) -> None:
        """Register or unregister a debug event callback."""
        self._debug_callback = callback

    async def _emit_debug(self, event: dict[str, Any]) -> None:
        """Emit a debug event if a callback is registered."""
        if self._debug_callback is not None:
            try:
                await self._debug_callback(event)
            except Exception:
                pass  # Debug is best-effort

    # ------------------------------------------------------------------
    # Persistence helpers (10.9)
    # ------------------------------------------------------------------

    async def _persist_safe(self, coro: object) -> None:
        """Fire-and-forget persistence; log but don't crash on failure."""
        try:
            await coro  # type: ignore[misc]
        except Exception:
            logger.warning("persistence_error", exc_info=True)

    # ------------------------------------------------------------------
    # Idempotency (10.7)
    # ------------------------------------------------------------------

    async def _is_duplicate(self, event_id: UUID) -> bool:
        eid = str(event_id)
        if self._seen_events is not None:
            try:
                is_new = await self._seen_events.add(eid)
                return not is_new
            except Exception:
                logger.warning("redis_dedup_fallback")
        # In-memory fallback
        if eid in self._seen_ids_fallback:
            return True
        self._seen_ids_fallback.add(eid)
        return False

    # ------------------------------------------------------------------
    # Event Handling (10.2)
    # ------------------------------------------------------------------

    async def handle_event(self, envelope: EventEnvelope) -> None:
        """Main entry point: dispatch event by type."""
        if await self._is_duplicate(envelope.event_id):
            logger.debug("duplicate_event_ignored", event_id=str(envelope.event_id))
            return

        tracer = get_tracer()
        with tracer.start_as_current_span(
            f"coordinator.{envelope.type}",
            attributes={
                "call_id": str(self._call_id),
                "event_type": envelope.type,
                "event_id": str(envelope.event_id),
                "turn_id": str(self._state.active_turn_id) if self._state.active_turn_id else "",
                "agent_generation_id": str(self._state.active_agent_generation_id) if self._state.active_agent_generation_id else "",
            },
        ):
            match envelope.type:
                case "speech_started":
                    await self._on_speech_started(envelope)
                case "transcript_final":
                    await self._on_transcript_final(envelope)
                case "human_turn_finalized":
                    await self._on_human_turn_finalized(envelope)
                case "request_guided_response":
                    await self._on_request_guided_response(envelope)
                case "request_agent_action":
                    await self._on_request_agent_action(envelope)
                case "tool_result":
                    await self._on_tool_result(envelope)
                case "voice_generation_completed":
                    await self._on_voice_completed(envelope)
                case "voice_generation_error":
                    await self._on_voice_error(envelope)
                case _:
                    logger.debug("unhandled_event_in_coordinator", event_type=envelope.type)

    # ------------------------------------------------------------------
    # Barge-in (10.4)
    # ------------------------------------------------------------------

    async def _on_speech_started(self, envelope: EventEnvelope) -> None:
        s = self._state

        # Cancel active voice if any (record barge-in metric)
        voice_id = s.cancel_active_voice()
        if voice_id is not None:
            BARGE_IN_TOTAL.inc()
            self._output_events.append(
                RealtimeVoiceCancel(
                    call_id=self._call_id,
                    voice_generation_id=voice_id,
                    reason="barge_in",
                    ts=envelope.ts,
                )
            )

        # Cancel active generation if any
        gen_id = s.cancel_active_generation()
        if gen_id is not None:
            self._output_events.append(
                CancelAgentGeneration(
                    call_id=self._call_id,
                    agent_generation_id=gen_id,
                    reason="barge_in",
                    ts=envelope.ts,
                )
            )
            self._agent_fsm.cancel(envelope.ts)
            self._agent_fsm.reset()

            # Persist agent generation cancellation (10.9)
            if self._agent_gen_repo is not None and s.active_turn_id is not None:
                from src.domain.models.entities import AgentGeneration

                await self._persist_safe(
                    self._agent_gen_repo.update(
                        AgentGeneration(
                            agent_generation_id=gen_id,
                            call_id=self._call_id,
                            turn_id=s.active_turn_id,
                            created_at=envelope.ts,
                            state=AgentState.CANCELLED,
                            ended_at=envelope.ts,
                            cancel_reason="barge_in",
                        )
                    )
                )

        # Cancel filler if running
        self._cancel_filler()

        # Forward to TurnManager
        self._turn_manager.handle_speech_started(envelope.ts)

    async def _on_transcript_final(self, envelope: EventEnvelope) -> None:
        text = envelope.payload.get("text", "")
        self._turn_manager.handle_transcript_final(str(text), envelope.ts)

        # Drain turn events and process finalized turns
        for event in self._turn_manager.drain_events():
            if isinstance(event, HumanTurnFinalized):
                fake_envelope = EventEnvelope(
                    event_id=uuid4(),
                    call_id=self._call_id,
                    ts=event.ts,
                    type="human_turn_finalized",
                    payload={"turn_id": str(event.turn_id), "text": event.text},
                    source=envelope.source,
                )
                await self._on_human_turn_finalized(fake_envelope)

    # ------------------------------------------------------------------
    # Turn lifecycle (10.3)
    # ------------------------------------------------------------------

    async def _on_human_turn_finalized(self, envelope: EventEnvelope) -> None:
        s = self._state

        # Cancel previous generation if still active (rapid successive turns - 10.3)
        if s.active_agent_generation_id is not None:
            prev_gen_id = s.active_agent_generation_id
            prev_turn_id = s.active_turn_id
            s.cancel_active_generation()
            s.cancel_active_voice()
            self._agent_fsm.cancel(envelope.ts)
            self._agent_fsm.reset()

            # Persist agent generation cancellation (10.9)
            if self._agent_gen_repo is not None and prev_turn_id is not None:
                from src.domain.models.entities import AgentGeneration

                await self._persist_safe(
                    self._agent_gen_repo.update(
                        AgentGeneration(
                            agent_generation_id=prev_gen_id,
                            call_id=self._call_id,
                            turn_id=prev_turn_id,
                            created_at=envelope.ts,
                            state=AgentState.CANCELLED,
                            ended_at=envelope.ts,
                            cancel_reason="rapid_successive_turn",
                        )
                    )
                )

        turn_id_str = envelope.payload.get("turn_id", "")
        text = str(envelope.payload.get("text", ""))
        turn_id = UUID(str(turn_id_str)) if turn_id_str else uuid4()

        s.active_turn_id = turn_id
        s.turn_seq += 1
        agent_generation_id = uuid4()
        s.active_agent_generation_id = agent_generation_id

        # Detect language, build routing context, and classify
        from src.routing.language import detect_language

        language = detect_language(text)
        routing_ctx = self._routing_context_builder.build(
            user_text=text,
            language=language,
            buffer=self._conversation_buffer,
        )
        routing_result = await self._router.classify(
            text,
            language,
            enriched_text=routing_ctx.enriched_text,
            llm_context=routing_ctx.llm_context,
        )

        # Persist turn insert (10.9)
        if self._turn_repo is not None:
            from src.domain.models.entities import Turn

            turn_entity = Turn(
                turn_id=turn_id,
                call_id=self._call_id,
                seq=s.turn_seq,
                started_at=envelope.ts,
                state=TurnState.FINALIZED,
                finalized_at=envelope.ts,
                text_final=text,
                language=language,
            )
            await self._persist_safe(self._turn_repo.insert(turn_entity))

        # Persist agent generation insert (10.9)
        if self._agent_gen_repo is not None:
            from src.domain.models.entities import AgentGeneration

            gen_entity = AgentGeneration(
                agent_generation_id=agent_generation_id,
                call_id=self._call_id,
                turn_id=turn_id,
                created_at=envelope.ts,
                state=AgentState.THINKING,
                started_at=envelope.ts,
                route_a_label=routing_result.route_a_label.value,
                route_a_confidence=routing_result.route_a_confidence,
                policy_key=None,
                specialist=routing_result.route_b_label.value if routing_result.route_b_label else None,
            )
            await self._persist_safe(self._agent_gen_repo.insert(gen_entity))

        # Debug: turn update
        await self._emit_debug({
            "type": "turn_update",
            "turn_id": str(turn_id),
            "text": text,
            "state": "finalized",
        })

        # Debug: routing decision
        await self._emit_debug({
            "type": "routing",
            "route_a": routing_result.route_a_label.value,
            "route_a_confidence": routing_result.route_a_confidence,
            "route_b": routing_result.route_b_label.value if routing_result.route_b_label else None,
        })

        # Run Agent FSM
        fsm_output = self._agent_fsm.handle_turn(
            agent_generation_id=agent_generation_id,
            route_a_label=routing_result.route_a_label,
            route_a_confidence=routing_result.route_a_confidence,
            route_b_label=routing_result.route_b_label,
            user_text=text,
            ts=envelope.ts,
        )

        # Debug: FSM state after handle_turn
        await self._emit_debug({
            "type": "fsm_state",
            "state": self._agent_fsm.state.value if hasattr(self._agent_fsm.state, "value") else str(self._agent_fsm.state),
            "agent_generation_id": str(agent_generation_id),
        })

        # Process FSM output
        for guided in fsm_output.guided_responses:
            guided_envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=self._call_id,
                ts=envelope.ts,
                type="request_guided_response",
                payload={
                    "agent_generation_id": str(guided.agent_generation_id),
                    "policy_key": guided.policy_key,
                    "user_text": guided.user_text,
                },
                source=envelope.source,
            )
            await self._on_request_guided_response(guided_envelope)

        for action in fsm_output.agent_actions:
            action_envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=self._call_id,
                ts=envelope.ts,
                type="request_agent_action",
                payload={
                    "agent_generation_id": str(action.agent_generation_id),
                    "specialist": action.specialist,
                    "user_text": action.user_text,
                },
                source=envelope.source,
            )
            await self._on_request_agent_action(action_envelope)

        # Record Prometheus metrics (13.3)
        ROUTE_A_CONFIDENCE.observe(routing_result.route_a_confidence)
        if routing_result.route_b_confidence is not None:
            ROUTE_B_CONFIDENCE.observe(routing_result.route_b_confidence)

        # Determine margin and final_action for calibration logging (13.5)
        scores_a = routing_result.all_scores_a
        if scores_a:
            sorted_a = sorted(scores_a.values(), reverse=True)
            margin_a = sorted_a[0] - sorted_a[1] if len(sorted_a) > 1 else 1.0
        else:
            margin_a = 0.0

        if routing_result.route_b_label is not None:
            final_action = "tool"
        elif routing_result.route_a_label == RouteALabel.DOMAIN:
            final_action = "clarify"
        elif routing_result.route_a_label in (RouteALabel.DISALLOWED, RouteALabel.OUT_OF_SCOPE):
            final_action = "guided_response"
        else:
            final_action = "guided_response"

        # Structured router calibration log (13.5)
        logger.info(
            "routing_decision",
            router_version=getattr(self._router, "_registry", None)
            and getattr(self._router._registry.thresholds, "version", "unknown")
            or "unknown",
            call_id=str(self._call_id),
            turn_id=str(turn_id),
            agent_generation_id=str(agent_generation_id),
            language=language,
            route_a_label=routing_result.route_a_label.value,
            route_a_score=routing_result.route_a_confidence,
            route_b_label=routing_result.route_b_label.value if routing_result.route_b_label else None,
            route_b_score=routing_result.route_b_confidence,
            margin=margin_a,
            short_circuit=routing_result.short_circuit,
            fallback_used=routing_result.fallback_used,
            final_action=final_action,
        )

    # ------------------------------------------------------------------
    # Prompt construction + voice start (10.5)
    # ------------------------------------------------------------------

    async def _on_request_guided_response(self, envelope: EventEnvelope) -> None:
        s = self._state
        gen_id_str = str(envelope.payload.get("agent_generation_id", ""))
        gen_id = UUID(gen_id_str) if gen_id_str else None

        # Late result check (10.8)
        if gen_id and s.is_generation_cancelled(gen_id):
            logger.debug("late_guided_response_ignored", gen_id=gen_id_str)
            return

        policy_key_str = str(envelope.payload.get("policy_key", ""))
        user_text = str(envelope.payload.get("user_text", ""))

        try:
            policy_key = PolicyKey(policy_key_str)
        except ValueError:
            logger.error("invalid_policy_key", policy_key=policy_key_str)
            policy_key = PolicyKey.CLARIFY_DEPARTMENT

        prompt = self._policies.build_prompt(policy_key, user_text)
        voice_gen_id = uuid4()
        s.active_voice_generation_id = voice_gen_id
        actual_gen_id = gen_id or uuid4()

        history = self._conversation_buffer.format_messages()
        self._output_events.append(
            RealtimeVoiceStart(
                call_id=self._call_id,
                agent_generation_id=actual_gen_id,
                voice_generation_id=voice_gen_id,
                prompt=[
                    {"role": "system", "content": self._policies.base_system},
                    {"role": "system", "content": self._policies.get_instructions(policy_key)},
                    *history,
                    {"role": "user", "content": user_text},
                ],
                ts=envelope.ts,
            )
        )

        # Debug: latency from turn finalized to voice start
        await self._emit_debug({
            "type": "latency",
            "metric": "turn_processing_ms",
            "value": round((time.time() * 1000) - envelope.ts, 2),
        })

        # Append to conversation buffer
        self._conversation_buffer.append(
            TurnEntry(
                seq=s.turn_seq,
                user_text=user_text,
                route_a_label=policy_key_str,
                policy_key=policy_key_str,
            )
        )

        # Persist voice generation insert (10.9)
        if self._voice_gen_repo is not None:
            from src.domain.models.entities import VoiceGeneration

            voice_entity = VoiceGeneration(
                voice_generation_id=voice_gen_id,
                call_id=self._call_id,
                agent_generation_id=actual_gen_id,
                turn_id=s.active_turn_id or uuid4(),
                kind=VoiceKind.RESPONSE,
                state=VoiceState.STARTING,
                started_at=envelope.ts,
            )
            await self._persist_safe(self._voice_gen_repo.insert(voice_entity))

    async def _on_request_agent_action(self, envelope: EventEnvelope) -> None:
        s = self._state
        gen_id_str = str(envelope.payload.get("agent_generation_id", ""))
        gen_id = UUID(gen_id_str) if gen_id_str else None

        if gen_id and s.is_generation_cancelled(gen_id):
            logger.debug("late_agent_action_ignored", gen_id=gen_id_str)
            return

        # For now, emit a placeholder voice start for the specialist action
        # In full implementation, this would trigger tool execution first
        specialist = str(envelope.payload.get("specialist", ""))
        user_text = str(envelope.payload.get("user_text", ""))

        # Filler strategy (10.6)
        if self._should_emit_filler():
            FILLER_EMITTED_TOTAL.inc()
            filler_voice_id = uuid4()
            self._output_events.append(
                RealtimeVoiceStart(
                    call_id=self._call_id,
                    agent_generation_id=gen_id or uuid4(),
                    voice_generation_id=filler_voice_id,
                    prompt="Un momento, por favor.",
                    ts=envelope.ts,
                )
            )
            self._start_filler_timeout(filler_voice_id, envelope.ts)

        voice_gen_id = uuid4()
        s.active_voice_generation_id = voice_gen_id
        actual_gen_id = gen_id or uuid4()
        self._output_events.append(
            RealtimeVoiceStart(
                call_id=self._call_id,
                agent_generation_id=actual_gen_id,
                voice_generation_id=voice_gen_id,
                prompt=f"Specialist: {specialist}. User said: {user_text}",
                ts=envelope.ts,
            )
        )

        # Append to conversation buffer
        self._conversation_buffer.append(
            TurnEntry(
                seq=s.turn_seq,
                user_text=user_text,
                route_a_label="domain",
                specialist=specialist,
            )
        )

        # Persist voice generation insert (10.9)
        if self._voice_gen_repo is not None:
            from src.domain.models.entities import VoiceGeneration

            voice_entity = VoiceGeneration(
                voice_generation_id=voice_gen_id,
                call_id=self._call_id,
                agent_generation_id=actual_gen_id,
                turn_id=s.active_turn_id or uuid4(),
                kind=VoiceKind.RESPONSE,
                state=VoiceState.STARTING,
                started_at=envelope.ts,
            )
            await self._persist_safe(self._voice_gen_repo.insert(voice_entity))

    # ------------------------------------------------------------------
    # Tool result handling (10.8)
    # ------------------------------------------------------------------

    async def _on_tool_result(self, envelope: EventEnvelope) -> None:
        gen_id_str = str(envelope.payload.get("agent_generation_id", ""))
        if gen_id_str:
            gen_id = UUID(gen_id_str)
            if self._state.is_generation_cancelled(gen_id):
                logger.info("late_tool_result_ignored", gen_id=gen_id_str)
                return

        # Cancel filler on tool_result
        self._cancel_filler()

    # ------------------------------------------------------------------
    # Voice callbacks (10.8)
    # ------------------------------------------------------------------

    async def _on_voice_completed(self, envelope: EventEnvelope) -> None:
        voice_id_str = str(envelope.payload.get("voice_generation_id", ""))
        if voice_id_str:
            voice_id = UUID(voice_id_str)
            if self._state.is_voice_cancelled(voice_id):
                logger.debug("late_voice_completed_ignored", voice_id=voice_id_str)
                return
            # Persist voice generation update (10.9)
            if self._voice_gen_repo is not None:
                from src.domain.models.entities import VoiceGeneration

                await self._persist_safe(
                    self._voice_gen_repo.update(
                        VoiceGeneration(
                            voice_generation_id=voice_id,
                            call_id=self._call_id,
                            agent_generation_id=self._state.active_agent_generation_id or uuid4(),
                            turn_id=self._state.active_turn_id or uuid4(),
                            kind=VoiceKind.RESPONSE,
                            state=VoiceState.COMPLETED,
                            ended_at=envelope.ts,
                        )
                    )
                )
        self._state.active_voice_generation_id = None

    async def _on_voice_error(self, envelope: EventEnvelope) -> None:
        voice_id_str = str(envelope.payload.get("voice_generation_id", ""))
        if voice_id_str:
            voice_id = UUID(voice_id_str)
            if self._state.is_voice_cancelled(voice_id):
                return
            # Persist voice generation error (10.9)
            if self._voice_gen_repo is not None:
                from src.domain.models.entities import VoiceGeneration

                await self._persist_safe(
                    self._voice_gen_repo.update(
                        VoiceGeneration(
                            voice_generation_id=voice_id,
                            call_id=self._call_id,
                            agent_generation_id=self._state.active_agent_generation_id or uuid4(),
                            turn_id=self._state.active_turn_id or uuid4(),
                            kind=VoiceKind.RESPONSE,
                            state=VoiceState.ERROR,
                            ended_at=envelope.ts,
                            error=str(envelope.payload.get("error", "")),
                        )
                    )
                )
        self._state.active_voice_generation_id = None
        logger.error("voice_generation_error", payload=envelope.payload)

    # ------------------------------------------------------------------
    # Filler strategy (10.6)
    # ------------------------------------------------------------------

    def _should_emit_filler(self) -> bool:
        # In full implementation, this checks thresholds config
        return False  # Disabled by default; enabled when thresholds loaded

    def _start_filler_timeout(self, voice_gen_id: UUID, ts: int) -> None:
        async def _auto_cancel_filler() -> None:
            await asyncio.sleep(1.2)  # 1200ms max
            if not self._state.is_voice_cancelled(voice_gen_id):
                self._state.cancelled_voice_generations.add(voice_gen_id)
                self._output_events.append(
                    RealtimeVoiceCancel(
                        call_id=self._call_id,
                        voice_generation_id=voice_gen_id,
                        reason="filler_max_duration",
                        ts=ts,
                    )
                )

        self._filler_task = asyncio.create_task(_auto_cancel_filler())

    def _cancel_filler(self) -> None:
        if self._filler_task is not None and not self._filler_task.done():
            self._filler_task.cancel()
            self._filler_task = None
