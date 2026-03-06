"""RealtimeVoiceProvider Protocol and stub implementation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class TranscriptionEvent:
    """A transcription result from the STT provider."""

    text: str
    is_final: bool


class RealtimeVoiceProvider(Protocol):
    """Protocol for streaming STT/TTS providers (OpenAI Realtime, Deepgram, etc.)."""

    async def send_audio(self, frame: bytes) -> None:
        """Send an audio frame to the STT engine."""
        ...

    async def receive_transcription(self) -> AsyncIterator[TranscriptionEvent]:
        """Yield transcription events as they arrive from STT."""
        ...

    async def send_text_for_tts(self, text: str) -> AsyncIterator[bytes]:
        """Send text for TTS and yield audio frames as they are generated."""
        ...

    async def close(self) -> None:
        """Clean up provider resources."""
        ...


class StubVoiceProvider:
    """Stub provider for testing — returns canned transcriptions and silent audio."""

    def __init__(
        self,
        canned_transcription: str = "Hello, I need help.",
        tts_frame_count: int = 5,
        frame_delay_ms: float = 20.0,
    ) -> None:
        self._canned_text = canned_transcription
        self._tts_frame_count = tts_frame_count
        self._frame_delay_s = frame_delay_ms / 1000.0
        self._audio_received: list[bytes] = []
        self._closed = False

    async def send_audio(self, frame: bytes) -> None:
        """Store received audio frames for assertions."""
        self._audio_received.append(frame)

    async def receive_transcription(self) -> AsyncIterator[TranscriptionEvent]:
        """Yield a single canned transcription after a short delay."""
        await asyncio.sleep(0.05)
        yield TranscriptionEvent(text=self._canned_text, is_final=True)

    async def send_text_for_tts(self, text: str) -> AsyncIterator[bytes]:
        """Yield silent audio frames (960 samples of 16-bit silence = 1920 bytes)."""
        silent_frame = b"\x00" * 1920
        for _ in range(self._tts_frame_count):
            await asyncio.sleep(self._frame_delay_s)
            yield silent_frame

    async def close(self) -> None:
        """Mark as closed."""
        self._closed = True
