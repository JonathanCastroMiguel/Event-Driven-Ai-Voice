"""OpenAI Realtime Event Bridge.

Receives OpenAI Realtime events forwarded from the browser (via WebSocket)
and translates them to Coordinator EventEnvelopes (input direction).
Translates Coordinator output commands to OpenAI API messages and sends
them back to the browser for forwarding to the data channel (output direction).

Architecture:
  Browser ←WebRTC→ OpenAI (audio + data channel "oai-events")
  Browser ←WebSocket→ Backend (event forwarding, both directions)
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Coroutine
from uuid import UUID, uuid4

import orjson
import structlog

from src.routing.model_router import Department, parse_function_call_action
from src.voice_runtime.events import (
    EventEnvelope,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
)
from src.voice_runtime.types import EventSource

logger = structlog.get_logger()


class OpenAIRealtimeEventBridge:
    """Bridge between browser-forwarded OpenAI events and Coordinator.

    Implements the RealtimeClient protocol:
    - on_event() → registers callback for translated EventEnvelopes
    - send_voice_start() → response.create (sent to frontend)
    - send_voice_cancel() → response.cancel (sent to frontend)
    - close() → teardown
    """

    def __init__(self, call_id: UUID) -> None:
        self._call_id = call_id
        self._callback: Callable[[EventEnvelope], Coroutine[Any, Any, None]] | None = (
            None
        )
        self._frontend_ws: Any | None = None  # FastAPI WebSocket
        self._closed = False
        self._active_voice_generation_id: UUID | None = None
        self._response_transcript_buffer: str = ""
        self._response_create_sent_ms: int = 0
        self._response_created_ms: int = 0
        self._current_response_source: str = "router"
        self._function_call_received: bool = False
        self._pending_direct_audio: bool = False
        self._last_instructions: str = ""
        self._pending_fn_call_id: str = ""
        self._pending_fn_item_id: str = ""

    # ------------------------------------------------------------------
    # RealtimeClient protocol: on_event
    # ------------------------------------------------------------------

    def on_event(
        self,
        callback: Callable[[EventEnvelope], Coroutine[Any, Any, None]],
    ) -> None:
        """Register a callback for events coming from OpenAI (via frontend)."""
        self._callback = callback

    # ------------------------------------------------------------------
    # Frontend WebSocket management
    # ------------------------------------------------------------------

    def set_frontend_ws(self, ws: Any | None) -> None:
        """Set or clear the frontend WebSocket connection."""
        self._frontend_ws = ws
        if ws is not None:
            logger.info("bridge_frontend_ws_connected", call_id=str(self._call_id))
        else:
            logger.info("bridge_frontend_ws_disconnected", call_id=str(self._call_id))

    async def handle_frontend_event(self, data: dict[str, Any]) -> None:
        """Process a raw OpenAI event forwarded from the frontend."""
        await self._translate_event(data)

    async def close(self) -> None:
        """Clean up bridge state."""
        self._closed = True
        self._frontend_ws = None
        logger.info("realtime_bridge_closed", call_id=str(self._call_id))

    # ------------------------------------------------------------------
    # RealtimeClient protocol: send_voice_start
    # ------------------------------------------------------------------

    async def send_voice_start(self, event: RealtimeVoiceStart) -> None:
        """Translate RealtimeVoiceStart → single response.create.

        Instructions are passed directly in response.create to avoid the
        ~500ms round-trip of a separate session.update.
        """
        if self._frontend_ws is None:
            logger.warning("bridge_send_no_ws", call_id=str(self._call_id))
            return

        self._active_voice_generation_id = event.voice_generation_id
        self._response_create_sent_ms = _now_ms()
        self._response_created_ms = 0
        self._current_response_source = event.response_source

        if isinstance(event.prompt, dict):
            # Already a complete response.create payload from RouterPromptBuilder
            resp = event.prompt.get("response", {})
            instructions = resp.get("instructions", "")
            has_history = "Conversation history:" in instructions
            has_tools = bool(resp.get("tools"))
            self._last_instructions = instructions
            logger.info(
                "bridge_sending_response_create",
                call_id=str(self._call_id),
                prompt_type="dict",
                has_history=has_history,
                has_tools=has_tools,
                instructions_len=len(instructions),
            )
            await self.send_to_frontend(event.prompt)
        else:
            response_create: dict[str, Any] = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": event.prompt if isinstance(event.prompt, str) else "",
                },
            }
            await self.send_to_frontend(response_create)

        logger.info(
            "bridge_voice_start_sent",
            call_id=str(self._call_id),
            voice_generation_id=str(event.voice_generation_id),
        )

    # ------------------------------------------------------------------
    # RealtimeClient protocol: send_voice_cancel
    # ------------------------------------------------------------------

    async def send_voice_cancel(self, event: RealtimeVoiceCancel) -> None:
        """Translate RealtimeVoiceCancel → response.cancel (sent to frontend)."""
        if self._frontend_ws is None:
            logger.warning("bridge_cancel_no_ws", call_id=str(self._call_id))
            return

        await self.send_to_frontend({"type": "response.cancel"})
        logger.info(
            "bridge_voice_cancel_sent",
            call_id=str(self._call_id),
            voice_generation_id=str(event.voice_generation_id),
        )

    # ------------------------------------------------------------------
    # Event translation: OpenAI → Coordinator EventEnvelopes
    # ------------------------------------------------------------------

    async def _translate_event(self, data: dict[str, Any]) -> None:
        """Translate an OpenAI Realtime event to an EventEnvelope."""
        event_type = data.get("type", "")

        if event_type == "error":
            logger.error(
                "bridge_openai_error",
                call_id=str(self._call_id),
                error=data.get("error"),
            )
        elif event_type == "session.updated":
            logger.info(
                "bridge_session_updated",
                call_id=str(self._call_id),
                session_keys=list(data.get("session", {}).keys()),
            )
        else:
            logger.info(
                "bridge_raw_event",
                call_id=str(self._call_id),
                event_type=event_type,
            )

        envelope: EventEnvelope | None = None

        if event_type == "input_audio_buffer.speech_started":
            envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=self._call_id,
                ts=_now_ms(),
                type="speech_started",
                payload={},
                source=EventSource.REALTIME,
            )

        elif event_type == "input_audio_buffer.speech_stopped":
            envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=self._call_id,
                ts=_now_ms(),
                type="speech_stopped",
                payload={},
                source=EventSource.REALTIME,
            )

        elif event_type == "input_audio_buffer.committed":
            envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=self._call_id,
                ts=_now_ms(),
                type="audio_committed",
                payload={},
                source=EventSource.REALTIME,
            )

        elif event_type == "response.created":
            self._response_transcript_buffer = ""
            self._response_created_ms = _now_ms()
            self._function_call_received = False
            send_to_created_ms = self._response_created_ms - self._response_create_sent_ms if self._response_create_sent_ms else 0
            logger.info(
                "bridge_response_created",
                call_id=str(self._call_id),
                response_id=data.get("response", {}).get("id"),
                send_to_created_ms=send_to_created_ms,
            )
            payload: dict[str, Any] = {
                "response_source": self._current_response_source,
            }
            if send_to_created_ms:
                payload["send_to_created_ms"] = send_to_created_ms
            envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=self._call_id,
                ts=_now_ms(),
                type="response_created",
                payload=payload,
                source=EventSource.REALTIME,
            )

        elif event_type == "response.audio_transcript.delta":
            delta = str(data.get("delta", ""))
            self._response_transcript_buffer += delta

        elif event_type == "response.function_call_arguments.done":
            # The model called route_to_specialist — extract routing action.
            # This is never vocalized (separate channel from audio).
            fn_name = str(data.get("name", ""))
            fn_args = str(data.get("arguments", ""))
            # Capture OpenAI's internal call_id and item_id for acknowledging
            # the function call before sending follow-up response.create.
            self._pending_fn_call_id = str(data.get("call_id", ""))
            self._pending_fn_item_id = str(data.get("item_id", ""))
            logger.info(
                "bridge_function_call_received",
                call_id=str(self._call_id),
                function_name=fn_name,
                arguments=fn_args[:200],
            )
            action = parse_function_call_action(fn_name, fn_args)
            if action is not None:
                if action.department == Department.DIRECT:
                    # Direct response — tool_choice=required suppresses audio,
                    # so we flag for a second response.create (audio-only, no tools)
                    # that will be sent on response.done.
                    self._pending_direct_audio = True
                    logger.info(
                        "bridge_direct_response_via_tool",
                        call_id=str(self._call_id),
                        summary=action.summary[:100],
                    )
                else:
                    self._function_call_received = True
                    voice_id = self._active_voice_generation_id
                    self._active_voice_generation_id = None
                    envelope = EventEnvelope(
                        event_id=uuid4(),
                        call_id=self._call_id,
                        ts=_now_ms(),
                        type="model_router_action",
                        payload={
                            "department": action.department.value,
                            "summary": action.summary,
                            "filler_text": _clean_transcript(self._response_transcript_buffer),
                        },
                        source=EventSource.REALTIME,
                    )

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = str(data.get("transcript", "")).strip()
            if not transcript:
                return
            envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=self._call_id,
                ts=_now_ms(),
                type="transcript_final",
                payload={"text": transcript},
                source=EventSource.REALTIME,
            )

        elif event_type == "response.done":
            now = _now_ms()
            created_to_done_ms = now - self._response_created_ms if self._response_created_ms else 0
            total_response_ms = now - self._response_create_sent_ms if self._response_create_sent_ms else 0
            response_obj = data.get("response", {})
            response_status = response_obj.get("status", "completed")
            status_details = response_obj.get("status_details")
            logger.info(
                "bridge_response_done",
                call_id=str(self._call_id),
                transcript_len=len(self._response_transcript_buffer),
                transcript_preview=self._response_transcript_buffer[:100],
                created_to_done_ms=created_to_done_ms,
                total_response_ms=total_response_ms,
                status=response_status,
                status_details=status_details,
                function_call_received=self._function_call_received,
                pending_direct_audio=self._pending_direct_audio,
            )

            # Two-step direct response: tool_choice=required produced only
            # a tool call (no audio).  Send a function call output to acknowledge
            # the tool call, then a second response.create WITHOUT tools so the
            # model generates the actual spoken reply.
            if self._pending_direct_audio:
                self._pending_direct_audio = False
                self._response_transcript_buffer = ""

                # Acknowledge the function call so OpenAI accepts the next response.create
                if self._pending_fn_call_id:
                    fn_output: dict[str, Any] = {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": self._pending_fn_call_id,
                            "output": '{"status":"ok"}',
                        },
                    }
                    logger.info(
                        "bridge_direct_fn_ack",
                        call_id=str(self._call_id),
                        fn_call_id=self._pending_fn_call_id,
                    )
                    await self.send_to_frontend(fn_output)
                    self._pending_fn_call_id = ""
                    self._pending_fn_item_id = ""

                self._response_create_sent_ms = _now_ms()
                self._response_created_ms = 0
                second_response: dict[str, Any] = {
                    "type": "response.create",
                    "response": {
                        "modalities": ["text", "audio"],
                        "instructions": self._last_instructions,
                        "temperature": 0.8,
                    },
                }
                logger.info(
                    "bridge_direct_audio_followup",
                    call_id=str(self._call_id),
                    instructions_len=len(self._last_instructions),
                )
                await self.send_to_frontend(second_response)
                return  # wait for second response.done

            voice_id = self._active_voice_generation_id
            transcript = _clean_transcript(self._response_transcript_buffer)
            self._response_transcript_buffer = ""

            if self._function_call_received:
                # Routing was dispatched via function call.
                # Do NOT emit voice_generation_completed here — the specialist's
                # response.done will emit it with the correct transcript.
                # The coordinator already transitioned FSM via model_router_action.
                pass
            elif voice_id is not None:
                # Normal direct response (no function call).
                vgc_payload = {
                    "voice_generation_id": str(voice_id),
                    "transcript": transcript,
                    "response_source": self._current_response_source,
                }
                if created_to_done_ms:
                    vgc_payload["created_to_done_ms"] = created_to_done_ms
                envelope = EventEnvelope(
                    event_id=uuid4(),
                    call_id=self._call_id,
                    ts=_now_ms(),
                    type="voice_generation_completed",
                    payload=vgc_payload,
                    source=EventSource.REALTIME,
                )
                self._active_voice_generation_id = None

        elif event_type == "response.failed":
            logger.error(
                "bridge_response_failed",
                call_id=str(self._call_id),
                error=data.get("error"),
            )
            voice_id = self._active_voice_generation_id
            error_detail = data.get("error", {})
            error_msg = str(
                error_detail.get("message", "unknown_error")
                if isinstance(error_detail, dict)
                else error_detail
            )
            if voice_id is not None:
                envelope = EventEnvelope(
                    event_id=uuid4(),
                    call_id=self._call_id,
                    ts=_now_ms(),
                    type="voice_generation_error",
                    payload={
                        "voice_generation_id": str(voice_id),
                        "error": error_msg,
                    },
                    source=EventSource.REALTIME,
                )
                self._active_voice_generation_id = None

        if envelope is not None:
            logger.info(
                "bridge_translated_event",
                call_id=str(self._call_id),
                envelope_type=envelope.type,
            )

        if envelope is not None and self._callback is not None:
            try:
                await self._callback(envelope)
            except Exception:
                logger.exception(
                    "bridge_callback_error",
                    call_id=str(self._call_id),
                    event_type=event_type,
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def send_to_frontend(self, data: dict[str, Any]) -> None:
        """Send a JSON message to the frontend via WebSocket."""
        if self._frontend_ws is not None:
            try:
                await self._frontend_ws.send_text(orjson.dumps(data).decode())
            except Exception:
                logger.warning(
                    "bridge_send_to_frontend_error",
                    call_id=str(self._call_id),
                    exc_info=True,
                )


def _now_ms() -> int:
    """Current time in epoch milliseconds."""
    return int(time.time() * 1000)


# Pattern to detect leaked function call text in model audio transcript.
# The model sometimes vocalizes function calls like:
#   "(functions.route_to_specialist(department="billing", ...))"
#   "(functions route_to_specialist ...)"
# This always appears at the end of the transcript, so we truncate from
# the first match to the end of the string.
_LEAKED_FUNC_RE = re.compile(
    r"\s*\(?functions?[.\s]route_to_specialist.*|route_to_specialist.*|\(\s*functions\b.*",
    re.IGNORECASE | re.DOTALL,
)


def _clean_transcript(text: str) -> str:
    """Remove leaked function call syntax from transcript text.

    Truncates everything from the first mention of route_to_specialist
    to the end of the string, since the leak always appears at the tail.
    """
    cleaned = _LEAKED_FUNC_RE.sub("", text).strip()
    if cleaned != text.strip():
        logger.warning("transcript_function_leak_cleaned", original_len=len(text), cleaned_len=len(cleaned))
    return cleaned
