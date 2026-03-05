from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from src.routing.embeddings import EmbeddingEngine, get_top_two
from src.routing.lexicon import check_lexicon, check_short_utterance
from src.routing.registry import RouterRegistry
from src.voice_runtime.types import RouteALabel, RouteBLabel

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from src.routing.llm_fallback import LLMFallbackClient

logger = structlog.get_logger()


@dataclass(frozen=True)
class RoutingResult:
    route_a_label: RouteALabel
    route_a_confidence: float
    route_b_label: RouteBLabel | None = None
    route_b_confidence: float | None = None
    language: str = "es"
    short_circuit: str | None = None  # "lexicon" | "short_utterance" | None
    fallback_used: bool = False
    all_scores_a: dict[str, float] = field(default_factory=dict)
    all_scores_b: dict[str, float] = field(default_factory=dict)


class Router:
    """Full classification pipeline: language -> lexicon -> short utterance -> Route A -> Route B -> LLM fallback."""

    def __init__(
        self,
        registry: RouterRegistry,
        embedding_engine: EmbeddingEngine,
        llm_fallback: LLMFallbackClient | None = None,
        centroids_a: dict[str, dict[str, NDArray[np.float32]]] | None = None,
        centroids_b: dict[str, dict[str, NDArray[np.float32]]] | None = None,
    ) -> None:
        self._registry = registry
        self._engine = embedding_engine
        self._llm = llm_fallback
        self._centroids_a: dict[str, dict[str, NDArray[np.float32]]] = centroids_a or {}
        self._centroids_b: dict[str, dict[str, NDArray[np.float32]]] = centroids_b or {}

    def precompute_centroids(self) -> None:
        """Compute centroids for all locales at startup."""
        for locale, examples in self._registry.route_a_examples.items():
            self._centroids_a[locale] = self._engine.compute_centroids(examples)
        for locale, examples in self._registry.route_b_examples.items():
            self._centroids_b[locale] = self._engine.compute_centroids(examples)
        logger.info(
            "centroids_computed",
            route_a_locales=list(self._centroids_a.keys()),
            route_b_locales=list(self._centroids_b.keys()),
        )

    async def classify(
        self,
        text: str,
        language: str,
        enriched_text: str | None = None,
        llm_context: str | None = None,
    ) -> RoutingResult:
        """Run the full classification pipeline."""
        thresholds = self._registry.thresholds

        # Step 1: Lexicon check (always uses original text)
        lexicon = self._registry.get_lexicon(language)
        if check_lexicon(text, lexicon):
            logger.info("routing_lexicon_match", language=language)
            return RoutingResult(
                route_a_label=RouteALabel.DISALLOWED,
                route_a_confidence=1.0,
                language=language,
                short_circuit="lexicon",
            )

        # Step 2: Short utterance check (always uses original text)
        short_utts = self._registry.get_short_utterances(language)
        max_chars = thresholds.short_text_len_chars
        category = check_short_utterance(text, short_utts, max_chars)
        if category is not None:
            logger.info("routing_short_utterance_match", category=category, language=language)
            return RoutingResult(
                route_a_label=RouteALabel.SIMPLE,
                route_a_confidence=1.0,
                language=language,
                short_circuit="short_utterance",
            )

        # Step 3: Route A embedding classification (uses enriched text when available)
        embed_text = enriched_text if enriched_text is not None else text
        centroids_a = self._get_centroids_a(language)
        best_a, score_a, scores_a = self._engine.classify(embed_text, centroids_a)
        route_a_label = RouteALabel(best_a)

        # Check if ambiguous on Route A
        (top1_a, s1_a), (top2_a, s2_a) = get_top_two(scores_a)
        margin_a = s1_a - s2_a
        a_threshold = thresholds.route_a[best_a]["high"]
        is_ambiguous_a = score_a < a_threshold and margin_a < thresholds.ambiguous_margin

        # LLM fallback for ambiguous Route A
        if is_ambiguous_a and self._should_fallback():
            llm_result = await self._llm_classify_a(text, language, llm_context)
            if llm_result is not None:
                return RoutingResult(
                    route_a_label=RouteALabel(llm_result),
                    route_a_confidence=score_a,
                    language=language,
                    fallback_used=True,
                    all_scores_a=scores_a,
                )

        # Step 4: If domain, proceed to Route B
        if route_a_label == RouteALabel.DOMAIN:
            return await self._classify_route_b(
                text, language, score_a, scores_a, enriched_text, llm_context
            )

        return RoutingResult(
            route_a_label=route_a_label,
            route_a_confidence=score_a,
            language=language,
            all_scores_a=scores_a,
        )

    async def _classify_route_b(
        self,
        text: str,
        language: str,
        route_a_confidence: float,
        scores_a: dict[str, float],
        enriched_text: str | None = None,
        llm_context: str | None = None,
    ) -> RoutingResult:
        thresholds = self._registry.thresholds
        embed_text = enriched_text if enriched_text is not None else text
        centroids_b = self._get_centroids_b(language)
        best_b, score_b, scores_b = self._engine.classify(embed_text, centroids_b)

        (top1_b, s1_b), (top2_b, s2_b) = get_top_two(scores_b)
        margin_b = s1_b - s2_b
        b_threshold = thresholds.route_b[best_b]["high"]
        is_ambiguous_b = score_b < b_threshold and margin_b < thresholds.ambiguous_margin

        # LLM fallback for ambiguous Route B
        if is_ambiguous_b and self._should_fallback():
            llm_result = await self._llm_classify_b(text, language, llm_context)
            if llm_result is not None:
                return RoutingResult(
                    route_a_label=RouteALabel.DOMAIN,
                    route_a_confidence=route_a_confidence,
                    route_b_label=RouteBLabel(llm_result),
                    route_b_confidence=score_b,
                    language=language,
                    fallback_used=True,
                    all_scores_a=scores_a,
                    all_scores_b=scores_b,
                )

        # If still ambiguous without LLM, return None for route_b to signal clarify
        if is_ambiguous_b:
            return RoutingResult(
                route_a_label=RouteALabel.DOMAIN,
                route_a_confidence=route_a_confidence,
                route_b_label=None,
                route_b_confidence=score_b,
                language=language,
                all_scores_a=scores_a,
                all_scores_b=scores_b,
            )

        return RoutingResult(
            route_a_label=RouteALabel.DOMAIN,
            route_a_confidence=route_a_confidence,
            route_b_label=RouteBLabel(best_b),
            route_b_confidence=score_b,
            language=language,
            all_scores_a=scores_a,
            all_scores_b=scores_b,
        )

    def _get_centroids_a(self, language: str) -> dict[str, NDArray[np.float32]]:
        if language in self._centroids_a:
            return self._centroids_a[language]
        return self._centroids_a.get("base", {})

    def _get_centroids_b(self, language: str) -> dict[str, NDArray[np.float32]]:
        if language in self._centroids_b:
            return self._centroids_b[language]
        return self._centroids_b.get("base", {})

    def _should_fallback(self) -> bool:
        return (
            self._registry.thresholds.fallback_enable
            and self._llm is not None
        )

    async def _llm_classify_a(
        self, text: str, language: str, llm_context: str | None = None
    ) -> str | None:
        if self._llm is None:
            return None
        labels = [l.value for l in RouteALabel]
        context = llm_context if llm_context is not None else f"language={language}"
        result = await self._llm.classify(text, labels, context=context)
        if result is not None:
            logger.info("llm_fallback_route_a", label=result.label, confidence=result.confidence)
            return result.label
        return None

    async def _llm_classify_b(
        self, text: str, language: str, llm_context: str | None = None
    ) -> str | None:
        if self._llm is None:
            return None
        labels = [l.value for l in RouteBLabel]
        context = llm_context if llm_context is not None else f"language={language}"
        result = await self._llm.classify(text, labels, context=context)
        if result is not None:
            logger.info("llm_fallback_route_b", label=result.label, confidence=result.confidence)
            return result.label
        return None
