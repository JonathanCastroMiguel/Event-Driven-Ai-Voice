from __future__ import annotations

from dataclasses import dataclass

import httpx
import orjson
import structlog

from src.config import Settings

logger = structlog.get_logger()


@dataclass(frozen=True)
class LLMClassificationResult:
    label: str
    confidence: float
    raw_response: str


class LLMFallbackClient:
    """Async HTTP client for 3rd-party LLM classification fallback."""

    def __init__(self, settings: Settings) -> None:
        self._url = settings.llm_fallback_url
        self._api_key = settings.llm_fallback_api_key
        self._model = settings.llm_fallback_model
        self._timeout = settings.llm_fallback_timeout_s
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=5.0),
                limits=httpx.Limits(max_connections=10),
            )
        return self._client

    async def classify(
        self,
        text: str,
        labels: list[str],
        context: str = "",
    ) -> LLMClassificationResult | None:
        """Classify text into one of the given labels via LLM.

        Returns None on timeout or error (graceful fallback).
        """
        if not self._url:
            logger.warning("llm_fallback_not_configured")
            return None

        prompt = _build_classification_prompt(text, labels, context)
        try:
            client = await self._get_client()
            response = await client.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                content=orjson.dumps({
                    "model": self._model,
                    "temperature": 0,
                    "max_tokens": 100,
                    "messages": [
                        {"role": "system", "content": "You are a text classifier. Respond with valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                }),
            )
            response.raise_for_status()
            data = orjson.loads(response.content)
            content = data["choices"][0]["message"]["content"]
            parsed = orjson.loads(content)
            label = parsed.get("label", "")
            confidence = float(parsed.get("confidence", 0.0))

            if label not in labels:
                logger.warning("llm_fallback_invalid_label", label=label, valid=labels)
                return None

            return LLMClassificationResult(
                label=label, confidence=confidence, raw_response=content
            )
        except httpx.TimeoutException:
            logger.warning("llm_fallback_timeout", timeout_s=self._timeout)
            return None
        except Exception:
            logger.exception("llm_fallback_error")
            return None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _build_classification_prompt(text: str, labels: list[str], context: str) -> str:
    labels_str = ", ".join(f'"{l}"' for l in labels)
    parts = [
        f"Classify the following user text into exactly one of these labels: [{labels_str}].",
    ]
    if context:
        parts.append(f"Context: {context}")
    parts.append(
        f'User text: "{text}"\n\n'
        'Respond with JSON: {"label": "<chosen_label>", "confidence": <0.0-1.0>}'
    )
    return "\n".join(parts)
