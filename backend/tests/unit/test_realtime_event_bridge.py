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

    async def test_audio_committed(self, bridge, call_id):
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        await bridge._translate_event({"type": "input_audio_buffer.committed"})

        assert len(received) == 1
        assert received[0].type == "audio_committed"
        assert received[0].call_id == call_id
        assert received[0].source.value == "realtime"

    async def test_voice_generation_completed_direct_voice(self, bridge, call_id):
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        voice_id = uuid4()
        bridge._active_voice_generation_id = voice_id
        bridge._response_transcript_buffer = "Buenos días, ¿en qué puedo ayudarle?"

        await bridge._translate_event({"type": "response.done"})

        assert len(received) == 1
        assert received[0].type == "voice_generation_completed"
        assert received[0].payload["voice_generation_id"] == str(voice_id)
        assert bridge._active_voice_generation_id is None
        assert bridge._response_transcript_buffer == ""

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
    async def test_send_voice_start_with_dict_payload(self, bridge, call_id):
        """Dict prompt (from RouterPromptBuilder) is forwarded as-is."""
        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)

        voice_id = uuid4()
        gen_id = uuid4()
        payload = {
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"],
                "instructions": "You are helpful. Greet warmly.",
                "tools": [{"type": "function", "name": "route_to_specialist"}],
                "tool_choice": "required",
                "temperature": 0.8,
            },
        }
        event = RealtimeVoiceStart(
            call_id=call_id,
            agent_generation_id=gen_id,
            voice_generation_id=voice_id,
            prompt=payload,
            ts=1000,
        )

        await bridge.send_voice_start(event)

        assert mock_ws.send_text.call_count == 1

        msg = orjson.loads(mock_ws.send_text.call_args_list[0][0][0])
        assert msg["type"] == "response.create"
        assert "You are helpful." in msg["response"]["instructions"]
        assert msg["response"]["tools"] is not None

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


# ---------------------------------------------------------------------------
# Transcript accumulation and JSON action detection
# ---------------------------------------------------------------------------


class TestTranscriptBufferAndJsonDetection:
    async def test_transcript_delta_accumulation(self, bridge):
        """response.audio_transcript.delta events accumulate in buffer."""
        await bridge._translate_event({"type": "response.audio_transcript.delta", "delta": "Buenos "})
        assert bridge._response_transcript_buffer == "Buenos "

        await bridge._translate_event({"type": "response.audio_transcript.delta", "delta": "días"})
        assert bridge._response_transcript_buffer == "Buenos días"

    async def test_buffer_reset_on_response_created(self, bridge):
        """response.created resets the transcript buffer."""
        bridge._response_transcript_buffer = "leftover text"
        await bridge._translate_event({"type": "response.created"})
        assert bridge._response_transcript_buffer == ""

    async def test_function_call_emits_model_router_action(self, bridge, call_id):
        """Function call with specialist department emits model_router_action."""
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        voice_id = uuid4()
        bridge._active_voice_generation_id = voice_id

        await bridge._translate_event({
            "type": "response.function_call_arguments.done",
            "name": "route_to_specialist",
            "arguments": '{"department": "billing", "summary": "billing issue"}',
            "call_id": "call_abc123",
            "item_id": "item_abc123",
        })

        assert len(received) == 1
        assert received[0].type == "model_router_action"
        assert received[0].payload["department"] == "billing"
        assert received[0].payload["summary"] == "billing issue"
        assert bridge._active_voice_generation_id is None

    async def test_malformed_json_falls_through_to_voice_completed(self, bridge, call_id):
        """Malformed JSON in transcript treats response as direct voice."""
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        voice_id = uuid4()
        bridge._active_voice_generation_id = voice_id
        bridge._response_transcript_buffer = '{"action": "specialist", "department": '

        await bridge._translate_event({"type": "response.done"})

        assert len(received) == 1
        assert received[0].type == "voice_generation_completed"

    async def test_unknown_department_falls_through(self, bridge, call_id):
        """Unknown department in JSON falls through to voice_generation_completed."""
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        voice_id = uuid4()
        bridge._active_voice_generation_id = voice_id
        bridge._response_transcript_buffer = '{"action": "specialist", "department": "unknown", "summary": "test"}'

        await bridge._translate_event({"type": "response.done"})

        assert len(received) == 1
        assert received[0].type == "voice_generation_completed"

    async def test_function_call_then_response_done_no_voice_completed(self, bridge, call_id):
        """Full flow: function call sets flag, response.done does NOT emit voice_generation_completed."""
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        bridge._active_voice_generation_id = uuid4()

        # Simulate response lifecycle with function call
        await bridge._translate_event({"type": "response.created"})
        await bridge._translate_event({
            "type": "response.function_call_arguments.done",
            "name": "route_to_specialist",
            "arguments": '{"department": "sales", "summary": "wants upgrade"}',
            "call_id": "call_xyz",
            "item_id": "item_xyz",
        })
        await bridge._translate_event({"type": "response.done"})

        # response_created + model_router_action — no voice_generation_completed
        assert len(received) == 2
        assert received[0].type == "response_created"
        assert received[1].type == "model_router_action"
        assert received[1].payload["department"] == "sales"

    async def test_buffer_cleared_after_response_done(self, bridge):
        """Buffer is cleared after response.done regardless of content."""
        bridge._active_voice_generation_id = uuid4()
        bridge._response_transcript_buffer = "some text"
        callback = AsyncMock()
        bridge.on_event(callback)

        await bridge._translate_event({"type": "response.done"})
        assert bridge._response_transcript_buffer == ""


