"""Unit tests for Realtime adapter Protocol contract (task 11.3)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from src.voice_runtime.events import (
    EventEnvelope,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
)
from src.voice_runtime.realtime_client import RealtimeClient, StubRealtimeClient
from src.voice_runtime.types import EventSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _voice_start(call_id=None, gen_id=None, voice_id=None) -> RealtimeVoiceStart:
    return RealtimeVoiceStart(
        call_id=call_id or uuid4(),
        agent_generation_id=gen_id or uuid4(),
        voice_generation_id=voice_id or uuid4(),
        prompt="Test prompt",
        ts=1000,
    )


def _voice_cancel(call_id=None, voice_id=None) -> RealtimeVoiceCancel:
    return RealtimeVoiceCancel(
        call_id=call_id or uuid4(),
        voice_generation_id=voice_id or uuid4(),
        reason="test",
        ts=1000,
    )


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_stub_satisfies_protocol(self) -> None:
        """StubRealtimeClient must satisfy the RealtimeClient Protocol."""
        client: RealtimeClient = StubRealtimeClient()
        assert hasattr(client, "send_voice_start")
        assert hasattr(client, "send_voice_cancel")
        assert hasattr(client, "on_event")
        assert hasattr(client, "close")


# ---------------------------------------------------------------------------
# send_voice_start
# ---------------------------------------------------------------------------


class TestSendVoiceStart:
    @pytest.mark.asyncio
    async def test_tracks_voice_starts(self) -> None:
        client = StubRealtimeClient(delay_ms=10)
        event = _voice_start()
        await client.send_voice_start(event)
        assert len(client.voice_starts) == 1
        assert client.voice_starts[0] is event

    @pytest.mark.asyncio
    async def test_emits_completed_after_delay(self) -> None:
        client = StubRealtimeClient(delay_ms=10)
        received: list[EventEnvelope] = []

        async def callback(env: EventEnvelope) -> None:
            received.append(env)

        client.on_event(callback)
        event = _voice_start()
        await client.send_voice_start(event)

        # Wait for completion
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0].type == "voice_generation_completed"
        payload = received[0].payload
        assert payload["voice_generation_id"] == str(event.voice_generation_id)

    @pytest.mark.asyncio
    async def test_no_callback_no_crash(self) -> None:
        client = StubRealtimeClient(delay_ms=10)
        # No on_event callback registered
        await client.send_voice_start(_voice_start())
        await asyncio.sleep(0.05)
        # Should not raise


# ---------------------------------------------------------------------------
# send_voice_cancel
# ---------------------------------------------------------------------------


class TestSendVoiceCancel:
    @pytest.mark.asyncio
    async def test_tracks_voice_cancels(self) -> None:
        client = StubRealtimeClient(delay_ms=10)
        event = _voice_cancel()
        await client.send_voice_cancel(event)
        assert len(client.voice_cancels) == 1
        assert client.voice_cancels[0] is event
        assert event.voice_generation_id in client.cancelled_voice_ids

    @pytest.mark.asyncio
    async def test_cancel_prevents_completed_emission(self) -> None:
        client = StubRealtimeClient(delay_ms=50)
        received: list[EventEnvelope] = []

        async def callback(env: EventEnvelope) -> None:
            received.append(env)

        client.on_event(callback)

        call_id = uuid4()
        voice_id = uuid4()
        start = _voice_start(call_id=call_id, voice_id=voice_id)
        await client.send_voice_start(start)

        # Cancel immediately before delay completes
        cancel = _voice_cancel(call_id=call_id, voice_id=voice_id)
        await client.send_voice_cancel(cancel)

        await asyncio.sleep(0.1)
        # No completed event should have been emitted
        assert len(received) == 0


# ---------------------------------------------------------------------------
# Error injection
# ---------------------------------------------------------------------------


class TestErrorInjection:
    @pytest.mark.asyncio
    async def test_fail_voice_ids_emits_error(self) -> None:
        client = StubRealtimeClient(delay_ms=10)
        received: list[EventEnvelope] = []

        async def callback(env: EventEnvelope) -> None:
            received.append(env)

        client.on_event(callback)

        voice_id = uuid4()
        client.fail_voice_ids.add(voice_id)

        event = _voice_start(voice_id=voice_id)
        await client.send_voice_start(event)

        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0].type == "voice_generation_error"
        assert received[0].payload["error"] == "stub_error"


# ---------------------------------------------------------------------------
# on_event
# ---------------------------------------------------------------------------


class TestOnEvent:
    @pytest.mark.asyncio
    async def test_callback_registered(self) -> None:
        client = StubRealtimeClient()
        called = False

        async def callback(env: EventEnvelope) -> None:
            nonlocal called
            called = True

        client.on_event(callback)
        assert client._callback is callback


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    @pytest.mark.asyncio
    async def test_close_cancels_pending_tasks(self) -> None:
        client = StubRealtimeClient(delay_ms=5000)  # Long delay
        await client.send_voice_start(_voice_start())
        assert len(client._tasks) == 1
        assert not client._tasks[0].done()

        await client.close()
        assert len(client._tasks) == 0

    @pytest.mark.asyncio
    async def test_close_idempotent(self) -> None:
        client = StubRealtimeClient()
        await client.close()
        await client.close()  # Should not raise
