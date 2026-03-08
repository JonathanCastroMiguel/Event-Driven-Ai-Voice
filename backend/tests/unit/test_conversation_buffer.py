"""Unit tests for ConversationBuffer."""

from __future__ import annotations

from src.voice_runtime.conversation_buffer import ConversationBuffer, TurnEntry


def _entry(
    seq: int = 1,
    user_text: str = "hola",
    agent_text: str = "respuesta",
) -> TurnEntry:
    return TurnEntry(
        seq=seq,
        user_text=user_text,
        agent_text=agent_text,
    )


# ---------------------------------------------------------------------------
# 4.1 Empty buffer
# ---------------------------------------------------------------------------


class TestEmptyBuffer:
    def test_format_messages_returns_empty_list(self) -> None:
        buf = ConversationBuffer()
        assert buf.format_messages() == []

    def test_len_is_zero(self) -> None:
        buf = ConversationBuffer()
        assert len(buf) == 0

    def test_entries_returns_empty_list(self) -> None:
        buf = ConversationBuffer()
        assert buf.entries == []


# ---------------------------------------------------------------------------
# 4.2 Append and retrieve single entry
# ---------------------------------------------------------------------------


class TestAppendSingle:
    def test_append_single_entry(self) -> None:
        buf = ConversationBuffer()
        entry = _entry(seq=1, user_text="hola")
        buf.append(entry)
        assert len(buf) == 1
        assert buf.entries[0] == entry

    def test_entries_returns_copy(self) -> None:
        buf = ConversationBuffer()
        buf.append(_entry())
        entries = buf.entries
        entries.clear()
        assert len(buf) == 1  # internal list not affected


# ---------------------------------------------------------------------------
# 4.3 Sliding window: max_turns
# ---------------------------------------------------------------------------


class TestSlidingWindow:
    def test_drops_oldest_when_max_turns_exceeded(self) -> None:
        buf = ConversationBuffer(max_turns=2, max_chars=10000)
        buf.append(_entry(seq=1, user_text="a"))
        buf.append(_entry(seq=2, user_text="b"))
        buf.append(_entry(seq=3, user_text="c"))

        assert len(buf) == 2
        assert buf.entries[0].seq == 2
        assert buf.entries[1].seq == 3

    def test_at_capacity_keeps_max_turns(self) -> None:
        buf = ConversationBuffer(max_turns=3, max_chars=10000)
        for i in range(3):
            buf.append(_entry(seq=i, user_text=f"t{i}"))
        assert len(buf) == 3

    def test_under_capacity_no_drops(self) -> None:
        buf = ConversationBuffer(max_turns=5, max_chars=10000)
        buf.append(_entry(seq=1, user_text="a"))
        buf.append(_entry(seq=2, user_text="b"))
        assert len(buf) == 2


# ---------------------------------------------------------------------------
# 4.4 Character budget pruning (via update_last_user_text)
# ---------------------------------------------------------------------------


class TestCharBudget:
    def test_prune_oldest_on_user_text_update(self) -> None:
        buf = ConversationBuffer(max_turns=100, max_chars=20)
        buf.append(_entry(seq=1, user_text="aaaa", agent_text="bbbb"))  # 8
        buf.append(TurnEntry(seq=2))
        buf.update_last_user_text("cccccccccccccc")  # 14 chars, total would be 22
        # Must drop seq=1 to fit
        assert len(buf) == 1
        assert buf.entries[0].seq == 2

    def test_prune_oldest_on_agent_text_update(self) -> None:
        buf = ConversationBuffer(max_turns=100, max_chars=20)
        buf.append(_entry(seq=1, user_text="aaaa", agent_text="bbbb"))  # 8
        buf.append(TurnEntry(seq=2, user_text="cc"))  # 2, total=10
        buf.update_agent_text(2, "dddddddddddd")  # 12 chars, total would be 22
        assert len(buf) == 1
        assert buf.entries[0].seq == 2


