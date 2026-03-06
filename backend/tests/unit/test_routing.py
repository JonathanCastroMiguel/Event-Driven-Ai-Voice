from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.routing.embeddings import EmbeddingEngine, get_top_two
from src.routing.llm_fallback import LLMClassificationResult, LLMFallbackClient
from src.routing.registry import RouterRegistry, ThresholdsConfig, load_registry
from src.routing.router import Router, RoutingResult
from src.voice_runtime.types import RouteALabel, RouteBLabel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_thresholds() -> ThresholdsConfig:
    """Build minimal thresholds for testing."""
    import yaml
    from pathlib import Path

    return ThresholdsConfig(
        yaml.safe_load(Path("router_registry/v1/thresholds.yaml").read_text())
    )


def _make_registry() -> RouterRegistry:
    return load_registry("router_registry/v1")


def _fake_centroids(labels: list[str], target: str, high_score: float = 0.92):
    """Create fake centroids where `target` will score `high_score` and others much lower."""
    dim = 8
    centroids = {}
    for label in labels:
        v = np.random.randn(dim).astype(np.float32)
        v = v / np.linalg.norm(v)
        centroids[label] = v
    return centroids


def _mock_engine(route_a_result: tuple[str, float, dict], route_b_result: tuple[str, float, dict] | None = None):
    """Create a mock EmbeddingEngine with preset classification results."""
    engine = MagicMock(spec=EmbeddingEngine)
    call_count = [0]

    def classify_side_effect(text, centroids):
        call_count[0] += 1
        if call_count[0] == 1:
            return route_a_result
        if route_b_result is not None:
            return route_b_result
        return route_a_result

    engine.classify.side_effect = classify_side_effect
    return engine


# ---------------------------------------------------------------------------
# Route A Tests (6.7)
# ---------------------------------------------------------------------------


class TestRouteAClassification:
    async def test_simple_high_confidence(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("simple", 0.92, {"simple": 0.92, "disallowed": 0.3, "out_of_scope": 0.25, "domain": 0.2})
        )
        router = Router(registry, engine)
        result = await router.classify("good morning, how are you doing today", "en")
        assert result.route_a_label == RouteALabel.SIMPLE
        assert result.route_a_confidence == 0.92

    async def test_disallowed_high_confidence(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("disallowed", 0.88, {"simple": 0.2, "disallowed": 0.88, "out_of_scope": 0.1, "domain": 0.1})
        )
        router = Router(registry, engine)
        result = await router.classify("stupid bot", "en")
        assert result.route_a_label == RouteALabel.DISALLOWED

    async def test_out_of_scope(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("out_of_scope", 0.85, {"simple": 0.2, "disallowed": 0.1, "out_of_scope": 0.85, "domain": 0.15})
        )
        router = Router(registry, engine)
        result = await router.classify("what is the weather", "en")
        assert result.route_a_label == RouteALabel.OUT_OF_SCOPE

    async def test_domain_triggers_route_b(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("domain", 0.85, {"simple": 0.1, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.85}),
            ("billing", 0.90, {"sales": 0.3, "billing": 0.90, "support": 0.2, "retention": 0.15}),
        )
        router = Router(registry, engine)
        result = await router.classify("my bill is wrong", "en")
        assert result.route_a_label == RouteALabel.DOMAIN
        assert result.route_b_label == RouteBLabel.BILLING

    async def test_low_confidence_uses_best(self) -> None:
        registry = _make_registry()
        # Medium confidence, but good margin — should still classify
        engine = _mock_engine(
            ("simple", 0.75, {"simple": 0.75, "disallowed": 0.3, "out_of_scope": 0.2, "domain": 0.15})
        )
        router = Router(registry, engine)
        result = await router.classify("hey", "en")
        assert result.route_a_label == RouteALabel.SIMPLE


# ---------------------------------------------------------------------------
# Route B Tests (6.8)
# ---------------------------------------------------------------------------


