from uuid import uuid4

from src.voice_runtime.events import (
    HumanTurnCancelled,
    HumanTurnFinalized,
    HumanTurnStarted,
)
from src.voice_runtime.turn_manager import TurnManager
from src.voice_runtime.types import TurnState


class TestTurnManager:
    def test_complete_turn_lifecycle(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_transcript_final(text="tengo un problema", ts=1500)

        events = tm.drain_events()
        assert len(events) == 2
        assert isinstance(events[0], HumanTurnStarted)
        assert isinstance(events[1], HumanTurnFinalized)
        assert events[1].text == "tengo un problema"
        assert tm.current_state == TurnState.FINALIZED

    def test_cancelled_turn_no_transcript(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_no_transcript_timeout(ts=2000)

        events = tm.drain_events()
        assert len(events) == 2
        assert isinstance(events[0], HumanTurnStarted)
        assert isinstance(events[1], HumanTurnCancelled)
        assert events[1].reason == "no_transcript"
        assert tm.current_state == TurnState.CANCELLED

    def test_barge_in_creates_new_turn(self) -> None:
        tm = TurnManager(call_id=uuid4())

        # First turn starts
        tm.handle_speech_started(ts=1000)
        # Barge-in: new speech before first turn finalized
        tm.handle_speech_started(ts=1200)

        events = tm.drain_events()
        assert len(events) == 3
        assert isinstance(events[0], HumanTurnStarted)  # first turn started
        assert isinstance(events[1], HumanTurnCancelled)  # first turn cancelled (barge-in)
        assert events[1].reason == "barge_in"
        assert isinstance(events[2], HumanTurnStarted)  # second turn started

        # Turn IDs should be different
        assert events[0].turn_id != events[2].turn_id

    def test_sequential_numbering(self) -> None:
        tm = TurnManager(call_id=uuid4())

        # Turn 1
        tm.handle_speech_started(ts=1000)
        tm.handle_transcript_final(text="hola", ts=1100)
        assert tm.seq == 1

        # Turn 2
        tm.handle_speech_started(ts=2000)
        tm.handle_transcript_final(text="necesito ayuda", ts=2100)
        assert tm.seq == 2

        # Turn 3
        tm.handle_speech_started(ts=3000)
        tm.handle_transcript_final(text="con mi factura", ts=3100)
        assert tm.seq == 3

    def test_barge_in_increments_seq(self) -> None:
        tm = TurnManager(call_id=uuid4())

        tm.handle_speech_started(ts=1000)  # seq=1
        tm.handle_speech_started(ts=1200)  # barge-in -> seq=2
        assert tm.seq == 2

    def test_transcript_final_without_open_turn_ignored(self) -> None:
        tm = TurnManager(call_id=uuid4())
        # No speech_started, just transcript_final
        tm.handle_transcript_final(text="orphan", ts=1000)
        events = tm.drain_events()
        assert len(events) == 0

    def test_drain_clears_events(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        first = tm.drain_events()
        assert len(first) == 1
        second = tm.drain_events()
        assert len(second) == 0

    def test_no_transcript_timeout_on_finalized_ignored(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_transcript_final(text="hola", ts=1100)
        tm.handle_no_transcript_timeout(ts=2000)

        events = tm.drain_events()
        # Only started + finalized, no cancelled
        assert len(events) == 2
        assert isinstance(events[1], HumanTurnFinalized)
