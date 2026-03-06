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
        assert result.llm_context == "language=es\nturn[-1] user: mi factura\nturn[-1] route: domain"

    def test_llm_context_for_long_text(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1)
        buf = _buffer_with("mi factura")
        result = builder.build("quiero cambiar mi plan de datos completo", "es", buf)
        assert result.llm_context == "language=es\nturn[-1] user: mi factura\nturn[-1] route: domain"
        assert result.enriched_text is None


class TestContextWindowUsesRecent:
    """5.5 — Context window of 1 uses only the most recent entry."""

    def test_uses_most_recent_entry_for_embedding(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1)
        buf = _buffer_with("first turn", "second turn", "third turn")
        result = builder.build("sí", "es", buf)
        assert result.enriched_text == "third turn. sí"

    def test_llm_context_uses_llm_context_window(self) -> None:
        builder = RoutingContextBuilder(short_text_chars=20, context_window=1, llm_context_window=3)
        buf = _buffer_with("first turn", "second turn", "third turn")
        result = builder.build("sí", "es", buf)
        assert "first turn" in (result.llm_context or "")
        assert "second turn" in (result.llm_context or "")
        assert "third turn" in (result.llm_context or "")


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


# ---------------------------------------------------------------------------
# Multi-turn LLM context tests (llm-fallback-history change)
# ---------------------------------------------------------------------------


def _buffer_with_routes(*entries: tuple[str, str]) -> ConversationBuffer:
    """Create a buffer with (user_text, route_a_label) pairs."""
    buf = ConversationBuffer(max_turns=10, max_chars=2000)
    for i, (text, route) in enumerate(entries, start=1):
        buf.append(TurnEntry(seq=i, user_text=text, route_a_label=route))
    return buf


class TestLLMContextWindowParam:
    """4.1 — Builder accepts llm_context_window and defaults to 3."""

    def test_default_llm_context_window(self) -> None:
        builder = RoutingContextBuilder()
        assert builder._llm_context_window == 3

    def test_custom_llm_context_window(self) -> None:
        builder = RoutingContextBuilder(llm_context_window=2)
        assert builder._llm_context_window == 2


class TestMultiTurnLLMContext:
    """4.2 — llm_context with 3 prior turns produces structured format."""

    def test_three_prior_turns(self) -> None:
        builder = RoutingContextBuilder(llm_context_window=3)
        buf = _buffer_with_routes(
            ("mi factura", "billing"),
            ("no me llega", "billing"),
            ("y ahora tampoco", "billing"),
        )
        result = builder.build("de este mes", "es", buf)
        expected = (
            "language=es\n"
            "turn[-3] user: mi factura\n"
            "turn[-3] route: billing\n"
            "turn[-2] user: no me llega\n"
            "turn[-2] route: billing\n"
            "turn[-1] user: y ahora tampoco\n"
            "turn[-1] route: billing"
        )
        assert result.llm_context == expected


class TestSingleTurnLLMContext:
    """4.3 — llm_context with 1 prior turn (fewer than window) produces single block."""

    def test_one_turn_with_window_3(self) -> None:
        builder = RoutingContextBuilder(llm_context_window=3)
        buf = _buffer_with_routes(("mi factura", "domain"))
        result = builder.build("de este mes", "es", buf)
        expected = (
            "language=es\n"
            "turn[-1] user: mi factura\n"
            "turn[-1] route: domain"
        )
        assert result.llm_context == expected


class TestEmptyBufferLLMContext:
    """4.4 — llm_context is None when buffer is empty."""

    def test_empty_buffer_returns_none(self) -> None:
        builder = RoutingContextBuilder(llm_context_window=3)
        buf = ConversationBuffer()
        result = builder.build("hola", "es", buf)
        assert result.llm_context is None


class TestLLMContextWindowOne:
    """4.5 — llm_context_window=1 produces single-turn format."""

    def test_window_one_single_turn(self) -> None:
        builder = RoutingContextBuilder(llm_context_window=1)
        buf = _buffer_with_routes(
            ("first", "simple"),
            ("second", "domain"),
            ("third", "billing"),
        )
        result = builder.build("current", "es", buf)
        expected = (
            "language=es\n"
            "turn[-1] user: third\n"
            "turn[-1] route: billing"
        )
        assert result.llm_context == expected


class TestEmbeddingIndependence:
    """4.6 — Embedding enrichment still uses routing_context_window (independence)."""

    def test_embedding_uses_context_window_not_llm_window(self) -> None:
        builder = RoutingContextBuilder(
            short_text_chars=20, context_window=1, llm_context_window=3
        )
        buf = _buffer_with_routes(
            ("first turn", "simple"),
            ("second turn", "domain"),
            ("third turn", "billing"),
        )
        result = builder.build("sí", "es", buf)
        # Embedding enrichment uses context_window=1 → only "third turn"
        assert result.enriched_text == "third turn. sí"
        # LLM context uses llm_context_window=3 → all 3 turns
        assert "first turn" in (result.llm_context or "")
        assert "second turn" in (result.llm_context or "")
        assert "third turn" in (result.llm_context or "")


class TestLLMContextWindowClipping:
    """4.7 — Buffer larger than window only uses most recent N entries."""

    def test_five_entries_window_three(self) -> None:
        builder = RoutingContextBuilder(llm_context_window=3)
        buf = _buffer_with_routes(
            ("turn1", "simple"),
            ("turn2", "domain"),
            ("turn3", "billing"),
            ("turn4", "support"),
            ("turn5", "retention"),
        )
        result = builder.build("current", "es", buf)
        # Only turns 3, 4, 5 should be in context
        assert "turn1" not in (result.llm_context or "")
        assert "turn2" not in (result.llm_context or "")
        assert "turn3" in (result.llm_context or "")
        assert "turn4" in (result.llm_context or "")
        assert "turn5" in (result.llm_context or "")