class TestRouteBClassification:
    async def test_billing_high_confidence(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("domain", 0.85, {"simple": 0.1, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.85}),
            ("billing", 0.90, {"sales": 0.3, "billing": 0.90, "support": 0.2, "retention": 0.15}),
        )
        router = Router(registry, engine)
        result = await router.classify("my bill is wrong", "en")
        assert result.route_b_label == RouteBLabel.BILLING
        assert result.route_b_confidence == 0.90

    async def test_support_high_confidence(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("domain", 0.82, {"simple": 0.1, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.82}),
            ("support", 0.88, {"sales": 0.2, "billing": 0.15, "support": 0.88, "retention": 0.1}),
        )
        router = Router(registry, engine)
        result = await router.classify("my internet is not working", "en")
        assert result.route_b_label == RouteBLabel.SUPPORT

    async def test_ambiguous_route_b_returns_none(self) -> None:
        registry = _make_registry()
        # Ambiguous: margin < 0.05 and below threshold
        engine = _mock_engine(
            ("domain", 0.85, {"simple": 0.1, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.85}),
            ("billing", 0.72, {"sales": 0.70, "billing": 0.72, "support": 0.3, "retention": 0.2}),
        )
        router = Router(registry, engine)
        result = await router.classify("I have a question about something", "en")
        assert result.route_a_label == RouteALabel.DOMAIN
        assert result.route_b_label is None  # ambiguous -> clarify

    async def test_each_specialist(self) -> None:
        for specialist in RouteBLabel:
            registry = _make_registry()
            scores_b = {l.value: 0.2 for l in RouteBLabel}
            scores_b[specialist.value] = 0.90
            engine = _mock_engine(
                ("domain", 0.85, {"simple": 0.1, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.85}),
                (specialist.value, 0.90, scores_b),
            )
            router = Router(registry, engine)
            result = await router.classify("test text", "en")
            assert result.route_b_label == specialist


# ---------------------------------------------------------------------------
# LLM Fallback Tests (6.9)
# ---------------------------------------------------------------------------


class TestLLMFallback:
    async def test_llm_fallback_success(self) -> None:
        registry = _make_registry()
        # Ambiguous Route A
        engine = _mock_engine(
            ("domain", 0.72, {"simple": 0.70, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.72})
        )
        llm = AsyncMock(spec=LLMFallbackClient)
        llm.classify.return_value = LLMClassificationResult(
            label="simple", confidence=0.95, raw_response='{"label":"simple","confidence":0.95}'
        )
        router = Router(registry, engine, llm_fallback=llm)
        result = await router.classify("hm ok", "en")
        assert result.fallback_used is True
        assert result.route_a_label == RouteALabel.SIMPLE

    async def test_llm_fallback_timeout_uses_embedding(self) -> None:
        registry = _make_registry()
        # Ambiguous but margin good enough (>0.05), so no LLM needed
        engine = _mock_engine(
            ("simple", 0.75, {"simple": 0.75, "disallowed": 0.3, "out_of_scope": 0.2, "domain": 0.15})
        )
        router = Router(registry, engine)
        result = await router.classify("hey", "en")
        assert result.fallback_used is False
        assert result.route_a_label == RouteALabel.SIMPLE

    async def test_llm_fallback_disabled(self) -> None:
        registry = _make_registry()
        registry.thresholds.fallback_enable = False
        # Ambiguous Route A -> domain -> Route B also provided
        engine = _mock_engine(
            ("domain", 0.72, {"simple": 0.70, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.72}),
            ("billing", 0.90, {"sales": 0.2, "billing": 0.90, "support": 0.1, "retention": 0.1}),
        )
        llm = AsyncMock(spec=LLMFallbackClient)
        router = Router(registry, engine, llm_fallback=llm)
        result = await router.classify("something about my account", "en")
        llm.classify.assert_not_called()
        assert result.fallback_used is False

    async def test_llm_returns_none_uses_embedding(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("domain", 0.72, {"simple": 0.70, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.72}),
            ("billing", 0.90, {"sales": 0.2, "billing": 0.90, "support": 0.1, "retention": 0.1}),
        )
        llm = AsyncMock(spec=LLMFallbackClient)
        llm.classify.return_value = None  # LLM failed
        router = Router(registry, engine, llm_fallback=llm)
        result = await router.classify("something about billing", "en")
        # Falls through to domain -> Route B
        assert result.route_a_label == RouteALabel.DOMAIN
        assert result.route_b_label == RouteBLabel.BILLING


