from uuid import uuid4

from src.voice_runtime.events import (
    EVENT_TYPE_MAP,
    EventEnvelope,
    HumanTurnFinalized,
    SpeechStarted,
    TranscriptFinal,
)
from src.voice_runtime.types import EventSource


class TestEventEnvelope:
    def test_create_with_required_fields(self) -> None:
        event = EventEnvelope(
            event_id=uuid4(),
            call_id=uuid4(),
            ts=1000,
            type="speech_started",
            payload={"key": "value"},
            source=EventSource.REALTIME,
        )
        assert event.type == "speech_started"
        assert event.correlation_id is None
        assert event.causation_id is None

    def test_create_with_causal_chain(self) -> None:
        cause_id = uuid4()
        correlation_id = uuid4()
        event = EventEnvelope(
            event_id=uuid4(),
            call_id=uuid4(),
            ts=1000,
            type="handle_turn",
            payload={},
            source=EventSource.COORDINATOR,
            correlation_id=correlation_id,
            causation_id=cause_id,
        )
        assert event.correlation_id == correlation_id
        assert event.causation_id == cause_id

    def test_envelope_is_frozen(self) -> None:
        event = EventEnvelope(
            event_id=uuid4(),
            call_id=uuid4(),
            ts=1000,
            type="speech_started",
            payload={},
            source=EventSource.REALTIME,
        )
        try:
            event.ts = 2000  # type: ignore[misc]
            raise AssertionError("Should not allow mutation")
        except AttributeError:
            pass


class TestTypedEventStructs:
    def test_speech_started(self) -> None:
        event = SpeechStarted(call_id=uuid4(), ts=1000)
        assert event.provider_event_id is None

    def test_speech_started_with_provider_id(self) -> None:
        event = SpeechStarted(call_id=uuid4(), ts=1000, provider_event_id="prov_123")
        assert event.provider_event_id == "prov_123"

    def test_transcript_final(self) -> None:
        call_id = uuid4()
        event = TranscriptFinal(call_id=call_id, text="hola", ts=2000)
        assert event.text == "hola"
        assert event.call_id == call_id

    def test_human_turn_finalized(self) -> None:
        event = HumanTurnFinalized(
            call_id=uuid4(), turn_id=uuid4(), text="necesito ayuda", ts=3000
        )
        assert event.text == "necesito ayuda"

    def test_typed_events_are_frozen(self) -> None:
        event = SpeechStarted(call_id=uuid4(), ts=1000)
        try:
            event.ts = 2000  # type: ignore[misc]
            raise AssertionError("Should not allow mutation")
        except AttributeError:
            pass


class TestEventTypeMap:
    def test_all_event_types_registered(self) -> None:
        expected_types = {
            "speech_started",
            "speech_stopped",
            "transcript_partial",
            "transcript_final",
            "voice_generation_completed",
            "voice_generation_error",
            "human_turn_started",
            "human_turn_finalized",
            "human_turn_cancelled",
            "handle_turn",
            "cancel_agent_generation",
            "voice_done",
            "agent_state_changed",
            "request_guided_response",
            "request_agent_action",
            "request_tool_call",
            "run_tool",
            "cancel_tool",
            "tool_result",
            "realtime_voice_start",
            "realtime_voice_cancel",
        }
        assert set(EVENT_TYPE_MAP.keys()) == expected_types

    def test_map_values_are_struct_types(self) -> None:
        import msgspec

        for event_type, struct_class in EVENT_TYPE_MAP.items():
            assert issubclass(struct_class, msgspec.Struct), (
                f"{event_type} maps to {struct_class} which is not a msgspec.Struct"
            )
