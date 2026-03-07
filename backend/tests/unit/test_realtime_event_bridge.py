"""Unit tests for OpenAIRealtimeEventBridge.

Tests event translation (input/output), frontend WebSocket lifecycle,
and error handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import orjson
import pytest

from src.voice_runtime.events import (
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
)
from src.voice_runtime.realtime_event_bridge import OpenAIRealtimeEventBridge


@pytest.fixture
def call_id():
    return uuid4()


@pytest.fixture
def bridge(call_id):
    return OpenAIRealtimeEventBridge(call_id=call_id)


def _make_mock_ws() -> AsyncMock:
    """Create a mock FastAPI WebSocket."""
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# Input event translation: OpenAI → Coordinator
# ---------------------------------------------------------------------------


class TestInputEventTranslation:
    async def test_speech_started(self, bridge, call_id):
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        await bridge._translate_event({"type": "input_audio_buffer.speech_started"})

        assert len(received) == 1
        assert received[0].type == "speech_started"
        assert received[0].call_id == call_id
        assert received[0].source.value == "realtime"

    async def test_speech_stopped(self, bridge, call_id):
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        await bridge._translate_event({"type": "input_audio_buffer.speech_stopped"})

        assert len(received) == 1
        assert received[0].type == "speech_stopped"
        assert received[0].call_id == call_id

    async def test_transcript_final(self, bridge, call_id):
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        await bridge._translate_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "hola buenos dias",
        })

        assert len(received) == 1
        assert received[0].type == "transcript_final"
        assert received[0].payload["text"] == "hola buenos dias"

    async def test_empty_transcript_ignored(self, bridge):
        callback = AsyncMock()
        bridge.on_event(callback)

        await bridge._translate_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "   ",
        })

        callback.assert_not_awaited()

    async def test_voice_generation_completed(self, bridge, call_id):
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        voice_id = uuid4()
        bridge._active_voice_generation_id = voice_id

        await bridge._translate_event({"type": "response.done"})

        assert len(received) == 1
        assert received[0].type == "voice_generation_completed"
        assert received[0].payload["voice_generation_id"] == str(voice_id)
        assert bridge._active_voice_generation_id is None

    async def test_voice_generation_completed_no_active_id(self, bridge):
        callback = AsyncMock()
        bridge.on_event(callback)

        await bridge._translate_event({"type": "response.done"})

        callback.assert_not_awaited()

    async def test_voice_generation_error(self, bridge, call_id):
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        voice_id = uuid4()
        bridge._active_voice_generation_id = voice_id

        await bridge._translate_event({
            "type": "response.failed",
            "error": {"message": "rate_limit_exceeded"},
        })

        assert len(received) == 1
        assert received[0].type == "voice_generation_error"
        assert received[0].payload["error"] == "rate_limit_exceeded"
        assert bridge._active_voice_generation_id is None

    async def test_unknown_event_ignored(self, bridge):
        callback = AsyncMock()
        bridge.on_event(callback)

        await bridge._translate_event({"type": "session.created"})

        callback.assert_not_awaited()

    async def test_callback_error_does_not_crash(self, bridge):
        callback = AsyncMock(side_effect=RuntimeError("boom"))
        bridge.on_event(callback)

        # Should not raise
        await bridge._translate_event({"type": "input_audio_buffer.speech_started"})


# ---------------------------------------------------------------------------
# Input via handle_frontend_event
# ---------------------------------------------------------------------------


class TestHandleFrontendEvent:
    async def test_frontend_event_calls_translate(self, bridge):
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        await bridge.handle_frontend_event(
            {"type": "input_audio_buffer.speech_started"}
        )

        assert len(received) == 1
        assert received[0].type == "speech_started"


# ---------------------------------------------------------------------------
# Output event translation: Coordinator → OpenAI (via frontend)
# ---------------------------------------------------------------------------


class TestOutputEventTranslation:
    async def test_send_voice_start_with_message_array(self, bridge, call_id):
        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)

        voice_id = uuid4()
        gen_id = uuid4()
        event = RealtimeVoiceStart(
            call_id=call_id,
            agent_generation_id=gen_id,
            voice_generation_id=voice_id,
            prompt=[
                {"role": "system", "content": "You are helpful."},
                {"role": "system", "content": "Greet warmly."},
                {"role": "user", "content": "hola"},
            ],
            ts=1000,
        )

        await bridge.send_voice_start(event)

        assert mock_ws.send_text.call_count == 1

        # Single response.create with instructions inline
        msg = orjson.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert msg["type"] == "response.create"
        assert "You are helpful." in msg["response"]["instructions"]
        assert "Greet warmly." in msg["response"]["instructions"]
        assert msg["response"]["input"][0]["content"][0]["text"] == "hola"

        # Voice generation ID tracked
        assert bridge._active_voice_generation_id == voice_id

    async def test_send_voice_start_with_string_prompt(self, bridge, call_id):
        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)

        event = RealtimeVoiceStart(
            call_id=call_id,
            agent_generation_id=uuid4(),
            voice_generation_id=uuid4(),
            prompt="Un momento, por favor.",
            ts=1000,
        )

        await bridge.send_voice_start(event)

        assert mock_ws.send_text.call_count == 1
        msg = orjson.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert msg["type"] == "response.create"
        assert msg["response"]["instructions"] == "Un momento, por favor."

    async def test_send_voice_cancel(self, bridge, call_id):
        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)

        event = RealtimeVoiceCancel(
            call_id=call_id,
            voice_generation_id=uuid4(),
            reason="barge_in",
            ts=1000,
        )

        await bridge.send_voice_cancel(event)

        assert mock_ws.send_text.call_count == 1
        msg = orjson.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert msg["type"] == "response.cancel"

    async def test_send_voice_start_no_ws(self, bridge, call_id):
        """send_voice_start without WebSocket should not raise."""
        event = RealtimeVoiceStart(
            call_id=call_id,
            agent_generation_id=uuid4(),
            voice_generation_id=uuid4(),
            prompt="test",
            ts=1000,
        )
        await bridge.send_voice_start(event)

    async def test_send_voice_cancel_no_ws(self, bridge, call_id):
        """send_voice_cancel without WebSocket should not raise."""
        event = RealtimeVoiceCancel(
            call_id=call_id,
            voice_generation_id=uuid4(),
            reason="test",
            ts=1000,
        )
        await bridge.send_voice_cancel(event)


# ---------------------------------------------------------------------------
# Frontend WebSocket lifecycle
# ---------------------------------------------------------------------------


class TestFrontendWebSocketLifecycle:
    def test_set_frontend_ws(self, bridge):
        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)
        assert bridge._frontend_ws is mock_ws

    def test_clear_frontend_ws(self, bridge):
        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)
        bridge.set_frontend_ws(None)
        assert bridge._frontend_ws is None

    async def test_close_clears_state(self, bridge):
        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)

        await bridge.close()

        assert bridge._closed is True
        assert bridge._frontend_ws is None

    async def test_close_idempotent(self, bridge):
        """Calling close() without WebSocket should not raise."""
        await bridge.close()
        assert bridge._closed is True
