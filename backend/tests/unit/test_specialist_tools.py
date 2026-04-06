"""Tests for specialist tools: text model integration and fallback behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.voice_runtime import specialist_tools
from src.voice_runtime.specialist_tools import (
    _call_text_model,
    specialist_billing,
    specialist_retention,
    specialist_sales,
    specialist_support,
)

SAMPLE_HISTORY = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi, how can I help?"},
]


def _get_instructions(result: dict[str, Any]) -> str:
    return result["response"]["instructions"]


# ---------------------------------------------------------------------------
# _call_text_model tests
# ---------------------------------------------------------------------------


def _make_mock_response(
    content: str = "test response", status_code: int = 200
) -> MagicMock:
    """Create a non-async mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
    }
    return resp


class TestCallTextModel:
    """Unit tests for _call_text_model."""

    @pytest.mark.asyncio
    async def test_success_returns_text(self) -> None:
        mock_resp = _make_mock_response("I understand you need a refund. Could you provide your invoice number?")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        original_client = specialist_tools._client
        specialist_tools._client = mock_client
        try:
            result = await _call_text_model("system prompt", "user message")
            assert result == "I understand you need a refund. Could you provide your invoice number?"
            mock_client.post.assert_called_once()
        finally:
            specialist_tools._client = original_client

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException("timeout")

        original_client = specialist_tools._client
        specialist_tools._client = mock_client
        try:
            result = await _call_text_model("system prompt", "user message")
            assert result is None
        finally:
            specialist_tools._client = original_client

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
            response=httpx.Response(500),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        original_client = specialist_tools._client
        specialist_tools._client = mock_client
        try:
            result = await _call_text_model("system prompt", "user message")
            assert result is None
        finally:
            specialist_tools._client = original_client

    @pytest.mark.asyncio
    async def test_empty_content_returns_none(self) -> None:
        mock_resp = _make_mock_response("")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        original_client = specialist_tools._client
        specialist_tools._client = mock_client
        try:
            result = await _call_text_model("system prompt", "user message")
            assert result is None
        finally:
            specialist_tools._client = original_client

    @pytest.mark.asyncio
    async def test_client_not_configured_returns_none(self) -> None:
        original_client = specialist_tools._client
        specialist_tools._client = None
        try:
            result = await _call_text_model("system prompt", "user message")
            assert result is None
        finally:
            specialist_tools._client = original_client


# ---------------------------------------------------------------------------
# Specialist tool tests — text model success path
# ---------------------------------------------------------------------------


class TestSpecialistToolsTextModelSuccess:
    """When text model succeeds, specialist tools return str."""

    @pytest.fixture(autouse=True)
    def _mock_text_model(self) -> Any:
        with patch.object(
            specialist_tools,
            "_call_text_model",
            new_callable=AsyncMock,
            return_value="Entiendo que necesitas un reembolso. ¿Podrías indicarme tu número de factura?",
        ) as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_billing_returns_str(self) -> None:
        result = await specialist_billing("refund request", SAMPLE_HISTORY)
        assert isinstance(result, str)
        assert "reembolso" in result

    @pytest.mark.asyncio
    async def test_sales_returns_str(self) -> None:
        result = await specialist_sales("upgrade plan", SAMPLE_HISTORY)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_support_returns_str(self) -> None:
        result = await specialist_support("internet down", SAMPLE_HISTORY)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_retention_returns_str(self) -> None:
        result = await specialist_retention("cancel service", SAMPLE_HISTORY)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Specialist tool tests — fallback path (text model fails)
# ---------------------------------------------------------------------------


class TestSpecialistToolsFallback:
    """When text model fails, specialist tools return response.create dict."""

    @pytest.fixture(autouse=True)
    def _mock_text_model_failure(self) -> Any:
        with patch.object(
            specialist_tools,
            "_call_text_model",
            new_callable=AsyncMock,
            return_value=None,
        ):
            yield

    @pytest.mark.asyncio
    async def test_billing_returns_dict_on_fallback(self) -> None:
        result = await specialist_billing("refund request", SAMPLE_HISTORY)
        assert isinstance(result, dict)
        assert result["type"] == "response.create"
        assert "billing" in _get_instructions(result).lower()

    @pytest.mark.asyncio
    async def test_all_fallbacks_produce_different_prompts(self) -> None:
        results = await _call_all("test summary", SAMPLE_HISTORY)
        instructions = [_get_instructions(r) for r in results]
        assert len(set(instructions)) == 4

    @pytest.mark.asyncio
    async def test_payload_structure_consistent(self) -> None:
        results = await _call_all("test summary", SAMPLE_HISTORY)
        for result in results:
            assert isinstance(result, dict)
            assert result["type"] == "response.create"
            assert result["response"]["modalities"] == ["text", "audio"]
            assert "instructions" in result["response"]


# ---------------------------------------------------------------------------
# Specialist tool tests — client not configured
# ---------------------------------------------------------------------------


class TestSpecialistToolsNotConfigured:
    """When httpx client is not configured, tools fall back without error."""

    @pytest.fixture(autouse=True)
    def _no_client(self) -> Any:
        original = specialist_tools._client
        specialist_tools._client = None
        yield
        specialist_tools._client = original

    @pytest.mark.asyncio
    async def test_billing_falls_back_when_not_configured(self) -> None:
        result = await specialist_billing("refund request", SAMPLE_HISTORY)
        assert isinstance(result, dict)
        assert result["type"] == "response.create"


# ---------------------------------------------------------------------------
# History embedding (preserved from original tests)
# ---------------------------------------------------------------------------


class TestHistoryEmbedding:
    """History formatting works correctly in fallback path."""

    @pytest.fixture(autouse=True)
    def _mock_text_model_failure(self) -> Any:
        with patch.object(
            specialist_tools,
            "_call_text_model",
            new_callable=AsyncMock,
            return_value=None,
        ):
            yield

    @pytest.mark.asyncio
    async def test_history_embedded_in_instructions(self) -> None:
        result = await specialist_sales("test", SAMPLE_HISTORY)
        text = _get_instructions(result)
        assert "Conversation history:" in text
        assert "User: Hello" in text
        assert "Assistant: Hi, how can I help?" in text

    @pytest.mark.asyncio
    async def test_empty_history_no_block(self) -> None:
        result = await specialist_sales("test", [])
        text = _get_instructions(result)
        assert "Conversation history:" not in text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _call_all(
    summary: str, history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        await specialist_sales(summary, history),
        await specialist_billing(summary, history),
        await specialist_support(summary, history),
        await specialist_retention(summary, history),
    ]