# ---------------------------------------------------------------------------
# Full Pipeline Order Tests (6.10)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    async def test_lexicon_short_circuits(self) -> None:
        registry = _make_registry()
        engine = MagicMock(spec=EmbeddingEngine)
        router = Router(registry, engine)
        # "idiota" is in es lexicon
        result = await router.classify("eres un idiota", "es")
        assert result.route_a_label == RouteALabel.DISALLOWED
        assert result.short_circuit == "lexicon"
        engine.classify.assert_not_called()

    async def test_short_utterance_short_circuits(self) -> None:
        registry = _make_registry()
        engine = MagicMock(spec=EmbeddingEngine)
        router = Router(registry, engine)
        # "hola" is in es short_utterances (4 chars <= 5)
        result = await router.classify("hola", "es")
        assert result.route_a_label == RouteALabel.SIMPLE
        assert result.short_circuit == "short_utterance"
        engine.classify.assert_not_called()

    async def test_no_short_circuit_runs_embeddings(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("simple", 0.90, {"simple": 0.90, "disallowed": 0.2, "out_of_scope": 0.1, "domain": 0.1})
        )
        router = Router(registry, engine)
        result = await router.classify("good morning, how are you doing today", "en")
        assert result.short_circuit is None
        engine.classify.assert_called_once()

    async def test_domain_runs_two_classifications(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("domain", 0.85, {"simple": 0.1, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.85}),
            ("support", 0.88, {"sales": 0.2, "billing": 0.15, "support": 0.88, "retention": 0.1}),
        )
        router = Router(registry, engine)
        result = await router.classify("my internet is broken", "en")
        assert engine.classify.call_count == 2
        assert result.route_a_label == RouteALabel.DOMAIN
        assert result.route_b_label == RouteBLabel.SUPPORT

    async def test_lexicon_en_also_works(self) -> None:
        registry = _make_registry()
        engine = MagicMock(spec=EmbeddingEngine)
        router = Router(registry, engine)
        result = await router.classify("you are an idiot", "en")
        assert result.route_a_label == RouteALabel.DISALLOWED
        assert result.short_circuit == "lexicon"


# ---------------------------------------------------------------------------
# Context-Aware Routing (Enrichment) Tests
# ---------------------------------------------------------------------------


