"""OpenAI Realtime API implementation of RealtimeVoiceProvider."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
import orjson
import structlog
import websockets

from src.voice_runtime.realtime_provider import TranscriptionEvent

logger = structlog.get_logger()

# OpenAI Realtime API endpoint
_REALTIME_URL = "wss://api.openai.com/v1/realtime"


class OpenAIRealtimeProvider:
    """RealtimeVoiceProvider backed by the OpenAI Realtime API.

    Uses a single persistent WebSocket for bidirectional streaming STT and TTS.
    Optimized for minimum latency: fire-and-forget audio sends, async event reader.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini-realtime-preview") -> None:
        self._api_key = api_key
        self._model = model
        self._ws: websockets.ClientConnection | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stt_queue: asyncio.Queue[TranscriptionEvent | None] = asyncio.Queue()
        self._tts_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._closed = False

    async def connect(self) -> None:
        """Open WebSocket connection and start the background reader."""
        url = f"{_REALTIME_URL}?model={self._model}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self._ws = await websockets.connect(url, additional_headers=headers)
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info("openai_realtime_connected", model=self._model)

    async def close(self) -> None:
        """Close WebSocket and cancel reader task."""
        self._closed = True
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        # Signal consumers to stop
        await self._stt_queue.put(None)
        await self._tts_queue.put(None)
        logger.info("openai_realtime_closed")

    async def send_audio(self, frame: bytes) -> None:
        """Send a PCM16 audio frame to OpenAI (fire-and-forget).

        Downsamples from 48kHz to 24kHz, base64-encodes, and sends immediately.
        """
        if not self._ws or self._closed:
            return
        downsampled = self._downsample_48k_to_24k(frame)
        encoded = base64.b64encode(downsampled).decode("ascii")
        msg = orjson.dumps({"type": "input_audio_buffer.append", "audio": encoded})
        await self._ws.send(msg)

    async def commit_audio_buffer(self) -> None:
        """Commit the audio buffer to trigger transcription."""
        if not self._ws or self._closed:
            return
        msg = orjson.dumps({"type": "input_audio_buffer.commit"})
        await self._ws.send(msg)

    async def receive_transcription(self) -> AsyncIterator[TranscriptionEvent]:
        """Yield transcription events from the STT queue."""
        while True:
            event = await self._stt_queue.get()
            if event is None:
                break
            yield event

    async def send_text_for_tts(self, text: str) -> AsyncIterator[bytes]:
        """Send text for TTS and yield audio frames as they arrive."""
        if not self._ws or self._closed:
            return
        msg = orjson.dumps({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": text,
            },
        })
        await self._ws.send(msg)

        # Yield audio frames from the TTS queue until sentinel
        while True:
            frame = await self._tts_queue.get()
            if frame is None:
                break
            yield frame

    async def _read_loop(self) -> None:
        """Background task: read WebSocket messages and route to queues."""
        try:
            assert self._ws is not None  # noqa: S101
            async for raw_message in self._ws:
                if self._closed:
                    break
                try:
                    msg: dict[str, Any] = orjson.loads(raw_message)
                except Exception:
                    logger.warning("openai_realtime_invalid_message")
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "conversation.item.input_audio_transcription.completed":
                    transcript = msg.get("transcript", "")
                    if transcript:
                        event = TranscriptionEvent(text=transcript, is_final=True)
                        await self._stt_queue.put(event)

                elif msg_type == "response.audio.delta":
                    delta = msg.get("delta", "")
                    if delta:
                        audio_bytes = base64.b64decode(delta)
                        await self._tts_queue.put(audio_bytes)

                elif msg_type == "response.audio.done":
                    await self._tts_queue.put(None)

                elif msg_type == "error":
                    logger.error(
                        "openai_realtime_error",
                        error=msg.get("error", {}),
                    )

                else:
                    logger.debug("openai_realtime_event", type=msg_type)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("openai_realtime_reader_error", error=str(exc))
            # Signal consumers so they don't hang
            await self._stt_queue.put(None)
            await self._tts_queue.put(None)

    def _downsample_48k_to_24k(self, pcm_data: bytes) -> bytes:
        """Downsample 48kHz PCM16 to 24kHz by taking every 2nd sample."""
        samples = np.frombuffer(pcm_data, dtype=np.int16)
        downsampled = samples[::2]
        return downsampled.tobytes()
