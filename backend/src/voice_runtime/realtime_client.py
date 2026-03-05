"""Realtime adapter Protocol and stub implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, Protocol
from uuid import UUID

import structlog

from src.voice_runtime.events import (
    EventEnvelope,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
    VoiceGenerationCompleted,
    VoiceGenerationError,
)

logger = structlog.get_logger()


class RealtimeClient(Protocol):
    """Protocol for the Realtime voice adapter."""

    async def send_voice_start(self, event: RealtimeVoiceStart) -> None:
        """Start a voice generation on the Realtime provider."""
        ...

    async def send_voice_cancel(self, event: RealtimeVoiceCancel) -> None:
        """Cancel an active voice generation on the Realtime provider."""
        ...

    def on_event(
        self,
        callback: Callable[[EventEnvelope], Coroutine[Any, Any, None]],
    ) -> None:
        """Register a callback for events coming from the Realtime provider."""
        ...

    async def close(self) -> None:
        """Clean up resources."""
        ...


class StubRealtimeClient:
    """Stub Realtime adapter for testing.

    Emits voice_generation_completed after a configurable delay when
    send_voice_start is called. Tracks all calls for test assertions.
    """

    def __init__(self, delay_ms: float = 50.0) -> None:
        self._delay_s = delay_ms / 1000.0
        self._callback: Callable[[EventEnvelope], Coroutine[Any, Any, None]] | None = None
        self._tasks: list[asyncio.Task[None]] = []

        # Tracking for assertions
        self.voice_starts: list[RealtimeVoiceStart] = []
        self.voice_cancels: list[RealtimeVoiceCancel] = []
        self.cancelled_voice_ids: set[UUID] = set()

        # Control: set to inject errors
        self.fail_voice_ids: set[UUID] = set()

    async def send_voice_start(self, event: RealtimeVoiceStart) -> None:
        self.voice_starts.append(event)
        logger.debug(
            "stub_voice_start",
            voice_generation_id=str(event.voice_generation_id),
        )
        task = asyncio.create_task(
            self._emit_completed(event.call_id, event.voice_generation_id, event.ts)
        )
        self._tasks.append(task)

    async def send_voice_cancel(self, event: RealtimeVoiceCancel) -> None:
        self.voice_cancels.append(event)
        self.cancelled_voice_ids.add(event.voice_generation_id)
        logger.debug(
            "stub_voice_cancel",
            voice_generation_id=str(event.voice_generation_id),
        )

    def on_event(
        self,
        callback: Callable[[EventEnvelope], Coroutine[Any, Any, None]],
    ) -> None:
        self._callback = callback

    async def close(self) -> None:
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()

    async def _emit_completed(
        self, call_id: UUID, voice_generation_id: UUID, ts: int
    ) -> None:
        await asyncio.sleep(self._delay_s)

        # Skip if cancelled during delay
        if voice_generation_id in self.cancelled_voice_ids:
            return

        if self._callback is None:
            return

        if voice_generation_id in self.fail_voice_ids:
            error_event = VoiceGenerationError(
                call_id=call_id,
                voice_generation_id=voice_generation_id,
                error="stub_error",
                ts=ts + int(self._delay_s * 1000),
            )
            from uuid import uuid4

            from src.voice_runtime.types import EventSource

            envelope = EventEnvelope(
                event_id=uuid4(),
                call_id=call_id,
                ts=error_event.ts,
                type="voice_generation_error",
                payload={
                    "voice_generation_id": str(voice_generation_id),
                    "error": "stub_error",
                },
                source=EventSource.REALTIME,
            )
            await self._callback(envelope)
            return

        completed = VoiceGenerationCompleted(
            call_id=call_id,
            voice_generation_id=voice_generation_id,
            ts=ts + int(self._delay_s * 1000),
        )
        from uuid import uuid4

        from src.voice_runtime.types import EventSource

        envelope = EventEnvelope(
            event_id=uuid4(),
            call_id=call_id,
            ts=completed.ts,
            type="voice_generation_completed",
            payload={"voice_generation_id": str(voice_generation_id)},
            source=EventSource.REALTIME,
        )
        await self._callback(envelope)
