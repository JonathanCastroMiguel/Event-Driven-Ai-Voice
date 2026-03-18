from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Callable, Coroutine
from uuid import UUID, uuid4

import structlog

from src.infrastructure.redis_client import TTLMap, TTLSet
from src.infrastructure.telemetry import (
    BARGE_IN_TOTAL,
    FILLER_EMITTED_TOTAL,
    get_tracer,
)
from src.routing.model_router import RouterPromptBuilder
from src.routing.policies import PoliciesRegistry

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
)
from src.voice_runtime.state import CoordinatorRuntimeState
from src.voice_runtime.tool_executor import ToolExecutor
from src.voice_runtime.turn_manager import TurnManager
from src.voice_runtime.types import (
    AgentState,
    TurnState,
    VoiceKind,
    VoiceState,
)

logger = structlog.get_logger()


class Coordinator:
    """Central orchestrator: consumes events, dispatches to actors, manages state.

    Uses model-as-router architecture: the Realtime voice model classifies intent
    AND responds in a single inference via response.create with router prompt.
    """

    def __init__(
        self,
        call_id: UUID,
        turn_manager: TurnManager,
        agent_fsm: AgentFSM,
        tool_executor: ToolExecutor,
        router_prompt_builder: RouterPromptBuilder | None,
        policies: PoliciesRegistry,
        seen_events: TTLSet | None = None,
        tool_cache: TTLMap | None = None,
        turn_repo: TurnRepository | None = None,
        agent_gen_repo: AgentGenerationRepository | None = None,
        voice_gen_repo: VoiceGenerationRepository | None = None,
        max_history_turns: int = 10,
        max_history_chars: int = 2000,
    ) -> None:
        self._call_id = call_id
        self._turn_manager = turn_manager
        self._agent_fsm = agent_fsm
        self._tool_executor = tool_executor
        self._router_prompt_builder = router_prompt_builder
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
        self._seen_ids_fallback: set[str] = set()
        self._filler_task: asyncio.Task[None] | None = None
        self._output_events: list[
            RealtimeVoiceStart | RealtimeVoiceCancel | CancelAgentGeneration
        ] = []
        self._debug_callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None
        self._debug_enabled: bool = False
        self._debug_turn_id: UUID | None = None
        self._debug_turn_start_ms: int = 0
        self._debug_last_stage_ms: int = 0
        self._debug_route_result_emitted: bool = False
        self._debug_audio_playback_end_received: bool = False
        self._output_callback: Callable[
            [RealtimeVoiceStart | RealtimeVoiceCancel | CancelAgentGeneration],
            Coroutine[Any, Any, None],
        ] | None = None

    @property
    def state(self) -> CoordinatorRuntimeState:
        return self._state

    def set_output_callback(
        self,
        callback: Callable[
            [RealtimeVoiceStart | RealtimeVoiceCancel | CancelAgentGeneration],
            Coroutine[Any, Any, None],
        ] | None,
    ) -> None:
        """Register callback for output events (voice start/cancel)."""
        self._output_callback = callback

    def drain_output_events(
        self,
    ) -> list[RealtimeVoiceStart | RealtimeVoiceCancel | CancelAgentGeneration]:
        events = self._output_events
        self._output_events = []
        return events

    async def _emit_output(
        self,
        event: RealtimeVoiceStart | RealtimeVoiceCancel | CancelAgentGeneration,
    ) -> None:
        """Append to output list and invoke callback if registered."""
        self._output_events.append(event)
        if self._output_callback is not None:
            try:
                await self._output_callback(event)
            except Exception:
                logger.exception(
                    "output_callback_error",
                    call_id=str(self._call_id),
                    event_type=type(event).__name__,
                )

    # ------------------------------------------------------------------
    # Debug event emission
    # ------------------------------------------------------------------

    def set_debug_callback(
        self,
        callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None,
    ) -> None:
        """Register or unregister a debug event callback."""
        self._debug_callback = callback

    def set_debug_enabled(self, enabled: bool) -> None:
        """Enable or disable debug event emission for this session."""
        self._debug_enabled = enabled
        logger.info(
            "debug_mode_toggled",
            call_id=str(self._call_id),
            enabled=enabled,
        )

    async def _emit_debug(self, event: dict[str, Any]) -> None:
        """Emit a debug event if a callback is registered."""
        if self._debug_callback is not None:
            try:
                await self._debug_callback(event)
            except Exception:
                pass  # Debug is best-effort

    async def _send_debug(self, stage: str, **extra: Any) -> None:
        """Emit a structured debug_event for the pipeline timeline.

        No-op when debug is disabled. Computes delta_ms and total_ms
        automatically from the turn's timing state.
        """
        if not self._debug_enabled or self._debug_callback is None:
            return

        now = self._now_ms()

        if stage == "speech_start":
            self._debug_turn_id = uuid4()
            self._debug_turn_start_ms = now
            self._debug_last_stage_ms = now

        delta_ms = now - self._debug_last_stage_ms if self._debug_last_stage_ms else 0
        total_ms = now - self._debug_turn_start_ms if self._debug_turn_start_ms else 0
        self._debug_last_stage_ms = now

        event: dict[str, Any] = {
            "type": "debug_event",
            "turn_id": str(self._debug_turn_id) if self._debug_turn_id else "",
            "stage": stage,
            "delta_ms": delta_ms,
            "total_ms": total_ms,
            "ts": now,
            **extra,
        }

        await self._emit_debug(event)

    async def handle_client_debug_event(self, stage: str, turn_id: str, ts: int) -> None:
        """Handle a debug event sent from the frontend (e.g., audio playback timing).

        The event is integrated into the server-side debug pipeline with proper
        delta_ms/total_ms relative to the current turn.
        """
        if stage == "audio_playback_end":
            self._debug_audio_playback_end_received = True
        await self._send_debug(stage)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _persist_safe(self, coro: object) -> None:
        """Fire-and-forget persistence; log but don't crash on failure."""
        try:
            await coro  # type: ignore[misc]
        except Exception:
            logger.warning("persistence_error", exc_info=True)

    # ------------------------------------------------------------------
    # Idempotency
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
    # Event Handling
    # ------------------------------------------------------------------

    async def handle_event(self, envelope: EventEnvelope) -> None:
        """Main entry point: dispatch event by type."""
        logger.info(
            "coordinator_handle_event",
            call_id=str(self._call_id),
            event_type=envelope.type,
            source=envelope.source.value,
        )
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
                case "speech_stopped":
                    await self._on_speech_stopped(envelope)
                case "audio_committed":
                    await self._on_audio_committed(envelope)
                case "transcript_final":
                    await self._on_transcript_final(envelope)
                case "model_router_action":
                    await self._on_model_router_action(envelope)
                case "response_created":
                    response_source = envelope.payload.get("response_source", "router")
                    send_to_created_ms = envelope.payload.get("send_to_created_ms")
                    if response_source == "specialist":
                        kwargs: dict[str, int] = {}
                        if send_to_created_ms is not None:
                            kwargs["send_to_created_ms"] = send_to_created_ms
                        await self._send_debug("specialist_processing", **kwargs)
                    else:
                        kwargs = {}
                        if send_to_created_ms is not None:
                            kwargs["send_to_created_ms"] = send_to_created_ms
                        await self._send_debug("model_processing", **kwargs)
                case "voice_generation_completed":
                    await self._on_voice_completed(envelope)
                case "voice_generation_error":
                    await self._on_voice_error(envelope)
                case "tool_result":
                    await self._on_tool_result(envelope)
                case _:
                    logger.debug("unhandled_event_in_coordinator", event_type=envelope.type)

    # ------------------------------------------------------------------
    # Barge-in
    # ------------------------------------------------------------------

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    async def _on_speech_started(self, envelope: EventEnvelope) -> None:
        s = self._state
        s.turn_speech_started_ms = envelope.ts

        logger.info(
            "fsm_speech_started",
            call_id=str(self._call_id),
            turn_seq=s.turn_seq,
            ts=envelope.ts,
            fsm_state=self._agent_fsm.state.value,
        )

        # Debug: speech_start (assigns new turn_id, resets timing)
        self._debug_route_result_emitted = False
        self._debug_audio_playback_end_received = False
        await self._send_debug("speech_start")

        # Cancel active voice if any (record barge-in metric)
        voice_id = s.cancel_active_voice()
        if voice_id is not None:
            BARGE_IN_TOTAL.inc()
            # Debug: barge_in on previous turn
            await self._send_debug("barge_in")
            await self._emit_output(
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
            await self._emit_output(
                CancelAgentGeneration(
                    call_id=self._call_id,
                    agent_generation_id=gen_id,
                    reason="barge_in",
                    ts=envelope.ts,
                )
            )
            self._agent_fsm.cancel(envelope.ts)
            self._agent_fsm.reset()

            # Persist agent generation cancellation
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

    async def _on_speech_stopped(self, envelope: EventEnvelope) -> None:
        """Handle speech_stopped: VAD detected silence. Debug only — no pipeline action."""
        await self._send_debug("speech_stop")

    # ------------------------------------------------------------------
    # Audio committed — primary turn trigger (model-as-router)
    # ------------------------------------------------------------------

    async def _on_audio_committed(self, envelope: EventEnvelope) -> None:
        """Handle audio_committed: finalize turn, build router prompt, emit response.create."""
        s = self._state
        s.turn_audio_committed_ms = envelope.ts

        speech_to_committed_ms = envelope.ts - s.turn_speech_started_ms if s.turn_speech_started_ms else 0
        logger.info(
            "fsm_audio_committed",
            call_id=str(self._call_id),
            turn_seq=s.turn_seq,
            ts=envelope.ts,
            speech_to_committed_ms=speech_to_committed_ms,
            fsm_state=self._agent_fsm.state.value,
        )

        # Debug: audio_committed
        await self._send_debug("audio_committed")

        # Finalize the turn via TurnManager
        self._turn_manager.handle_audio_committed(envelope.ts)

        # Process turn events from TurnManager
        for event in self._turn_manager.drain_events():
            if isinstance(event, HumanTurnFinalized):
                turn_id = event.turn_id

                # Cancel previous generation if still active (rapid successive turns)
                if s.active_agent_generation_id is not None:
                    prev_gen_id = s.active_agent_generation_id
                    prev_turn_id = s.active_turn_id
                    s.cancel_active_generation()
                    s.cancel_active_voice()
                    self._agent_fsm.cancel(envelope.ts)
                    self._agent_fsm.reset()

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

                s.active_turn_id = turn_id
                s.turn_seq += 1
                agent_generation_id = uuid4()
                s.active_agent_generation_id = agent_generation_id

                # Create conversation buffer entry early (user_text/agent_text filled async)
                self._conversation_buffer.append(TurnEntry(seq=s.turn_seq))

                # FSM: idle → routing
                self._agent_fsm.start_routing(agent_generation_id, envelope.ts)
                logger.info(
                    "fsm_transition",
                    call_id=str(self._call_id),
                    turn_seq=s.turn_seq,
                    transition="idle→routing",
                    fsm_state=self._agent_fsm.state.value,
                    agent_generation_id=str(agent_generation_id),
                )

                # Build router prompt with conversation history (excludes current turn)
                history = self._conversation_buffer.format_messages()
                if history:
                    logger.info(
                        "history_content",
                        call_id=str(self._call_id),
                        turn_count=len(history) // 2,
                        messages=[
                            {"role": m["role"], "text": m["content"][:80]}
                            for m in history
                        ],
                    )

                if self._router_prompt_builder is not None:
                    payload = self._router_prompt_builder.build_response_create(history)
                else:
                    # Fallback when no router prompt builder configured
                    fallback_instructions = "You are a helpful voice assistant."
                    if history:
                        history_lines = [
                            f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
                            for m in history
                        ]
                        fallback_instructions += "\n\nConversation history:\n" + "\n".join(history_lines)
                    payload = {
                        "type": "response.create",
                        "response": {
                            "modalities": ["text", "audio"],
                            "instructions": fallback_instructions,
                        },
                    }

                # Debug: prompt_sent (after building, before sending)
                await self._send_debug("prompt_sent")

                voice_gen_id = uuid4()
                s.active_voice_generation_id = voice_gen_id

                await self._emit_output(
                    RealtimeVoiceStart(
                        call_id=self._call_id,
                        agent_generation_id=agent_generation_id,
                        voice_generation_id=voice_gen_id,
                        prompt=payload,
                        ts=envelope.ts,
                    )
                )

                # Persist turn
                if self._turn_repo is not None:
                    from src.domain.models.entities import Turn

                    turn_entity = Turn(
                        turn_id=turn_id,
                        call_id=self._call_id,
                        seq=s.turn_seq,
                        started_at=envelope.ts,
                        state=TurnState.FINALIZED,
                        finalized_at=envelope.ts,
                        text_final="",  # Text arrives asynchronously
                    )
                    await self._persist_safe(self._turn_repo.insert(turn_entity))

                # Persist agent generation
                if self._agent_gen_repo is not None:
                    from src.domain.models.entities import AgentGeneration

                    gen_entity = AgentGeneration(
                        agent_generation_id=agent_generation_id,
                        call_id=self._call_id,
                        turn_id=turn_id,
                        created_at=envelope.ts,
                        state=AgentState.ROUTING,
                        started_at=envelope.ts,
                    )
                    await self._persist_safe(self._agent_gen_repo.insert(gen_entity))

                # Debug events
                await self._emit_debug({
                    "type": "turn_update",
                    "turn_id": str(turn_id),
                    "text": "",
                    "state": "finalized",
                })

                await self._emit_debug({
                    "type": "fsm_state",
                    "state": self._agent_fsm.state.value,
                    "agent_generation_id": str(agent_generation_id),
                })

                dispatch_elapsed_ms = self._now_ms() - s.turn_audio_committed_ms
                logger.info(
                    "model_router_dispatched",
                    call_id=str(self._call_id),
                    turn_seq=s.turn_seq,
                    turn_id=str(turn_id),
                    agent_generation_id=str(agent_generation_id),
                    has_history=len(history) > 0,
                    history_turns=len(history) // 2,
                    dispatch_elapsed_ms=dispatch_elapsed_ms,
                    speech_to_dispatch_ms=self._now_ms() - s.turn_speech_started_ms if s.turn_speech_started_ms else 0,
                )

    # ------------------------------------------------------------------
    # Transcript final — async logging only
    # ------------------------------------------------------------------

    async def _on_transcript_final(self, envelope: EventEnvelope) -> None:
        """Store transcript for logging, persistence, and debug display. No routing."""
        text = str(envelope.payload.get("text", ""))
        s = self._state

        transcript_elapsed_ms = envelope.ts - s.turn_audio_committed_ms if s.turn_audio_committed_ms else 0
        logger.info(
            "fsm_transcript_final",
            call_id=str(self._call_id),
            turn_seq=s.turn_seq,
            text=text[:100],
            transcript_elapsed_ms=transcript_elapsed_ms,
            fsm_state=self._agent_fsm.state.value,
        )

        self._turn_manager.handle_transcript_final(text, envelope.ts)

        # Update conversation buffer entry with user text (entry created at audio_committed)
        if text and self._state.active_turn_id is not None:
            self._conversation_buffer.update_last_user_text(text)

        # Update persisted turn with transcript text
        if self._turn_repo is not None and self._state.active_turn_id is not None:
            from src.domain.models.entities import Turn

            await self._persist_safe(
                self._turn_repo.update(
                    Turn(
                        turn_id=self._state.active_turn_id,
                        call_id=self._call_id,
                        seq=self._state.turn_seq,
                        started_at=envelope.ts,
                        state=TurnState.FINALIZED,
                        text_final=text,
                    )
                )
            )

        # Debug: transcript arrived
        await self._emit_debug({
            "type": "transcript_final",
            "turn_id": str(self._state.active_turn_id) if self._state.active_turn_id else None,
            "text": text,
        })

    # ------------------------------------------------------------------
    # Model router action — specialist dispatch
    # ------------------------------------------------------------------

    async def _on_model_router_action(self, envelope: EventEnvelope) -> None:
        """Handle model_router_action: the model called route_to_specialist() for specialist routing."""
        s = self._state
        department = str(envelope.payload.get("department", ""))
        summary = str(envelope.payload.get("summary", ""))

        routing_elapsed_ms = envelope.ts - s.turn_audio_committed_ms if s.turn_audio_committed_ms else 0
        logger.info(
            "fsm_model_router_action",
            call_id=str(self._call_id),
            turn_seq=s.turn_seq,
            department=department,
            summary=summary[:100],
            routing_elapsed_ms=routing_elapsed_ms,
            fsm_state=self._agent_fsm.state.value,
        )

        if s.active_agent_generation_id is None:
            logger.warning("model_router_action_without_active_generation")
            return

        if s.is_generation_cancelled(s.active_agent_generation_id):
            logger.debug("late_model_router_action_ignored")
            return

        # Debug: route_result (delegate)
        await self._send_debug("route_result", label=department, route_type="delegate")

        # FSM: routing → waiting_tools
        self._agent_fsm.specialist_action(envelope.ts)
        logger.info(
            "fsm_transition",
            call_id=str(self._call_id),
            turn_seq=s.turn_seq,
            transition="routing→waiting_tools",
            fsm_state=self._agent_fsm.state.value,
        )

        logger.info(
            "model_router_action_received",
            call_id=str(self._call_id),
            department=department,
            summary=summary,
            agent_generation_id=str(s.active_agent_generation_id),
        )

        # Debug: fill_silence (main flow — parallel to specialist sub-flow)
        await self._send_debug("fill_silence")

        # Filler strategy — per-department filler from config
        filler_msg: str | None = None
        if self._router_prompt_builder is not None:
            filler_msg = self._router_prompt_builder.get_department_filler(department)
        if filler_msg is not None:
            FILLER_EMITTED_TOTAL.inc()
            filler_voice_id = uuid4()
            await self._emit_output(
                RealtimeVoiceStart(
                    call_id=self._call_id,
                    agent_generation_id=s.active_agent_generation_id,
                    voice_generation_id=filler_voice_id,
                    prompt=filler_msg,
                    ts=envelope.ts,
                )
            )
            self._start_filler_timeout(filler_voice_id, envelope.ts)

        # Debug: specialist_sent (sub-flow starts)
        await self._send_debug("specialist_sent")

        # Execute specialist tool — passes summary + conversation history.
        # The tool returns a complete response.create payload.
        tool_request_id = uuid4()
        history = self._conversation_buffer.format_messages()
        # Resolve specialist tool name from config
        tool_name = f"specialist_{department}"  # fallback
        if self._router_prompt_builder is not None:
            tool_config = self._router_prompt_builder.get_department_tool(department)
            if tool_config is not None and tool_config.name is not None:
                tool_name = tool_config.name

        tool_result = await self._tool_executor.execute(
            call_id=self._call_id,
            agent_generation_id=s.active_agent_generation_id,
            tool_request_id=tool_request_id,
            tool_name=tool_name,
            args={"summary": summary, "history": history},
            timeout_ms=5000,
        )

        # FSM: waiting_tools → speaking
        self._agent_fsm.tool_result(envelope.ts)
        logger.info(
            "fsm_transition",
            call_id=str(self._call_id),
            turn_seq=s.turn_seq,
            transition="waiting_tools→speaking",
            fsm_state=self._agent_fsm.state.value,
        )

        # Debug: specialist_ready (sub-flow complete)
        await self._send_debug("specialist_ready")

        # Cancel filler if still running
        self._cancel_filler()

        # Debug: generation_start (specialist voice begins)
        await self._send_debug("generation_start")

        # Emit specialist response voice
        voice_gen_id = uuid4()
        s.active_voice_generation_id = voice_gen_id

        # Use tool result payload directly as the prompt, or fallback on failure
        if tool_result.ok:
            specialist_prompt = tool_result.payload
        else:
            logger.warning(
                "specialist_tool_failed",
                call_id=str(self._call_id),
                department=department,
                error=tool_result.payload,
            )
            specialist_prompt = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": (
                        "Apologize to the customer briefly. Tell them you are having "
                        "a temporary issue connecting to the specialist and ask them "
                        "to try again in a moment. Respond in the same language the "
                        "customer used."
                    ),
                    "temperature": 0.8,
                },
            }

        await self._emit_output(
            RealtimeVoiceStart(
                call_id=self._call_id,
                agent_generation_id=s.active_agent_generation_id,
                voice_generation_id=voice_gen_id,
                prompt=specialist_prompt,
                ts=envelope.ts,
                response_source="specialist",
            )
        )

        # Persist voice generation
        if self._voice_gen_repo is not None and s.active_turn_id is not None:
            from src.domain.models.entities import VoiceGeneration

            voice_entity = VoiceGeneration(
                voice_generation_id=voice_gen_id,
                call_id=self._call_id,
                agent_generation_id=s.active_agent_generation_id,
                turn_id=s.active_turn_id,
                kind=VoiceKind.RESPONSE,
                state=VoiceState.STARTING,
                started_at=envelope.ts,
            )
            await self._persist_safe(self._voice_gen_repo.insert(voice_entity))

    # ------------------------------------------------------------------
    # Voice callbacks
    # ------------------------------------------------------------------

    async def _on_voice_completed(self, envelope: EventEnvelope) -> None:
        voice_id_str = str(envelope.payload.get("voice_generation_id", ""))
        agent_transcript = str(envelope.payload.get("transcript", ""))
        s = self._state

        voice_elapsed_ms = envelope.ts - s.turn_audio_committed_ms if s.turn_audio_committed_ms else 0
        total_turn_ms = envelope.ts - s.turn_speech_started_ms if s.turn_speech_started_ms else 0
        logger.info(
            "fsm_voice_completed",
            call_id=str(self._call_id),
            turn_seq=s.turn_seq,
            voice_id=voice_id_str,
            agent_text=agent_transcript[:100],
            voice_elapsed_ms=voice_elapsed_ms,
            total_turn_ms=total_turn_ms,
            fsm_state=self._agent_fsm.state.value,
        )

        if voice_id_str:
            voice_id = UUID(voice_id_str)
            if self._state.is_voice_cancelled(voice_id):
                logger.debug("late_voice_completed_ignored", voice_id=voice_id_str)
                return

            # Store agent response text in conversation buffer
            if agent_transcript:
                logger.info(
                    "agent_text_stored",
                    call_id=str(self._call_id),
                    seq=self._state.turn_seq,
                    agent_text=agent_transcript[:100],
                )
                self._conversation_buffer.update_agent_text(
                    self._state.turn_seq, agent_transcript,
                )

            # FSM: speaking → done
            if self._agent_fsm.state == AgentState.SPEAKING:
                self._agent_fsm.voice_completed(envelope.ts)
                logger.info(
                    "fsm_transition",
                    call_id=str(self._call_id),
                    turn_seq=s.turn_seq,
                    transition="speaking→done",
                    fsm_state=self._agent_fsm.state.value,
                    total_turn_ms=total_turn_ms,
                )
            elif self._agent_fsm.state == AgentState.ROUTING:
                # Direct route: model spoke directly (no specialist action)
                response_source = envelope.payload.get("response_source", "router")
                if response_source == "router" and not self._debug_route_result_emitted:
                    await self._send_debug("route_result", label="direct", route_type="direct")
                    self._debug_route_result_emitted = True
                # Transition routing → speaking → done
                self._agent_fsm.voice_started(envelope.ts)
                self._agent_fsm.voice_completed(envelope.ts)

            # Debug: generation_finish (fallback — skip if frontend audio_playback_end already arrived)
            if not self._debug_audio_playback_end_received:
                created_to_done_ms = envelope.payload.get("created_to_done_ms")
                finish_kwargs: dict[str, int] = {}
                if created_to_done_ms is not None:
                    finish_kwargs["created_to_done_ms"] = created_to_done_ms
                await self._send_debug("generation_finish", **finish_kwargs)

            # Persist voice generation update
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
            # Persist voice generation error
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
    # Tool result handling
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
    # Filler strategy
    # ------------------------------------------------------------------

    def _should_emit_filler(self) -> bool:
        # In full implementation, this checks thresholds config
        return False  # Disabled by default; enabled when thresholds loaded

    def _start_filler_timeout(self, voice_gen_id: UUID, ts: int) -> None:
        async def _auto_cancel_filler() -> None:
            await asyncio.sleep(1.2)  # 1200ms max
            if not self._state.is_voice_cancelled(voice_gen_id):
                self._state.cancelled_voice_generations.add(voice_gen_id)
                await self._emit_output(
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
