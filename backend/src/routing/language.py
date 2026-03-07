from __future__ import annotations

import langid
import structlog

logger = structlog.get_logger()

SUPPORTED_LANGUAGES = {"es", "en"}
DEFAULT_LANGUAGE = "es"

# Restrict langid to only the languages we support (faster + more accurate)
langid.set_languages(list(SUPPORTED_LANGUAGES))


def detect_language(text: str) -> str:
    """Detect language of text. Returns ISO 639-1 code (e.g. 'es', 'en')."""
    try:
        lang, confidence = langid.classify(text)
        if lang in SUPPORTED_LANGUAGES:
            return lang
        return DEFAULT_LANGUAGE
    except Exception:
        logger.warning("language_detection_error", fallback=DEFAULT_LANGUAGE)
        return DEFAULT_LANGUAGE
