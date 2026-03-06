"""Unit tests for RealtimeVoiceProvider and StubVoiceProvider (task 11.2 supplement)."""

from __future__ import annotations

import pytest

from src.voice_runtime.realtime_provider import (
    RealtimeVoiceProvider,
    StubVoiceProvider,
    TranscriptionEvent,
)


class TestTranscriptionEvent:
    def test_immutable(self) -> None:
        event = TranscriptionEvent(text="hello", is_final=True)
        assert event.text == "hello"
        assert event.is_final is True


class TestStubVoiceProvider:
    @pytest.mark.asyncio
    async def test_send_audio_stores_frames(self) -> None:
        provider = StubVoiceProvider()
        await provider.send_audio(b"\x00" * 100)
        await provider.send_audio(b"\x01" * 50)
        assert len(provider._audio_received) == 2
        assert provider._audio_received[0] == b"\x00" * 100

    @pytest.mark.asyncio
    async def test_receive_transcription_yields_canned(self) -> None:
        provider = StubVoiceProvider(canned_transcription="Test input")
        events: list[TranscriptionEvent] = []
        async for event in provider.receive_transcription():
            events.append(event)
        assert len(events) == 1
        assert events[0].text == "Test input"
        assert events[0].is_final is True

    @pytest.mark.asyncio
    async def test_send_text_for_tts_yields_frames(self) -> None:
        provider = StubVoiceProvider(tts_frame_count=3, frame_delay_ms=1)
        frames: list[bytes] = []
        async for frame in provider.send_text_for_tts("Hello"):
            frames.append(frame)
        assert len(frames) == 3
        # Each frame is 1920 bytes of silence
        assert all(f == b"\x00" * 1920 for f in frames)

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        provider = StubVoiceProvider()
        assert provider._closed is False
        await provider.close()
        assert provider._closed is True