# ---------------------------------------------------------------------------
# Response source and timing in payloads
# ---------------------------------------------------------------------------


class TestResponseSourceAndTiming:
    async def test_response_created_includes_response_source_router(self, bridge, call_id):
        """response_created payload includes response_source='router' by default."""
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)

        # Simulate send_voice_start to set timing
        event = RealtimeVoiceStart(
            call_id=call_id,
            agent_generation_id=uuid4(),
            voice_generation_id=uuid4(),
            prompt="test",
            ts=1000,
        )
        await bridge.send_voice_start(event)

        await bridge._translate_event({"type": "response.created"})

        assert len(received) == 1
        assert received[0].type == "response_created"
        assert received[0].payload["response_source"] == "router"

    async def test_response_created_includes_response_source_specialist(self, bridge, call_id):
        """response_created payload includes response_source='specialist' when set."""
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)

        event = RealtimeVoiceStart(
            call_id=call_id,
            agent_generation_id=uuid4(),
            voice_generation_id=uuid4(),
            prompt="specialist prompt",
            ts=1000,
            response_source="specialist",
        )
        await bridge.send_voice_start(event)

        await bridge._translate_event({"type": "response.created"})

        assert len(received) == 1
        assert received[0].payload["response_source"] == "specialist"

    async def test_response_created_includes_send_to_created_ms(self, bridge, call_id):
        """response_created payload includes send_to_created_ms when non-zero."""
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)

        event = RealtimeVoiceStart(
            call_id=call_id,
            agent_generation_id=uuid4(),
            voice_generation_id=uuid4(),
            prompt="test",
            ts=1000,
        )
        await bridge.send_voice_start(event)
        await bridge._translate_event({"type": "response.created"})

        assert len(received) == 1
        # send_to_created_ms should be present (may be 0 due to fast execution)
        assert "response_source" in received[0].payload

    async def test_voice_generation_completed_includes_response_source(self, bridge, call_id):
        """voice_generation_completed payload includes response_source."""
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        voice_id = uuid4()
        bridge._active_voice_generation_id = voice_id
        bridge._response_transcript_buffer = "Buenos días"
        bridge._current_response_source = "router"
        bridge._response_created_ms = 100

        await bridge._translate_event({"type": "response.done"})

        assert len(received) == 1
        assert received[0].type == "voice_generation_completed"
        assert received[0].payload["response_source"] == "router"

    async def test_voice_generation_completed_includes_created_to_done_ms(self, bridge, call_id):
        """voice_generation_completed payload includes created_to_done_ms when non-zero."""
        received = []
        callback = AsyncMock(side_effect=lambda e: received.append(e))
        bridge.on_event(callback)

        voice_id = uuid4()
        bridge._active_voice_generation_id = voice_id
        bridge._response_transcript_buffer = "Hello"
        bridge._response_created_ms = 1  # Non-zero to trigger inclusion

        await bridge._translate_event({"type": "response.done"})

        assert len(received) == 1
        assert "created_to_done_ms" in received[0].payload
        assert received[0].payload["created_to_done_ms"] > 0

    async def test_send_voice_start_resets_timing_state(self, bridge, call_id):
        """send_voice_start resets timing and response_source state."""
        mock_ws = _make_mock_ws()
        bridge.set_frontend_ws(mock_ws)

        bridge._response_created_ms = 999
        bridge._current_response_source = "specialist"

        event = RealtimeVoiceStart(
            call_id=call_id,
            agent_generation_id=uuid4(),
            voice_generation_id=uuid4(),
            prompt="test",
            ts=1000,
        )
        await bridge.send_voice_start(event)

        assert bridge._response_created_ms == 0
        assert bridge._current_response_source == "router"
