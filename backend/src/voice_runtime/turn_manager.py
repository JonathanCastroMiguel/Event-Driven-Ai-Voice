from __future__ import annotations

from uuid import UUID, uuid4

import structlog

from src.voice_runtime.events import (
    EventEnvelope,
    HumanTurnCancelled,
    HumanTurnFinalized,
    HumanTurnStarted,
)
from src.voice_runtime.types import TurnState

logger = structlog.get_logger()


class TurnManager:
    """Detects human turns from speech/transcript events.

    Emits turn lifecycle events (started, finalized, cancelled).
    Has no knowledge of tools, agents, or routing.
    """

    def __init__(self, call_id: UUID) -> None:
        self._call_id = call_id
        self._seq = 0
        self._current_turn_id: UUID | None = None
        self._current_state: TurnState | None = None
        self._current_transcript: str | None = None
        self._pending_events: list[HumanTurnStarted | HumanTurnFinalized | HumanTurnCancelled] = []

    @property
    def current_turn_id(self) -> UUID | None:
        return self._current_turn_id

    @property
    def current_state(self) -> TurnState | None:
        return self._current_state

    @property
    def seq(self) -> int:
        return self._seq

    def drain_events(self) -> list[HumanTurnStarted | HumanTurnFinalized | HumanTurnCancelled]:
        """Return and clear pending output events."""
        events = self._pending_events
        self._pending_events = []
        return events

    def handle_speech_started(self, ts: int) -> None:
        """Handle speech_started event. Opens a new turn, cancelling any open one."""
        # If there's an open turn, cancel it (barge-in)
        if self._current_turn_id is not None and self._current_state == TurnState.OPEN:
            self._cancel_current("barge_in", ts)

        # Start new turn
        self._seq += 1
        self._current_turn_id = uuid4()
        self._current_state = TurnState.OPEN
        self._pending_events.append(
            HumanTurnStarted(
                call_id=self._call_id,
                turn_id=self._current_turn_id,
                ts=ts,
            )
        )
        logger.info(
            "turn_started",
            turn_id=str(self._current_turn_id),
            seq=self._seq,
        )

    def handle_audio_committed(self, ts: int) -> None:
        """Handle audio_committed event. Finalizes the current open turn.

        This is the primary turn-closing signal in the model-as-router architecture.
        The committed event fires when server VAD confirms the user has stopped speaking.
        """
        if self._current_turn_id is None or self._current_state != TurnState.OPEN:
            logger.warning("audio_committed_without_open_turn")
            return

        self._current_state = TurnState.FINALIZED
        self._pending_events.append(
            HumanTurnFinalized(
                call_id=self._call_id,
                turn_id=self._current_turn_id,
                text="",  # Text arrives asynchronously via transcript_final
                ts=ts,
            )
        )
        logger.info(
            "turn_finalized_via_committed",
            turn_id=str(self._current_turn_id),
            seq=self._seq,
        )

    def handle_transcript_final(self, text: str, ts: int) -> None:
        """Handle transcript_final event. Stores transcript for logging only.

        In the model-as-router architecture, transcript_final does NOT finalize
        turns — that's done by audio_committed. The transcript is stored for
        persistence, conversation buffer, and debug display.
        """
        self._current_transcript = text
        logger.info(
            "transcript_stored",
            turn_id=str(self._current_turn_id),
            seq=self._seq,
            text_len=len(text),
            text=text,
        )

    @property
    def current_transcript(self) -> str | None:
        """The most recent transcript text (stored for logging, not turn finalization)."""
        return self._current_transcript

    def handle_no_transcript_timeout(self, ts: int) -> None:
        """Handle timeout when no transcript_final arrives after speech_started."""
        if self._current_turn_id is not None and self._current_state == TurnState.OPEN:
            self._cancel_current("no_transcript", ts)

    def _cancel_current(self, reason: str, ts: int) -> None:
        if self._current_turn_id is None:
            return
        self._current_state = TurnState.CANCELLED
        self._pending_events.append(
            HumanTurnCancelled(
                call_id=self._call_id,
                turn_id=self._current_turn_id,
                reason=reason,
                ts=ts,
            )
        )
        logger.info(
            "turn_cancelled",
            turn_id=str(self._current_turn_id),
            reason=reason,
        )
