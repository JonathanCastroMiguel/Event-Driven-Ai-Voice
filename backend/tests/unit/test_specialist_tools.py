"""Tests for per-department specialist tool prompts."""

from __future__ import annotations

import pytest

from src.voice_runtime.specialist_tools import (
    specialist_billing,
    specialist_retention,
    specialist_sales,
    specialist_support,
)

SAMPLE_HISTORY = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi, how can I help?"},
]


def _get_instructions(result: dict) -> str:
    return result["response"]["instructions"]


class TestSpecialistPromptDifferentiation:
    """3.1 — Each specialist returns distinct instructions."""

    @pytest.mark.asyncio
    async def test_all_specialists_produce_different_prompts(self) -> None:
        results = await _call_all("test summary", SAMPLE_HISTORY)
        instructions = [_get_instructions(r) for r in results]
        # All four must be unique
        assert len(set(instructions)) == 4

    @pytest.mark.asyncio
    async def test_payload_structure_consistent(self) -> None:
        results = await _call_all("test summary", SAMPLE_HISTORY)
        for result in results:
            assert result["type"] == "response.create"
            assert result["response"]["modalities"] == ["text", "audio"]
            assert "instructions" in result["response"]
            assert result["response"]["temperature"] == 0.8


class TestNoHardcodedSpanish:
    """3.2 — No prompt contains hardcoded Spanish translations."""

    FORBIDDEN_TERMS = ["ventas", "facturación", "soporte técnico", "retención"]

    @pytest.mark.asyncio
    async def test_no_spanish_department_labels(self) -> None:
        results = await _call_all("billing issue", SAMPLE_HISTORY)
        for result in results:
            text = _get_instructions(result).lower()
            for term in self.FORBIDDEN_TERMS:
                assert term not in text, (
                    f"Found hardcoded Spanish term '{term}' in instructions"
                )


class TestDepartmentSpecificExamples:
    """3.3 — Each prompt contains department-specific triage keywords."""

    @pytest.mark.asyncio
    async def test_sales_prompt_has_sales_keywords(self) -> None:
        result = await specialist_sales("upgrade plan", SAMPLE_HISTORY)
        text = _get_instructions(result).lower()
        assert "plan" in text
        assert "features" in text or "upgrades" in text
        assert "budget" in text

    @pytest.mark.asyncio
    async def test_billing_prompt_has_billing_keywords(self) -> None:
        result = await specialist_billing("wrong charge", SAMPLE_HISTORY)
        text = _get_instructions(result).lower()
        assert "invoice" in text or "account number" in text
        assert "charge" in text
        assert "bill" in text or "amount" in text

    @pytest.mark.asyncio
    async def test_support_prompt_has_support_keywords(self) -> None:
        result = await specialist_support("internet down", SAMPLE_HISTORY)
        text = _get_instructions(result).lower()
        assert "device" in text or "service" in text
        assert "error" in text
        assert "started" in text or "consistently" in text

    @pytest.mark.asyncio
    async def test_retention_prompt_has_retention_keywords(self) -> None:
        result = await specialist_retention("cancel service", SAMPLE_HISTORY)
        text = _get_instructions(result).lower()
        assert "cancelling" in text or "cancel" in text
        assert "how long" in text or "been with us" in text
        assert "change your mind" in text


class TestHistoryEmbedding:
    """History formatting works correctly."""

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
    summary: str, history: list[dict],
) -> list[dict]:
    return [
        await specialist_sales(summary, history),
        await specialist_billing(summary, history),
        await specialist_support(summary, history),
        await specialist_retention(summary, history),
    ]
