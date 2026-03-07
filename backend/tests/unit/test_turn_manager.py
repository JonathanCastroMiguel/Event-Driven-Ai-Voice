from uuid import uuid4

from src.voice_runtime.events import (
    HumanTurnCancelled,
    HumanTurnFinalized,
    HumanTurnStarted,
)
from src.voice_runtime.turn_manager import TurnManager
from src.voice_runtime.types import TurnState


class TestCommittedBasedTurnLifecycle:
    """Tests for the model-as-router turn lifecycle: speech_started → audio_committed → finalized."""

    def test_committed_finalizes_turn(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_audio_committed(ts=1500)

        events = tm.drain_events()
        assert len(events) == 2
        assert isinstance(events[0], HumanTurnStarted)
        assert isinstance(events[1], HumanTurnFinalized)
        assert events[1].text == ""  # Text arrives asynchronously
        assert tm.current_state == TurnState.FINALIZED

    def test_committed_without_open_turn_ignored(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_audio_committed(ts=1000)
        events = tm.drain_events()
        assert len(events) == 0

    def test_committed_after_already_finalized_ignored(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_audio_committed(ts=1500)
        tm.drain_events()

        # Second committed should be ignored (already finalized)
        tm.handle_audio_committed(ts=2000)
        events = tm.drain_events()
        assert len(events) == 0

    def test_full_flow_with_transcript(self) -> None:
        """speech_started → audio_committed → transcript_final (async, logging only)."""
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_audio_committed(ts=1500)

        events = tm.drain_events()
        assert len(events) == 2
        assert isinstance(events[1], HumanTurnFinalized)

        # Transcript arrives after committed (for logging/persistence)
        tm.handle_transcript_final(text="tengo un problema", ts=1700)
        assert tm.current_transcript == "tengo un problema"

        # No new events emitted — transcript is logging only
        events = tm.drain_events()
        assert len(events) == 0


class TestTranscriptFinalDoesNotFinalize:
    """Verify that transcript_final no longer finalizes turns."""

    def test_transcript_final_stores_text_only(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)

        # transcript_final should NOT finalize the turn
        tm.handle_transcript_final(text="hola", ts=1100)

        events = tm.drain_events()
        # Only speech_started, no finalized event
        assert len(events) == 1
        assert isinstance(events[0], HumanTurnStarted)
        assert tm.current_state == TurnState.OPEN  # Still open
        assert tm.current_transcript == "hola"

    def test_transcript_final_then_committed_finalizes(self) -> None:
        """Even if transcript arrives before committed, committed is the finalizer."""
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_transcript_final(text="hola", ts=1100)

        # Turn still open
        assert tm.current_state == TurnState.OPEN

        tm.handle_audio_committed(ts=1200)
        events = tm.drain_events()
        assert len(events) == 2  # started + finalized
        assert isinstance(events[1], HumanTurnFinalized)
        assert tm.current_state == TurnState.FINALIZED


class TestBargeIn:
    def test_barge_in_creates_new_turn(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_speech_started(ts=1200)

        events = tm.drain_events()
        assert len(events) == 3
        assert isinstance(events[0], HumanTurnStarted)
        assert isinstance(events[1], HumanTurnCancelled)
        assert events[1].reason == "barge_in"
        assert isinstance(events[2], HumanTurnStarted)
        assert events[0].turn_id != events[2].turn_id

    def test_barge_in_increments_seq(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_speech_started(ts=1200)
        assert tm.seq == 2


class TestSequentialNumbering:
    def test_sequential_numbering_with_committed(self) -> None:
        tm = TurnManager(call_id=uuid4())

        tm.handle_speech_started(ts=1000)
        tm.handle_audio_committed(ts=1100)
        assert tm.seq == 1

        tm.handle_speech_started(ts=2000)
        tm.handle_audio_committed(ts=2100)
        assert tm.seq == 2

        tm.handle_speech_started(ts=3000)
        tm.handle_audio_committed(ts=3100)
        assert tm.seq == 3


class TestMiscTurnManager:
    def test_cancelled_turn_no_transcript(self) -> None:
        tm = TurnManager(call_id=uuid4())
        tm.handle_speech_started(ts=1000)
        tm.handle_no_transcript_timeout(ts=2000)

        events = tm.drain_events()
        assert len(events) == 2
        assert isinstance(events[1], HumanTurnCancelled)
        assert events[1].reason == "no_transcript"
        assert tm.current_state == TurnState.CANCELLED

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
        tm.handle_audio_committed(ts=1100)
        tm.handle_no_transcript_timeout(ts=2000)

        events = tm.drain_events()
        assert len(events) == 2
        assert isinstance(events[1], HumanTurnFinalized)