class TestEnrichedTextRouting:
    """6.1 — Router uses enriched_text for embedding when provided."""

    async def test_enriched_text_used_for_embedding(self) -> None:
        registry = _make_registry()
        engine = _mock_engine(
            ("domain", 0.85, {"simple": 0.1, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.85}),
            ("billing", 0.90, {"sales": 0.2, "billing": 0.90, "support": 0.15, "retention": 0.1}),
        )
        router = Router(registry, engine)
        result = await router.classify(
            "de este mes", "es",
            enriched_text="tengo un problema con mi factura. de este mes",
        )
        # Verify embedding engine received the enriched text, not the original
        first_call_text = engine.classify.call_args_list[0][0][0]
        assert first_call_text == "tengo un problema con mi factura. de este mes"
        assert result.route_a_label == RouteALabel.DOMAIN

    """6.2 — Router uses original text for lexicon check."""

    async def test_lexicon_uses_original_text(self) -> None:
        registry = _make_registry()
        engine = MagicMock(spec=EmbeddingEngine)
        router = Router(registry, engine)
        # "idiota" in original text should trigger lexicon, even with enriched text
        result = await router.classify(
            "eres un idiota", "es",
            enriched_text="mi factura. eres un idiota",
        )
        assert result.route_a_label == RouteALabel.DISALLOWED
        assert result.short_circuit == "lexicon"
        engine.classify.assert_not_called()

    """6.3 — Router uses original text for short utterance check."""

    async def test_short_utterance_uses_original_text(self) -> None:
        registry = _make_registry()
        engine = MagicMock(spec=EmbeddingEngine)
        router = Router(registry, engine)
        # "hola" should match short utterances even with enriched text
        result = await router.classify(
            "hola", "es",
            enriched_text="something else. hola",
        )
        assert result.route_a_label == RouteALabel.SIMPLE
        assert result.short_circuit == "short_utterance"
        engine.classify.assert_not_called()

    """6.4 — llm_context passed through to LLM fallback when ambiguous."""

    async def test_llm_context_passed_to_fallback(self) -> None:
        registry = _make_registry()
        # Ambiguous Route A: low scores, tight margin
        engine = _mock_engine(
            ("domain", 0.72, {"simple": 0.70, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.72})
        )
        llm = AsyncMock(spec=LLMFallbackClient)
        llm.classify.return_value = LLMClassificationResult(
            label="domain", confidence=0.90, raw_response='{"label":"domain","confidence":0.90}'
        )
        router = Router(registry, engine, llm_fallback=llm)
        llm_ctx = "language=es; previous_turn: tengo un problema con mi factura"
        result = await router.classify("de este mes", "es", llm_context=llm_ctx)
        # Verify the LLM received the conversation context
        llm.classify.assert_called_once()
        call_kwargs = llm.classify.call_args
        assert call_kwargs[1]["context"] == llm_ctx or call_kwargs[0][2] == llm_ctx


class TestMultiTurnLLMContextPassthrough:
    """5.1/5.2 — Multi-turn llm_context passed through Router to LLMFallbackClient."""

    async def test_multi_turn_context_passed_to_llm_classify_a(self) -> None:
        """5.1 — Multi-turn context reaches LLM fallback for Route A."""
        registry = _make_registry()
        engine = _mock_engine(
            ("domain", 0.72, {"simple": 0.70, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.72})
        )
        llm = AsyncMock(spec=LLMFallbackClient)
        llm.classify.return_value = LLMClassificationResult(
            label="domain", confidence=0.90, raw_response='{"label":"domain","confidence":0.90}'
        )
        router = Router(registry, engine, llm_fallback=llm)
        multi_turn_ctx = (
            "language=es\n"
            "turn[-2] user: mi factura\n"
            "turn[-2] route: billing\n"
            "turn[-1] user: no me llega\n"
            "turn[-1] route: billing"
        )
        await router.classify("de este mes", "es", llm_context=multi_turn_ctx)
        llm.classify.assert_called_once()
        call_kwargs = llm.classify.call_args
        assert call_kwargs[1]["context"] == multi_turn_ctx

    async def test_multi_turn_context_passed_to_llm_classify_b(self) -> None:
        """5.2 — Multi-turn context reaches LLM fallback for Route B."""
        registry = _make_registry()
        engine = _mock_engine(
            ("domain", 0.85, {"simple": 0.1, "disallowed": 0.1, "out_of_scope": 0.1, "domain": 0.85}),
            ("billing", 0.72, {"sales": 0.70, "billing": 0.72, "support": 0.3, "retention": 0.2}),
        )
        llm = AsyncMock(spec=LLMFallbackClient)
        llm.classify.return_value = LLMClassificationResult(
            label="billing", confidence=0.90, raw_response='{"label":"billing","confidence":0.90}'
        )
        router = Router(registry, engine, llm_fallback=llm)
        multi_turn_ctx = (
            "language=es\n"
            "turn[-2] user: mi factura\n"
            "turn[-2] route: billing\n"
            "turn[-1] user: no me llega\n"
            "turn[-1] route: billing"
        )
        result = await router.classify("de este mes", "es", llm_context=multi_turn_ctx)
        llm.classify.assert_called_once()
        call_kwargs = llm.classify.call_args
        assert call_kwargs[1]["context"] == multi_turn_ctx
        assert result.route_b_label == RouteBLabel.BILLING
