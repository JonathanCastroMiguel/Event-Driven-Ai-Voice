from __future__ import annotations


def check_lexicon(text: str, disallowed: set[str]) -> bool:
    """Check if text contains any disallowed word/phrase. Case-insensitive."""
    text_lower = text.lower()
    return any(word in text_lower for word in disallowed)


def check_short_utterance(
    text: str, short_utterances: dict[str, list[str]], max_chars: int
) -> str | None:
    """Check if text matches a short utterance category.

    Returns the category name (e.g. 'greetings', 'acknowledgements') or None.
    """
    normalized = text.strip().lower()
    if len(normalized) > max_chars:
        return None
    for category, phrases in short_utterances.items():
        if normalized in phrases:
            return category
    return None
