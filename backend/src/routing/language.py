from __future__ import annotations

import structlog

logger = structlog.get_logger()

SUPPORTED_LANGUAGES = {"es", "en"}
DEFAULT_LANGUAGE = "es"

_model = None


def _get_model():  # type: ignore[no-untyped-def]
    global _model  # noqa: PLW0603
    if _model is None:
        import fasttext

        _model = fasttext.load_model(
            str(_download_model_path())
        )
    return _model


def _download_model_path() -> str:
    import os
    from pathlib import Path

    # Check for local model first
    local = Path("models/lid.176.ftz")
    if local.exists():
        return str(local)

    # Check env var
    env_path = os.environ.get("FASTTEXT_MODEL_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # Download via huggingface_hub
    from huggingface_hub import hf_hub_download

    return hf_hub_download(
        repo_id="facebook/fasttext-language-identification",
        filename="model.bin",
    )


def detect_language(text: str) -> str:
    """Detect language of text. Returns ISO 639-1 code (e.g. 'es', 'en')."""
    try:
        model = _get_model()
        predictions = model.predict(text.replace("\n", " "), k=1)
        label = predictions[0][0]  # e.g. "__label__es"
        lang = label.replace("__label__", "")
        if lang in SUPPORTED_LANGUAGES:
            return lang
        logger.debug("unsupported_language_detected", detected=lang, fallback=DEFAULT_LANGUAGE)
        return DEFAULT_LANGUAGE
    except Exception:
        logger.exception("language_detection_error")
        return DEFAULT_LANGUAGE
