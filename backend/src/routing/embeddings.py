from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from sentence_transformers import SentenceTransformer

logger = structlog.get_logger()

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingEngine:
    """Manages embedding model, centroid computation, and cosine similarity scoring."""

    def __init__(self, model: SentenceTransformer) -> None:
        self._model = model
        self._centroids: dict[str, NDArray[np.float32]] = {}

    @classmethod
    def load(cls, model_name: str = DEFAULT_MODEL_NAME) -> EmbeddingEngine:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        logger.info("embedding_model_loaded", model=model_name)
        return cls(model=model)

    def compute_centroids(
        self, examples: dict[str, list[str]], prefix: str = ""
    ) -> dict[str, NDArray[np.float32]]:
        """Compute centroids from text examples per class. Returns and caches them."""
        centroids: dict[str, NDArray[np.float32]] = {}
        for label, texts in examples.items():
            if not texts:
                continue
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            centroid = np.mean(embeddings, axis=0).astype(np.float32)
            # Normalize the centroid
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
            key = f"{prefix}{label}" if prefix else label
            centroids[key] = centroid
            self._centroids[key] = centroid
        return centroids

    def embed_text(self, text: str) -> NDArray[np.float32]:
        """Embed a single text string."""
        embedding = self._model.encode([text], normalize_embeddings=True)
        return embedding[0].astype(np.float32)

    def score_against_centroids(
        self, text_embedding: NDArray[np.float32], centroids: dict[str, NDArray[np.float32]]
    ) -> dict[str, float]:
        """Compute cosine similarity between text embedding and each centroid."""
        scores: dict[str, float] = {}
        for label, centroid in centroids.items():
            similarity = float(np.dot(text_embedding, centroid))
            scores[label] = similarity
        return scores

    def classify(
        self, text: str, centroids: dict[str, NDArray[np.float32]]
    ) -> tuple[str, float, dict[str, float]]:
        """Classify text against centroids. Returns (best_label, best_score, all_scores)."""
        embedding = self.embed_text(text)
        scores = self.score_against_centroids(embedding, centroids)
        best_label = max(scores, key=scores.get)  # type: ignore[arg-type]
        return best_label, scores[best_label], scores


def get_top_two(scores: dict[str, float]) -> tuple[tuple[str, float], tuple[str, float]]:
    """Get top-2 labels by score. Returns ((label1, score1), (label2, score2))."""
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_items) < 2:
        return (sorted_items[0], (sorted_items[0][0], 0.0))
    return (sorted_items[0], sorted_items[1])