# ---------------------------------------------------------------------------
# 4.5 format_messages structure
# ---------------------------------------------------------------------------


class TestFormatMessages:
    def test_alternating_user_assistant(self) -> None:
        buf = ConversationBuffer()
        buf.append(_entry(seq=1, user_text="hola", agent_text="Buenos días"))
        buf.append(_entry(seq=2, user_text="mi factura", agent_text="Déjame ayudarte"))

        messages = buf.format_messages()
        assert len(messages) == 4
        assert messages[0] == {"role": "user", "content": "hola"}
        assert messages[1] == {"role": "assistant", "content": "Buenos días"}
        assert messages[2] == {"role": "user", "content": "mi factura"}
        assert messages[3] == {"role": "assistant", "content": "Déjame ayudarte"}

    def test_single_entry_produces_two_messages(self) -> None:
        buf = ConversationBuffer()
        buf.append(_entry(seq=1, user_text="hola", agent_text="Hola, ¿en qué puedo ayudarte?"))
        messages = buf.format_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hola, ¿en qué puedo ayudarte?"

    def test_skips_empty_entries(self) -> None:
        buf = ConversationBuffer()
        buf.append(TurnEntry(seq=1))  # empty, should be skipped
        buf.append(_entry(seq=2, user_text="hola", agent_text="hi"))
        messages = buf.format_messages()
        assert len(messages) == 2
        assert messages[0]["content"] == "hola"

    def test_fallback_for_missing_user_text(self) -> None:
        buf = ConversationBuffer()
        buf.append(TurnEntry(seq=1, agent_text="response"))
        messages = buf.format_messages()
        assert messages[0]["content"] == "(audio)"

    def test_fallback_for_missing_agent_text(self) -> None:
        buf = ConversationBuffer()
        buf.append(TurnEntry(seq=1, user_text="hello"))
        messages = buf.format_messages()
        assert messages[1]["content"] == "(no response)"


# ---------------------------------------------------------------------------
# 4.6 update_last_user_text
# ---------------------------------------------------------------------------


class TestUpdateUserText:
    def test_updates_most_recent_entry(self) -> None:
        buf = ConversationBuffer()
        buf.append(TurnEntry(seq=1))
        buf.update_last_user_text("hola mundo")
        assert buf.entries[0].user_text == "hola mundo"

    def test_no_op_on_empty_buffer(self) -> None:
        buf = ConversationBuffer()
        buf.update_last_user_text("test")  # should not raise
        assert len(buf) == 0


# ---------------------------------------------------------------------------
# 4.7 update_agent_text
# ---------------------------------------------------------------------------


class TestUpdateAgentText:
    def test_updates_matching_seq(self) -> None:
        buf = ConversationBuffer()
        buf.append(TurnEntry(seq=1, user_text="hi"))
        buf.append(TurnEntry(seq=2, user_text="hello"))
        buf.update_agent_text(1, "response to hi")
        assert buf.entries[0].agent_text == "response to hi"
        assert buf.entries[1].agent_text == ""

    def test_no_match_does_nothing(self) -> None:
        buf = ConversationBuffer()
        buf.append(TurnEntry(seq=1, user_text="hi"))
        buf.update_agent_text(99, "orphan")  # should not raise
        assert buf.entries[0].agent_text == ""


# ---------------------------------------------------------------------------
# 4.8 Combined max_turns + max_chars pruning
# ---------------------------------------------------------------------------


class TestCombinedLimits:
    def test_max_turns_triggers_before_char_budget(self) -> None:
        buf = ConversationBuffer(max_turns=2, max_chars=10000)
        buf.append(_entry(seq=1, user_text="a"))
        buf.append(_entry(seq=2, user_text="b"))
        buf.append(_entry(seq=3, user_text="c"))
        assert len(buf) == 2
        assert buf.entries[0].seq == 2
