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

    Layer 2 (LLM fallback context): Produces a structured multi-turn context
    string with up to llm_context_window prior turns when the buffer is non-empty.
    """

    def __init__(
        self,
        short_text_chars: int = 20,
        context_window: int = 1,
        llm_context_window: int = 3,
    ) -> None:
        self._short_text_chars = short_text_chars
        self._context_window = context_window
        self._llm_context_window = llm_context_window

    def build(
        self,
        user_text: str,
        language: str,
        buffer: ConversationBuffer,
    ) -> RoutingContext:
        """Produce enriched text and LLM context from the conversation buffer.

        Returns a RoutingContext with:
        - enriched_text: concatenated text for embeddings (or None if not needed)
        - llm_context: structured multi-turn context for LLM fallback (or None on first turn)
        """
        if len(buffer) == 0:
            return RoutingContext()

        # Layer 1: embedding enrichment for short texts (uses context_window)
        embed_entries = buffer.entries[-self._context_window :]
        prev_text = embed_entries[-1].user_text
        enriched_text: str | None = None
        if len(user_text) < self._short_text_chars:
            enriched_text = f"{prev_text}. {user_text}"

        # Layer 2: multi-turn LLM fallback context (uses llm_context_window)
        llm_entries = buffer.entries[-self._llm_context_window :]
        lines: list[str] = [f"language={language}"]
        total = len(llm_entries)
        for i, entry in enumerate(llm_entries):
            offset = -(total - i)
            lines.append(f"turn[{offset}] user: {entry.user_text}")
            lines.append(f"turn[{offset}] route: {entry.route_a_label}")
        llm_context = "\n".join(lines)

        return RoutingContext(enriched_text=enriched_text, llm_context=llm_context)
