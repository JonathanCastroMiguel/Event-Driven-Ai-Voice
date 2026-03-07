from __future__ import annotations

import asyncio
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

    async def _emit_debug(self, event: dict[str, Any]) -> None:
        """Emit a debug event if a callback is registered."""
        if self._debug_callback is not None:
            try:
                await self._debug_callback(event)
            except Exception:
                pass  # Debug is best-effort

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
                case "audio_committed":
                    await self._on_audio_committed(envelope)
                case "transcript_final":
                    await self._on_transcript_final(envelope)
                case "model_router_action":
                    await self._on_model_router_action(envelope)
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

    async def _on_speech_started(self, envelope: EventEnvelope) -> None:
        s = self._state

        # Cancel active voice if any (record barge-in metric)
        voice_id = s.cancel_active_voice()
        if voice_id is not None:
            BARGE_IN_TOTAL.inc()
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

    # ------------------------------------------------------------------
    # Audio committed — primary turn trigger (model-as-router)
    # ------------------------------------------------------------------

    async def _on_audio_committed(self, envelope: EventEnvelope) -> None:
        """Handle audio_committed: finalize turn, build router prompt, emit response.create."""
        s = self._state

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

                # FSM: idle → routing
                self._agent_fsm.start_routing(agent_generation_id, envelope.ts)

                # Build router prompt with conversation history
                history = self._conversation_buffer.format_messages()

                if self._router_prompt_builder is not None:
                    payload = self._router_prompt_builder.build_response_create(history)
                else:
                    # Fallback when no router prompt builder configured
                    payload = {
                        "type": "response.create",
                        "response": {
                            "modalities": ["text", "audio"],
                            "instructions": "You are a helpful voice assistant.",
                        },
                    }
                    if history:
                        payload["response"]["input"] = [
                            {
                                "type": "message",
                                "role": msg.get("role", "user"),
                                "content": [{"type": "input_text", "text": msg.get("content", "")}],
                            }
                            for msg in history
                        ]

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

                logger.info(
                    "model_router_dispatched",
                    call_id=str(self._call_id),
                    turn_id=str(turn_id),
                    agent_generation_id=str(agent_generation_id),
                    has_history=len(history) > 0,
                )

    # ------------------------------------------------------------------
    # Transcript final — async logging only
    # ------------------------------------------------------------------

    async def _on_transcript_final(self, envelope: EventEnvelope) -> None:
        """Store transcript for logging, persistence, and debug display. No routing."""
        text = str(envelope.payload.get("text", ""))
        self._turn_manager.handle_transcript_final(text, envelope.ts)

        # Append to conversation buffer for subsequent turns' history
        if text and self._state.active_turn_id is not None:
            self._conversation_buffer.append(
                TurnEntry(
                    seq=self._state.turn_seq,
                    user_text=text,
                )
            )

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
        """Handle model_router_action: the model returned a JSON action for specialist routing."""
        s = self._state
        department = str(envelope.payload.get("department", ""))
        summary = str(envelope.payload.get("summary", ""))

        if s.active_agent_generation_id is None:
            logger.warning("model_router_action_without_active_generation")
            return

        if s.is_generation_cancelled(s.active_agent_generation_id):
            logger.debug("late_model_router_action_ignored")
            return

        # FSM: routing → waiting_tools
        self._agent_fsm.specialist_action(envelope.ts)

        logger.info(
            "model_router_action_received",
            call_id=str(self._call_id),
            department=department,
            summary=summary,
            agent_generation_id=str(s.active_agent_generation_id),
        )

        # Filler strategy
        if self._should_emit_filler():
            FILLER_EMITTED_TOTAL.inc()
            filler_voice_id = uuid4()
            await self._emit_output(
                RealtimeVoiceStart(
                    call_id=self._call_id,
                    agent_generation_id=s.active_agent_generation_id,
                    voice_generation_id=filler_voice_id,
                    prompt="Un momento, por favor.",
                    ts=envelope.ts,
                )
            )
            self._start_filler_timeout(filler_voice_id, envelope.ts)

        # Execute specialist tool
        tool_request_id = uuid4()
        tool_result = await self._tool_executor.execute(
            call_id=self._call_id,
            agent_generation_id=s.active_agent_generation_id,
            tool_request_id=tool_request_id,
            tool_name=f"specialist_{department}",
            args={"summary": summary},
            timeout_ms=5000,
        )

        # FSM: waiting_tools → speaking
        self._agent_fsm.tool_result(envelope.ts)

        # Cancel filler if still running
        self._cancel_filler()

        # Emit specialist response voice
        voice_gen_id = uuid4()
        s.active_voice_generation_id = voice_gen_id

        # Build specialist response prompt
        history = self._conversation_buffer.format_messages()
        tool_payload_str = str(tool_result.payload) if tool_result.ok else "Tool unavailable"
        specialist_prompt: list[dict[str, str]] = [
            {"role": "system", "content": self._policies.base_system},
            {"role": "system", "content": f"The user needs help with {department}. Tool result: {tool_payload_str}"},
            *history,
            {"role": "user", "content": summary},
        ]

        await self._emit_output(
            RealtimeVoiceStart(
                call_id=self._call_id,
                agent_generation_id=s.active_agent_generation_id,
                voice_generation_id=voice_gen_id,
                prompt=specialist_prompt,
                ts=envelope.ts,
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
        if voice_id_str:
            voice_id = UUID(voice_id_str)
            if self._state.is_voice_cancelled(voice_id):
                logger.debug("late_voice_completed_ignored", voice_id=voice_id_str)
                return

            # FSM: speaking → done
            if self._agent_fsm.state == AgentState.SPEAKING:
                self._agent_fsm.voice_completed(envelope.ts)

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
