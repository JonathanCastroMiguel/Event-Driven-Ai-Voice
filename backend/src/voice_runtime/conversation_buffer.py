"""Conversation buffer for multi-turn context within a single call."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnEntry:
    """A completed turn's summary for conversation history."""

    seq: int
    user_text: str
    route_a_label: str | None = None
    policy_key: str | None = None
    specialist: str | None = None


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

    def append(self, entry: TurnEntry) -> None:
        """Append a turn entry, pruning oldest entries if limits are exceeded."""
        # Sliding window: drop oldest if at max_turns
        while len(self._entries) >= self._max_turns:
            self._entries.pop(0)

        # Character budget: drop oldest until new entry fits
        new_chars = len(entry.user_text)
        current_chars = sum(len(e.user_text) for e in self._entries)

        if current_chars + new_chars > self._max_chars:
            if new_chars > self._max_chars:
                # Single entry exceeds entire budget: clear and store as-is
                self._entries.clear()
            else:
                while self._entries and current_chars + new_chars > self._max_chars:
                    removed = self._entries.pop(0)
                    current_chars -= len(removed.user_text)

        self._entries.append(entry)

    def format_messages(self) -> list[dict[str, str]]:
        """Return history as alternating user/assistant chat messages."""
        messages: list[dict[str, str]] = []
        for entry in self._entries:
            messages.append({"role": "user", "content": entry.user_text})
            messages.append({"role": "assistant", "content": self._format_assistant(entry)})
        return messages

    @staticmethod
    def _format_assistant(entry: TurnEntry) -> str:
        if entry.specialist is not None:
            return f"[{entry.route_a_label}] Specialist: {entry.specialist}"
        if entry.policy_key is not None:
            return f"[{entry.policy_key}] Guided response"
        return f"[{entry.route_a_label}] Response"
