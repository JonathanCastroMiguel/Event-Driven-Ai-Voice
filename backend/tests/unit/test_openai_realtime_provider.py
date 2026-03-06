"""Unit tests for OpenAIRealtimeProvider."""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import orjson
import pytest

from src.voice_runtime.openai_realtime_provider import OpenAIRealtimeProvider
from src.voice_runtime.realtime_provider import TranscriptionEvent


class _AsyncIterList:
    """Helper to make a list behave as an async iterator (for mock WebSocket)."""

    def __init__(self, items: list) -> None:
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


@pytest.fixture
def provider() -> OpenAIRealtimeProvider:
    return OpenAIRealtimeProvider(api_key="test-key", model="gpt-4o-mini-realtime-preview")


class TestSendAudio:
    async def test_sends_base64_encoded_audio(self, provider: OpenAIRealtimeProvider) -> None:
        mock_ws = AsyncMock()
        provider._ws = mock_ws
        provider._closed = False

        # 48kHz mono PCM16: 960 samples (20ms at 48kHz)
        samples_48k = np.arange(960, dtype=np.int16)
        frame = samples_48k.tobytes()

        await provider.send_audio(frame)

        mock_ws.send.assert_called_once()
        sent_data = orjson.loads(mock_ws.send.call_args[0][0])
        assert sent_data["type"] == "input_audio_buffer.append"
        assert "audio" in sent_data

        # Verify the audio was downsampled (960 -> 480 samples)
        decoded = base64.b64decode(sent_data["audio"])
        result_samples = np.frombuffer(decoded, dtype=np.int16)
        assert len(result_samples) == 480

    async def test_skips_when_disconnected(self, provider: OpenAIRealtimeProvider) -> None:
        provider._ws = None
        await provider.send_audio(b"\x00" * 1920)  # Should not raise


class TestCommitAudioBuffer:
    async def test_sends_commit_message(self, provider: OpenAIRealtimeProvider) -> None:
        mock_ws = AsyncMock()
        provider._ws = mock_ws
        provider._closed = False

        await provider.commit_audio_buffer()

        mock_ws.send.assert_called_once()
        sent_data = orjson.loads(mock_ws.send.call_args[0][0])
        assert sent_data["type"] == "input_audio_buffer.commit"

    async def test_skips_when_closed(self, provider: OpenAIRealtimeProvider) -> None:
        provider._ws = AsyncMock()
        provider._closed = True
        await provider.commit_audio_buffer()
        provider._ws.send.assert_not_called()


class TestReceiveTranscription:
    async def test_yields_events_from_queue(self, provider: OpenAIRealtimeProvider) -> None:
        event = TranscriptionEvent(text="hello", is_final=True)
        await provider._stt_queue.put(event)
        await provider._stt_queue.put(None)  # Sentinel

        results = []
        async for e in provider.receive_transcription():
            results.append(e)

        assert len(results) == 1
        assert results[0].text == "hello"
        assert results[0].is_final is True


class TestSendTextForTts:
    async def test_sends_response_create_and_yields_frames(
        self, provider: OpenAIRealtimeProvider
    ) -> None:
        mock_ws = AsyncMock()
        provider._ws = mock_ws
        provider._closed = False

        # Pre-populate TTS queue with audio frames
        audio_frame = b"\x01\x02\x03\x04"
        await provider._tts_queue.put(audio_frame)
        await provider._tts_queue.put(None)  # Sentinel

        results = []
        async for frame in provider.send_text_for_tts("Say hello"):
            results.append(frame)

        # Verify response.create was sent
        mock_ws.send.assert_called_once()
        sent_data = orjson.loads(mock_ws.send.call_args[0][0])
        assert sent_data["type"] == "response.create"
        assert sent_data["response"]["modalities"] == ["audio", "text"]

        # Verify audio frames were yielded
        assert len(results) == 1
        assert results[0] == audio_frame


class TestReadLoop:
    async def test_routes_transcription_to_stt_queue(
        self, provider: OpenAIRealtimeProvider
    ) -> None:
        transcription_msg = orjson.dumps({
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "test transcript",
        })

        mock_ws = _AsyncIterList([transcription_msg])
        provider._ws = mock_ws

        # Run reader in a task, let it process one message
        task = asyncio.create_task(provider._read_loop())
        await asyncio.sleep(0.05)
        provider._closed = True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        event = provider._stt_queue.get_nowait()
        assert isinstance(event, TranscriptionEvent)
        assert event.text == "test transcript"

    async def test_routes_audio_delta_to_tts_queue(
        self, provider: OpenAIRealtimeProvider
    ) -> None:
        audio_data = base64.b64encode(b"\x00\x01\x02").decode()
        audio_msg = orjson.dumps({
            "type": "response.audio.delta",
            "delta": audio_data,
        })

        mock_ws = _AsyncIterList([audio_msg])
        provider._ws = mock_ws

        task = asyncio.create_task(provider._read_loop())
        await asyncio.sleep(0.05)
        provider._closed = True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        frame = provider._tts_queue.get_nowait()
        assert frame == b"\x00\x01\x02"

    async def test_routes_audio_done_as_sentinel(
        self, provider: OpenAIRealtimeProvider
    ) -> None:
        done_msg = orjson.dumps({"type": "response.audio.done"})

        mock_ws = _AsyncIterList([done_msg])
        provider._ws = mock_ws

        task = asyncio.create_task(provider._read_loop())
        await asyncio.sleep(0.05)
        provider._closed = True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        sentinel = provider._tts_queue.get_nowait()
        assert sentinel is None


class TestDownsample:
    def test_48k_to_24k(self, provider: OpenAIRealtimeProvider) -> None:
        # 960 samples at 48kHz = 20ms
        samples = np.arange(960, dtype=np.int16)
        result = provider._downsample_48k_to_24k(samples.tobytes())
        result_samples = np.frombuffer(result, dtype=np.int16)

        assert len(result_samples) == 480
        # Every 2nd sample: 0, 2, 4, 6, ...
        np.testing.assert_array_equal(result_samples, samples[::2])

    def test_preserves_values(self, provider: OpenAIRealtimeProvider) -> None:
        samples = np.array([100, 200, 300, 400, 500, 600], dtype=np.int16)
        result = provider._downsample_48k_to_24k(samples.tobytes())
        result_samples = np.frombuffer(result, dtype=np.int16)
        np.testing.assert_array_equal(result_samples, [100, 300, 500])
