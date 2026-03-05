"""Unit tests for RoutingContextBuilder."""

from __future__ import annotations

import pytest

from src.routing.context import RoutingContextBuilder
from src.voice_runtime.conversation_buffer import ConversationBuffer, TurnEntry


def _buffer_with(*texts: str) -> ConversationBuffer:
    """Create a ConversationBuffer pre-filled with entries."""
    buf = ConversationBuffer(max_turns=10, max_chars=2000)
    for i, text in enumerate(texts, start=1):
        buf.append(TurnEntry(seq=i, user_text=text, route_a_label="domain"))
    return buf


class TestShortTextEnrichment:
    """5.1 — Short text with non-empty buffer returns enriched text."""

    def test_short_text_enriched(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1)
        buf = _buffer_with("tengo un problema con mi factura")
        result = builder.build("de este mes", "es", buf)
        assert result.enriched_text == "tengo un problema con mi factura. de este mes"

    def test_short_text_exactly_at_threshold_not_enriched(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1)
        buf = _buffer_with("something prior")
        text = "x" * 20  # exactly 20 chars
        result = builder.build(text, "es", buf)
        assert result.enriched_text is None


class TestLongTextNoEnrichment:
    """5.2 — Long text returns enriched_text=None."""

    def test_long_text_not_enriched(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1)
        buf = _buffer_with("prior turn text")
        result = builder.build("quiero cambiar mi plan de datos a uno más barato", "es", buf)
        assert result.enriched_text is None


class TestEmptyBufferNoEnrichment:
    """5.3 — Empty buffer returns both outputs as None."""

    def test_empty_buffer(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1)
        buf = ConversationBuffer()
        result = builder.build("hola", "es", buf)
        assert result.enriched_text is None
        assert result.llm_context is None


class TestLLMContextAlwaysProduced:
    """5.4 — llm_context always produced when buffer is non-empty."""

    def test_llm_context_for_short_text(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1)
        buf = _buffer_with("mi factura")
        result = builder.build("sí", "es", buf)
        assert result.llm_context == "language=es; previous_turn: mi factura"

    def test_llm_context_for_long_text(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1)
        buf = _buffer_with("mi factura")
        result = builder.build("quiero cambiar mi plan de datos completo", "es", buf)
        assert result.llm_context == "language=es; previous_turn: mi factura"
        assert result.enriched_text is None


class TestContextWindowUsesRecent:
    """5.5 — Context window of 1 uses only the most recent entry."""

    def test_uses_most_recent_entry(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1)
        buf = _buffer_with("first turn", "second turn", "third turn")
        result = builder.build("sí", "es", buf)
        assert result.enriched_text == "third turn. sí"
        assert "third turn" in (result.llm_context or "")
        assert "first turn" not in (result.llm_context or "")


class TestCustomThreshold:
    """5.6 — Custom short_text_chars threshold."""

    def test_custom_threshold_30(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=30, context_window=1)
        buf = _buffer_with("prior text")
        # 25 chars — below 30 threshold, should be enriched
        text = "quiero ver mi factura"  # 21 chars
        result = builder.build(text, "es", buf)
        assert result.enriched_text is not None
        assert result.enriched_text == f"prior text. {text}"

    def test_threshold_zero_disables_enrichment(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=0, context_window=1)
        buf = _buffer_with("prior text")
        result = builder.build("sí", "es", buf)
        assert result.enriched_text is None
        # LLM context still produced
        assert result.llm_context is not None
