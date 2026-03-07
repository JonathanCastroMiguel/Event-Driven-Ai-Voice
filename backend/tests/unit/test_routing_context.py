"""Unit tests for format_history (simplified model-as-router context)."""

from __future__ import annotations

from src.routing.context import format_history
from src.voice_runtime.conversation_buffer import ConversationBuffer, TurnEntry


def _buffer_with(*texts: str) -> ConversationBuffer:
    """Create a ConversationBuffer pre-filled with entries."""
    buf = ConversationBuffer(max_turns=10, max_chars=2000)
    for i, text in enumerate(texts, start=1):
        buf.append(TurnEntry(seq=i, user_text=text))
    return buf


class TestFormatHistoryEmpty:
    def test_empty_buffer_returns_empty_list(self) -> None:
        buf = ConversationBuffer()
        result = format_history(buf)
        assert result == []


class TestFormatHistorySingleTurn:
    def test_single_turn_returns_user_assistant_pair(self) -> None:
        buf = _buffer_with("hola")
        result = format_history(buf)
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "hola"}
        assert result[1]["role"] == "assistant"


class TestFormatHistoryMultipleTurns:
    def test_multiple_turns_in_order(self) -> None:
        buf = _buffer_with("hola", "mi factura", "de este mes")
        result = format_history(buf)
        assert len(result) == 6  # 3 turns × 2 messages each
        assert result[0]["content"] == "hola"
        assert result[2]["content"] == "mi factura"
        assert result[4]["content"] == "de este mes"

    def test_buffer_limit_respected(self) -> None:
        buf = ConversationBuffer(max_turns=2, max_chars=2000)
        for i, text in enumerate(["first", "second", "third"], start=1):
            buf.append(TurnEntry(seq=i, user_text=text))
        result = format_history(buf)
        # Only last 2 turns should be present
        assert len(result) == 4
        assert result[0]["content"] == "second"
        assert result[2]["content"] == "third"
