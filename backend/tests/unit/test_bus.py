import asyncio
from uuid import uuid4

import pytest

from src.voice_runtime.bus import EventBus
from src.voice_runtime.events import EventEnvelope
from src.voice_runtime.types import EventSource


def _make_event(event_type: str = "speech_started") -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        call_id=uuid4(),
        ts=1000,
        type=event_type,
        payload={},
        source=EventSource.REALTIME,
    )


class TestEventBus:
    async def test_publish_and_dispatch(self) -> None:
        bus = EventBus(maxsize=10)
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        bus.register("speech_started", handler)

        event = _make_event("speech_started")
        await bus.publish(event)

        # Run bus in background, give it time to process
        task = asyncio.create_task(bus.run())
        await asyncio.sleep(0.05)
        task.cancel()

        assert len(received) == 1
        assert received[0].event_id == event.event_id

    async def test_unknown_event_type_ignored(self) -> None:
        bus = EventBus(maxsize=10)
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        bus.register("speech_started", handler)

        # Publish an unknown event type
        await bus.publish(_make_event("unknown_event"))
        # Then a known one
        await bus.publish(_make_event("speech_started"))

        task = asyncio.create_task(bus.run())
        await asyncio.sleep(0.05)
        task.cancel()

        # Only the known event should be handled
        assert len(received) == 1
        assert received[0].type == "speech_started"

    async def test_handler_error_does_not_crash_bus(self) -> None:
        bus = EventBus(maxsize=10)
        processed_after_error: list[EventEnvelope] = []

        async def failing_handler(event: EventEnvelope) -> None:
            msg = "handler error"
            raise RuntimeError(msg)

        async def good_handler(event: EventEnvelope) -> None:
            processed_after_error.append(event)

        bus.register("bad_event", failing_handler)
        bus.register("good_event", good_handler)

        await bus.publish(_make_event("bad_event"))
        await bus.publish(_make_event("good_event"))

        task = asyncio.create_task(bus.run())
        await asyncio.sleep(0.05)
        task.cancel()

        # The good event should still be processed after the error
        assert len(processed_after_error) == 1

    async def test_backpressure_with_bounded_queue(self) -> None:
        bus = EventBus(maxsize=2)

        await bus.publish(_make_event())
        await bus.publish(_make_event())

        assert bus.full

        # Third publish should block — verify with a timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(bus.publish(_make_event()), timeout=0.1)

    async def test_qsize_tracking(self) -> None:
        bus = EventBus(maxsize=10)
        assert bus.qsize == 0

        await bus.publish(_make_event())
        assert bus.qsize == 1

        await bus.publish(_make_event())
        assert bus.qsize == 2

    async def test_multiple_event_types_dispatched_correctly(self) -> None:
        bus = EventBus(maxsize=10)
        speech_events: list[EventEnvelope] = []
        turn_events: list[EventEnvelope] = []

        async def speech_handler(event: EventEnvelope) -> None:
            speech_events.append(event)

        async def turn_handler(event: EventEnvelope) -> None:
            turn_events.append(event)

        bus.register("speech_started", speech_handler)
        bus.register("human_turn_finalized", turn_handler)

        await bus.publish(_make_event("speech_started"))
        await bus.publish(_make_event("human_turn_finalized"))
        await bus.publish(_make_event("speech_started"))

        task = asyncio.create_task(bus.run())
        await asyncio.sleep(0.05)
        task.cancel()

        assert len(speech_events) == 2
        assert len(turn_events) == 1
