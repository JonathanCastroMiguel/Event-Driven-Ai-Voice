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

import asyncio
from typing import Any, Callable, Coroutine
from uuid import UUID, uuid4

import orjson
import structlog

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
    - send_voice_start() → session.update + response.create (sent to frontend)
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

        if isinstance(event.prompt, list):
            system_parts: list[str] = []
            user_text = ""
            for msg in event.prompt:
                if msg.get("role") == "system":
                    system_parts.append(str(msg.get("content", "")))
                elif msg.get("role") == "user":
                    user_text = str(msg.get("content", ""))

            instructions = "\n\n".join(system_parts)

            response_create: dict[str, Any] = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": instructions,
                },
            }
            if user_text:
                response_create["response"]["input"] = [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_text}],
                    }
                ]
            await self.send_to_frontend(response_create)
        else:
            response_create = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": event.prompt,
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
            voice_id = self._active_voice_generation_id
            if voice_id is not None:
                envelope = EventEnvelope(
                    event_id=uuid4(),
                    call_id=self._call_id,
                    ts=_now_ms(),
                    type="voice_generation_completed",
                    payload={"voice_generation_id": str(voice_id)},
                    source=EventSource.REALTIME,
                )
                self._active_voice_generation_id = None

        elif event_type == "response.failed":
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
    import time

    return int(time.time() * 1000)
