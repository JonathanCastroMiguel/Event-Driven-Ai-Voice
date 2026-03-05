"""Unit tests for ConversationBuffer (tasks 4.1–4.9)."""

from __future__ import annotations

from src.voice_runtime.conversation_buffer import ConversationBuffer, TurnEntry


def _entry(
    seq: int = 1,
    user_text: str = "hola",
    route_a_label: str = "simple",
    policy_key: str | None = "greeting",
    specialist: str | None = None,
) -> TurnEntry:
    return TurnEntry(
        seq=seq,
        user_text=user_text,
        route_a_label=route_a_label,
        policy_key=policy_key,
        specialist=specialist,
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
# 4.4 Character budget pruning
# ---------------------------------------------------------------------------


class TestCharBudget:
    def test_drops_oldest_to_fit_within_max_chars(self) -> None:
        buf = ConversationBuffer(max_turns=100, max_chars=10)
        buf.append(_entry(seq=1, user_text="aaaa"))  # 4 chars
        buf.append(_entry(seq=2, user_text="bbbb"))  # 4 chars, total=8
        buf.append(_entry(seq=3, user_text="cccccc"))  # 6 chars, total would be 14

        # Must drop seq=1 (4 chars) -> total=10, fits
        assert len(buf) == 2
        assert buf.entries[0].seq == 2
        assert buf.entries[1].seq == 3

    def test_drops_multiple_oldest_if_needed(self) -> None:
        buf = ConversationBuffer(max_turns=100, max_chars=10)
        buf.append(_entry(seq=1, user_text="aaaa"))  # 4
        buf.append(_entry(seq=2, user_text="bbbb"))  # 4, total=8
        buf.append(_entry(seq=3, user_text="cccccccc"))  # 8, total would be 16

        # Must drop seq=1 (4) -> 12 still > 10, drop seq=2 (4) -> 8, fits
        assert len(buf) == 1
        assert buf.entries[0].seq == 3


# ---------------------------------------------------------------------------
# 4.5 Single entry exceeding entire budget
# ---------------------------------------------------------------------------


class TestSingleEntryExceedsBudget:
    def test_clears_buffer_stores_entry_as_is(self) -> None:
        buf = ConversationBuffer(max_turns=100, max_chars=5)
        buf.append(_entry(seq=1, user_text="ab"))
        buf.append(_entry(seq=2, user_text="abcdefghij"))  # 10 > 5

        assert len(buf) == 1
        assert buf.entries[0].seq == 2
        assert buf.entries[0].user_text == "abcdefghij"  # not truncated


# ---------------------------------------------------------------------------
# 4.6 format_messages structure
# ---------------------------------------------------------------------------


class TestFormatMessages:
    def test_alternating_user_assistant(self) -> None:
        buf = ConversationBuffer()
        buf.append(_entry(seq=1, user_text="hola", policy_key="greeting"))
        buf.append(_entry(seq=2, user_text="mi factura", route_a_label="domain", specialist="billing"))

        messages = buf.format_messages()
        assert len(messages) == 4
        assert messages[0] == {"role": "user", "content": "hola"}
        assert messages[1]["role"] == "assistant"
        assert messages[2] == {"role": "user", "content": "mi factura"}
        assert messages[3]["role"] == "assistant"

    def test_single_entry_produces_two_messages(self) -> None:
        buf = ConversationBuffer()
        buf.append(_entry(seq=1, user_text="hola", policy_key="greeting"))
        messages = buf.format_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# 4.7 Assistant message format: guided response
# ---------------------------------------------------------------------------


class TestAssistantFormatGuided:
    def test_policy_key_set_specialist_none(self) -> None:
        buf = ConversationBuffer()
        buf.append(_entry(policy_key="greeting", specialist=None))
        messages = buf.format_messages()
        assert messages[1]["content"] == "[greeting] Guided response"

    def test_fallback_no_policy_no_specialist(self) -> None:
        buf = ConversationBuffer()
        buf.append(_entry(policy_key=None, specialist=None, route_a_label="simple"))
        messages = buf.format_messages()
        assert messages[1]["content"] == "[simple] Response"


# ---------------------------------------------------------------------------
# 4.8 Assistant message format: specialist action
# ---------------------------------------------------------------------------


class TestAssistantFormatSpecialist:
    def test_specialist_set(self) -> None:
        buf = ConversationBuffer()
        buf.append(_entry(route_a_label="domain", specialist="billing", policy_key=None))
        messages = buf.format_messages()
        assert messages[1]["content"] == "[domain] Specialist: billing"

    def test_specialist_takes_precedence_over_policy_key(self) -> None:
        buf = ConversationBuffer()
        buf.append(_entry(route_a_label="domain", specialist="billing", policy_key="greeting"))
        messages = buf.format_messages()
        # specialist is not None, so specialist format is used
        assert messages[1]["content"] == "[domain] Specialist: billing"


# ---------------------------------------------------------------------------
# 4.9 Combined max_turns + max_chars pruning
# ---------------------------------------------------------------------------


class TestCombinedLimits:
    def test_max_turns_triggers_before_char_budget(self) -> None:
        buf = ConversationBuffer(max_turns=2, max_chars=10000)
        buf.append(_entry(seq=1, user_text="a"))
        buf.append(_entry(seq=2, user_text="b"))
        buf.append(_entry(seq=3, user_text="c"))
        assert len(buf) == 2
        assert buf.entries[0].seq == 2

    def test_char_budget_triggers_before_max_turns(self) -> None:
        buf = ConversationBuffer(max_turns=100, max_chars=5)
        buf.append(_entry(seq=1, user_text="aaa"))  # 3
        buf.append(_entry(seq=2, user_text="bbb"))  # 3, total would be 6 > 5
        assert len(buf) == 1
        assert buf.entries[0].seq == 2

    def test_both_limits_active(self) -> None:
        buf = ConversationBuffer(max_turns=3, max_chars=8)
        buf.append(_entry(seq=1, user_text="aa"))   # 2
        buf.append(_entry(seq=2, user_text="bb"))   # 2, total=4
        buf.append(_entry(seq=3, user_text="cc"))   # 2, total=6, turns=3 (at max)
        buf.append(_entry(seq=4, user_text="dddd"))  # 4, turns would be 4 > 3

        # max_turns drops seq=1 first -> [2,3], chars=4, new total=8 <= 8
        assert len(buf) == 3
        assert buf.entries[0].seq == 2
        assert buf.entries[2].seq == 4
