"""Context enrichment for routing classification of short follow-up turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.voice_runtime.conversation_buffer import ConversationBuffer


@dataclass(frozen=True)
class RoutingContext:
    """Enriched classification inputs produced by the context builder."""

    enriched_text: str | None = None
    llm_context: str | None = None


class RoutingContextBuilder:
    """Builds enriched classification inputs from conversation history.

    Layer 1 (embedding enrichment): For short texts, concatenates the previous
    turn's user_text to produce a richer embedding input.

    Layer 2 (LLM fallback context): Always produces a context string with the
    previous turn when the buffer is non-empty.
    """

    def __init__(
        self,
        short_text_chars: int = 20,
        context_window: int = 1,
    ) -> None:
        self._short_text_chars = short_text_chars
        self._context_window = context_window

    def build(
        self,
        user_text: str,
        language: str,
        buffer: ConversationBuffer,
    ) -> RoutingContext:
        """Produce enriched text and LLM context from the conversation buffer.

        Returns a RoutingContext with:
        - enriched_text: concatenated text for embeddings (or None if not needed)
        - llm_context: context string for LLM fallback (or None on first turn)
        """
        if len(buffer) == 0:
            return RoutingContext()

        recent = buffer.entries[-self._context_window :]
        prev_text = recent[-1].user_text

        # Layer 1: embedding enrichment for short texts
        enriched_text: str | None = None
        if len(user_text) < self._short_text_chars:
            enriched_text = f"{prev_text}. {user_text}"

        # Layer 2: LLM fallback context (always when buffer non-empty)
        llm_context = f"language={language}; previous_turn: {prev_text}"

        return RoutingContext(enriched_text=enriched_text, llm_context=llm_context)
