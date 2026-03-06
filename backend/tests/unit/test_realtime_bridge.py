"""Unit tests for RealtimeVoiceBridge (task 11.2)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.voice_runtime.events import (
    EventEnvelope,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
)
from src.voice_runtime.realtime_bridge import RealtimeVoiceBridge
from src.voice_runtime.realtime_provider import StubVoiceProvider
from src.voice_runtime.types import EventSource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_control_channel() -> MagicMock:
    """Create a mock DataChannel with .on() and .send()."""
    channel = MagicMock()
    channel.readyState = "open"
    channel._handlers: dict[str, list] = {}

    def on(event_name: str):
        def decorator(func):
            channel._handlers.setdefault(event_name, []).append(func)
            return func
        return decorator

    channel.on = on
    return channel


def _make_debug_channel() -> MagicMock:
    channel = MagicMock()
    channel.readyState = "open"
    return channel


def _make_bridge(
    provider: StubVoiceProvider | None = None,
) -> tuple[RealtimeVoiceBridge, MagicMock, MagicMock]:
    call_id = uuid4()
    prov = provider or StubVoiceProvider(tts_frame_count=2, frame_delay_ms=5)
    ctrl = _make_control_channel()
    dbg = _make_debug_channel()
    bridge = RealtimeVoiceBridge(call_id, prov, ctrl, dbg)
    return bridge, ctrl, dbg


def _voice_start(call_id=None, gen_id=None, voice_id=None) -> RealtimeVoiceStart:
    return RealtimeVoiceStart(
        call_id=call_id or uuid4(),
        agent_generation_id=gen_id or uuid4(),
        voice_generation_id=voice_id or uuid4(),
        prompt="Hello, how can I help you?",
        ts=1000,
    )


def _voice_cancel(call_id=None, voice_id=None) -> RealtimeVoiceCancel:
    return RealtimeVoiceCancel(
        call_id=call_id or uuid4(),
        voice_generation_id=voice_id or uuid4(),
        reason="barge_in",
        ts=1000,
    )


# ---------------------------------------------------------------------------
# send_voice_start — TTS streaming
# ---------------------------------------------------------------------------


class TestSendVoiceStart:
    @pytest.mark.asyncio
    async def test_emits_voice_generation_completed(self) -> None:
        bridge, ctrl, dbg = _make_bridge()
        received: list[EventEnvelope] = []

        async def cb(env: EventEnvelope) -> None:
            received.append(env)

        bridge.on_event(cb)

        event = _voice_start(call_id=bridge._call_id)
        await bridge.send_voice_start(event)
        # Wait for TTS to finish (2 frames * 5ms + margin)
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0].type == "voice_generation_completed"
        assert received[0].source == EventSource.REALTIME

    @pytest.mark.asyncio
    async def test_no_callback_no_crash(self) -> None:
        bridge, _, _ = _make_bridge()
        event = _voice_start(call_id=bridge._call_id)
        await bridge.send_voice_start(event)
        await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# send_voice_cancel — TTS cancellation
# ---------------------------------------------------------------------------


class TestSendVoiceCancel:
    @pytest.mark.asyncio
    async def test_cancel_stops_tts(self) -> None:
        provider = StubVoiceProvider(tts_frame_count=50, frame_delay_ms=50)
        bridge, _, _ = _make_bridge(provider)
        received: list[EventEnvelope] = []

        async def cb(env: EventEnvelope) -> None:
            received.append(env)

        bridge.on_event(cb)

        voice_id = uuid4()
        start = _voice_start(call_id=bridge._call_id, voice_id=voice_id)
        await bridge.send_voice_start(start)

        # Cancel immediately
        cancel = _voice_cancel(call_id=bridge._call_id, voice_id=voice_id)
        await bridge.send_voice_cancel(cancel)

        await asyncio.sleep(0.1)
        # No completed event should be emitted
        completed = [e for e in received if e.type == "voice_generation_completed"]
        assert len(completed) == 0


# ---------------------------------------------------------------------------
# STT listener (Provider → Coordinator)
# ---------------------------------------------------------------------------


class TestSTTListener:
    @pytest.mark.asyncio
    async def test_forwards_final_transcription(self) -> None:
        provider = StubVoiceProvider(canned_transcription="Hello there")
        bridge, ctrl, _ = _make_bridge(provider)
        received: list[EventEnvelope] = []

        async def cb(env: EventEnvelope) -> None:
            received.append(env)

        bridge.on_event(cb)
        bridge.start_stt_listener()

        await asyncio.sleep(0.2)

        # Should have dispatched a transcript_final event
        finals = [e for e in received if e.type == "transcript_final"]
        assert len(finals) == 1
        assert finals[0].payload["text"] == "Hello there"

        # Should have sent transcription to browser via control channel
        ctrl.send.assert_called()
        sent_data = json.loads(ctrl.send.call_args[0][0])
        assert sent_data["type"] == "transcription"
        assert sent_data["text"] == "Hello there"
        assert sent_data["is_final"] is True


# ---------------------------------------------------------------------------
# VAD signal handling (DataChannel → Coordinator)
# ---------------------------------------------------------------------------


class TestVADSignals:
    @pytest.mark.asyncio
    async def test_speech_started_dispatches_event(self) -> None:
        bridge, ctrl, _ = _make_bridge()
        received: list[EventEnvelope] = []

        async def cb(env: EventEnvelope) -> None:
            received.append(env)

        bridge.on_event(cb)

        await bridge._handle_control_message(json.dumps({
            "type": "speech_started",
            "ts": 12345,
        }))

        assert len(received) == 1
        assert received[0].type == "speech_started"
        assert received[0].ts == 12345

    @pytest.mark.asyncio
    async def test_speech_ended_maps_to_speech_stopped(self) -> None:
        """Browser sends 'speech_ended' but internal event is 'speech_stopped'."""
        bridge, ctrl, _ = _make_bridge()
        received: list[EventEnvelope] = []

        async def cb(env: EventEnvelope) -> None:
            received.append(env)

        bridge.on_event(cb)

        await bridge._handle_control_message(json.dumps({
            "type": "speech_ended",
            "ts": 12345,
        }))

        assert len(received) == 1
        assert received[0].type == "speech_stopped"

    @pytest.mark.asyncio
    async def test_invalid_json_ignored(self) -> None:
        bridge, _, _ = _make_bridge()
        # Should not raise
        await bridge._handle_control_message("not json")

    @pytest.mark.asyncio
    async def test_debug_enable_disable(self) -> None:
        bridge, _, _ = _make_bridge()

        assert bridge._debug_enabled is False
        await bridge._handle_control_message(json.dumps({"type": "debug_enable"}))
        assert bridge._debug_enabled is True
        await bridge._handle_control_message(json.dumps({"type": "debug_disable"}))
        assert bridge._debug_enabled is False


# ---------------------------------------------------------------------------
# Debug event forwarding
# ---------------------------------------------------------------------------


class TestDebugForwarding:
    @pytest.mark.asyncio
    async def test_emit_debug_when_disabled(self) -> None:
        bridge, _, dbg = _make_bridge()
        bridge._debug_enabled = False

        await bridge.emit_debug({"type": "test", "data": 42})
        dbg.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_debug_when_enabled(self) -> None:
        bridge, _, dbg = _make_bridge()
        bridge._debug_enabled = True

        await bridge.emit_debug({"type": "test", "data": 42})
        dbg.send.assert_called_once()
        sent = json.loads(dbg.send.call_args[0][0])
        assert sent["type"] == "test"
        assert sent["data"] == 42


# ---------------------------------------------------------------------------
# on_event / close
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_on_event_registers_callback(self) -> None:
        bridge, _, _ = _make_bridge()

        async def cb(env: EventEnvelope) -> None:
            pass

        bridge.on_event(cb)
        assert bridge._callback is cb

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        provider = StubVoiceProvider()
        bridge, _, _ = _make_bridge(provider)

        bridge.start_stt_listener()
        await asyncio.sleep(0.01)

        await bridge.close()
        assert provider._closed is True
