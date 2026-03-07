"""History formatting for conversation context in routing prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.voice_runtime.conversation_buffer import ConversationBuffer


def format_history(buffer: ConversationBuffer) -> list[dict[str, str]]:
    """Return conversation history as alternating user/assistant message pairs.

    This is the simplified version for model-as-router architecture.
    The model receives history via response.create input messages.
    """
    return buffer.format_messages()
