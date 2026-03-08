"""Conversation buffer for multi-turn context within a single call."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TurnEntry:
    """A completed turn's summary for conversation history."""

    seq: int
    user_text: str = ""
    agent_text: str = ""


class ConversationBuffer:
    """Sliding-window buffer of completed turns for prompt history injection."""

    def __init__(self, max_turns: int = 10, max_chars: int = 2000) -> None:
        self._max_turns = max_turns
        self._max_chars = max_chars
        self._entries: list[TurnEntry] = []

    @property
    def entries(self) -> list[TurnEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def _entry_chars(self, entry: TurnEntry) -> int:
        return len(entry.user_text) + len(entry.agent_text)

    def _prune_oldest(self) -> None:
        """Drop oldest entries until within character budget."""
        total = sum(self._entry_chars(e) for e in self._entries)
        while self._entries and total > self._max_chars:
            removed = self._entries.pop(0)
            total -= self._entry_chars(removed)

    def append(self, entry: TurnEntry) -> None:
        """Append a turn entry, pruning oldest entries if limits are exceeded."""
        while len(self._entries) >= self._max_turns:
            self._entries.pop(0)
        self._entries.append(entry)

    def update_last_user_text(self, text: str) -> None:
        """Update the user_text of the most recent entry."""
        if self._entries:
            self._entries[-1].user_text = text
            self._prune_oldest()

    def update_agent_text(self, seq: int, text: str) -> None:
        """Update the agent_text for the entry with the given seq."""
        for entry in reversed(self._entries):
            if entry.seq == seq:
                entry.agent_text = text
                self._prune_oldest()
                return

    def format_messages(self) -> list[dict[str, str]]:
        """Return history as alternating user/assistant chat messages."""
        messages: list[dict[str, str]] = []
        for entry in self._entries:
            if not entry.user_text and not entry.agent_text:
                continue
            messages.append({"role": "user", "content": entry.user_text or "(audio)"})
            messages.append({"role": "assistant", "content": entry.agent_text or "(no response)"})
        return messages
