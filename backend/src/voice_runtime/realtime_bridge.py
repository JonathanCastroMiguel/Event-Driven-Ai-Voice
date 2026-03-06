"""RealtimeVoiceBridge — connects WebRTC audio to Coordinator via RealtimeVoiceProvider."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, Callable, Coroutine
from uuid import UUID, uuid4

import structlog

from src.voice_runtime.events import (
    EventEnvelope,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
    VoiceGenerationCompleted,
    VoiceGenerationError,
)
from src.voice_runtime.realtime_provider import RealtimeVoiceProvider, TranscriptionEvent
from src.voice_runtime.types import EventSource

if TYPE_CHECKING:
    from aiortc import MediaStreamTrack, RTCDataChannel, RTCPeerConnection

logger = structlog.get_logger()


class RealtimeVoiceBridge:
    """Bridges WebRTC audio ↔ RealtimeVoiceProvider ↔ Coordinator.

    Implements the RealtimeClient Protocol so the Coordinator can use it
    as a drop-in replacement for StubRealtimeClient.
    """

    def __init__(
        self,
        call_id: UUID,
        provider: RealtimeVoiceProvider,
        control_channel: RTCDataChannel,
        debug_channel: RTCDataChannel,
    ) -> None:
        self._call_id = call_id
        self._provider = provider
        self._control_channel = control_channel
        self._debug_channel = debug_channel
        self._callback: Callable[[EventEnvelope], Coroutine[Any, Any, None]] | None = None
        self._debug_enabled = False
        self._active_tts_task: asyncio.Task[None] | None = None
        self._cancelled_voice_ids: set[UUID] = set()
        self._stt_task: asyncio.Task[None] | None = None
        self._audio_forward_task: asyncio.Task[None] | None = None

        # Wire up control channel message handler
        @control_channel.on("message")
        def on_control_message(message: str) -> None:
            asyncio.ensure_future(self._handle_control_message(message))

    # -----------------------------------------------------------------
    # RealtimeClient Protocol implementation
    # -----------------------------------------------------------------

    async def send_voice_start(self, event: RealtimeVoiceStart) -> None:
        """Start TTS streaming for an agent response."""
        voice_id = event.voice_generation_id

        async def _tts_stream() -> None:
            try:
                async for _frame in self._provider.send_text_for_tts(event.prompt):
                    if voice_id in self._cancelled_voice_ids:
                        logger.debug("tts_cancelled_mid_stream", voice_generation_id=str(voice_id))
                        return
                    # In a full implementation, frames would be pushed to the
                    # WebRTC audio track. For now we consume them.

                # TTS completed — notify Coordinator
                if voice_id not in self._cancelled_voice_ids:
                    completed = VoiceGenerationCompleted(
                        call_id=self._call_id,
                        voice_generation_id=voice_id,
                        ts=_now_ms(),
                    )
                    envelope = EventEnvelope(
                        event_id=uuid4(),
                        call_id=self._call_id,
                        ts=completed.ts,
                        type="voice_generation_completed",
                        payload={"voice_generation_id": str(voice_id)},
                        source=EventSource.REALTIME,
                    )
                    if self._callback:
                        await self._callback(envelope)
            except Exception as exc:
                logger.error("tts_error", voice_generation_id=str(voice_id), error=str(exc))
                error_event = VoiceGenerationError(
                    call_id=self._call_id,
                    voice_generation_id=voice_id,
                    error=str(exc),
                    ts=_now_ms(),
                )
                envelope = EventEnvelope(
                    event_id=uuid4(),
                    call_id=self._call_id,
                    ts=error_event.ts,
                    type="voice_generation_error",
                    payload={"voice_generation_id": str(voice_id), "error": str(exc)},
                    source=EventSource.REALTIME,
                )
                if self._callback:
                    await self._callback(envelope)

        self._active_tts_task = asyncio.create_task(_tts_stream())
        logger.debug("tts_started", voice_generation_id=str(voice_id))

    async def send_voice_cancel(self, event: RealtimeVoiceCancel) -> None:
        """Cancel an active TTS stream."""
        self._cancelled_voice_ids.add(event.voice_generation_id)
        if self._active_tts_task and not self._active_tts_task.done():
            self._active_tts_task.cancel()
        logger.debug("tts_cancelled", voice_generation_id=str(event.voice_generation_id))

    def on_event(
        self,
        callback: Callable[[EventEnvelope], Coroutine[Any, Any, None]],
    ) -> None:
        """Register the Coordinator's event callback."""
        self._callback = callback

    async def close(self) -> None:
        """Clean up all async tasks and provider resources."""
        if self._stt_task and not self._stt_task.done():
            self._stt_task.cancel()
        if self._audio_forward_task and not self._audio_forward_task.done():
            self._audio_forward_task.cancel()
        if self._active_tts_task and not self._active_tts_task.done():
            self._active_tts_task.cancel()
        await self._provider.close()

    # -----------------------------------------------------------------
    # Audio forwarding (WebRTC → Provider)
    # -----------------------------------------------------------------

    def start_audio_forwarding(self, track: MediaStreamTrack) -> None:
        """Start forwarding audio frames from WebRTC track to the provider."""

        async def _forward() -> None:
            try:
                while True:
                    frame = await track.recv()
                    # frame.to_ndarray() gives PCM samples; convert to bytes
                    pcm_data = frame.to_ndarray().tobytes()
                    await self._provider.send_audio(pcm_data)
            except Exception:
                logger.debug("audio_forwarding_ended", call_id=str(self._call_id))

        self._audio_forward_task = asyncio.create_task(_forward())

    # -----------------------------------------------------------------
    # STT listener (Provider → Coordinator)
    # -----------------------------------------------------------------

    def start_stt_listener(self) -> None:
        """Start listening for transcriptions from the provider."""

        async def _listen() -> None:
            try:
                async for event in self._provider.receive_transcription():
                    # Forward transcription to browser
                    self._send_control_message({
                        "type": "transcription",
                        "text": event.text,
                        "is_final": event.is_final,
                    })

                    # Only dispatch final transcriptions to Coordinator
                    if event.is_final and self._callback:
                        envelope = EventEnvelope(
                            event_id=uuid4(),
                            call_id=self._call_id,
                            ts=_now_ms(),
                            type="transcript_final",
                            payload={"text": event.text},
                            source=EventSource.REALTIME,
                        )
                        await self._callback(envelope)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.error("stt_listener_error", error=str(exc))

        self._stt_task = asyncio.create_task(_listen())

    # -----------------------------------------------------------------
    # Control channel message handling
    # -----------------------------------------------------------------

    async def _handle_control_message(self, message: str) -> None:
        """Handle messages from the browser's control DataChannel."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning("invalid_control_message", message=message)
            return

        msg_type = data.get("type")
        ts = data.get("ts", _now_ms())

        if msg_type == "speech_started":
            envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=self._call_id,
                ts=ts,
                type="speech_started",
                payload={},
                source=EventSource.REALTIME,
            )
            if self._callback:
                await self._callback(envelope)

        elif msg_type == "speech_ended":
            envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=self._call_id,
                ts=ts,
                type="speech_stopped",
                payload={},
                source=EventSource.REALTIME,
            )
            if self._callback:
                await self._callback(envelope)
            # Trigger transcription of accumulated audio
            if hasattr(self._provider, "commit_audio_buffer"):
                await self._provider.commit_audio_buffer()

        elif msg_type == "debug_enable":
            self._debug_enabled = True
            logger.debug("debug_enabled", call_id=str(self._call_id))

        elif msg_type == "debug_disable":
            self._debug_enabled = False
            logger.debug("debug_disabled", call_id=str(self._call_id))

    # -----------------------------------------------------------------
    # Debug event forwarding
    # -----------------------------------------------------------------

    async def emit_debug(self, event: dict[str, Any]) -> None:
        """Forward a debug event to the browser if debug mode is enabled."""
        if not self._debug_enabled:
            return
        try:
            self._debug_channel.send(json.dumps(event))
        except Exception:
            pass  # Debug delivery is best-effort

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _send_control_message(self, data: dict[str, Any]) -> None:
        """Send a JSON message on the control DataChannel."""
        try:
            self._control_channel.send(json.dumps(data))
        except Exception:
            pass  # Best-effort delivery


def _now_ms() -> int:
    """Current time in epoch milliseconds."""
    return int(time.time() * 1000)
