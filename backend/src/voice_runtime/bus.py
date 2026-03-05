from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from src.voice_runtime.events import EventEnvelope

logger = structlog.get_logger()

type EventHandler = Callable[[EventEnvelope], Awaitable[None]]

DEFAULT_MAX_SIZE = 1000


class EventBus:
    """In-process async event bus backed by asyncio.Queue."""

    def __init__(self, maxsize: int = DEFAULT_MAX_SIZE) -> None:
        self._queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=maxsize)
        self._handlers: dict[str, EventHandler] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type] = handler

    async def publish(self, event: EventEnvelope) -> None:
        await self._queue.put(event)

    async def run(self) -> None:
        """Consume events from the queue and dispatch to registered handlers."""
        while True:
            event = await self._queue.get()
            handler = self._handlers.get(event.type)
            if handler is None:
                logger.warning(
                    "unhandled_event_type",
                    event_type=event.type,
                    event_id=str(event.event_id),
                )
                continue
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "event_handler_error",
                    event_type=event.type,
                    event_id=str(event.event_id),
                    call_id=str(event.call_id),
                )

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def full(self) -> bool:
        return self._queue.full()

    def pending(self) -> int:
        return self._queue.qsize()
