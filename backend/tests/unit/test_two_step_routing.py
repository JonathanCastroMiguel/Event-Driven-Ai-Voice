"""Unit tests for two-step routing: Department.DIRECT parsing, specialist tools, coordinator delegation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.routing.model_router import (
    Department,
    ModelRouterAction,
    parse_function_call_action,
)
from src.voice_runtime.specialist_tools import (
    register_specialist_tools,
    specialist_billing,
    specialist_retention,
    specialist_sales,
    specialist_support,
)


# ---------------------------------------------------------------------------
# 7.1 — parse_function_call_action with department="direct"
# ---------------------------------------------------------------------------


class TestParseFunctionCallDirect:
    def test_direct_department_parsed(self) -> None:
        result = parse_function_call_action(
            "route_to_specialist",
            '{"department": "direct", "summary": "greeting"}',
        )
        assert result is not None
        assert result.department == Department.DIRECT
        assert result.summary == "greeting"

    def test_all_departments_parsed(self) -> None:
        for dept in Department:
            result = parse_function_call_action(
                "route_to_specialist",
                f'{{"department": "{dept.value}", "summary": "test"}}',
            )
            assert result is not None
            assert result.department == dept

    def test_wrong_function_name_returns_none(self) -> None:
        result = parse_function_call_action(
            "some_other_function",
            '{"department": "direct", "summary": "test"}',
        )
        assert result is None

    def test_invalid_json_returns_none(self) -> None:
        result = parse_function_call_action(
            "route_to_specialist",
            '{"department": ',
        )
        assert result is None

    def test_unknown_department_returns_none(self) -> None:
        result = parse_function_call_action(
            "route_to_specialist",
            '{"department": "unknown", "summary": "test"}',
        )
        assert result is None


# ---------------------------------------------------------------------------
# 7.2 — Mock specialist tool returns valid response.create payload
# ---------------------------------------------------------------------------


class TestSpecialistTools:
    @pytest.mark.asyncio
    async def test_returns_response_create_payload(self) -> None:
        result = await specialist_retention(
            summary="wants to cancel",
            history=[
                {"role": "user", "content": "quiero cancelar"},
            ],
        )
        assert result["type"] == "response.create"
        assert result["response"]["modalities"] == ["text", "audio"]
        assert "instructions" in result["response"]

    @pytest.mark.asyncio
    async def test_history_embedded_in_instructions(self) -> None:
        history = [
            {"role": "user", "content": "me cobraron de más"},
            {"role": "assistant", "content": "entiendo, déjeme revisar"},
        ]
        result = await specialist_billing(summary="overcharge", history=history)
        instructions = result["response"]["instructions"]
        assert "User: me cobraron de más" in instructions
        assert "Assistant: entiendo, déjeme revisar" in instructions
        assert "Conversation history:" in instructions

    @pytest.mark.asyncio
    async def test_empty_history_no_history_section(self) -> None:
        result = await specialist_sales(summary="upgrade", history=[])
        instructions = result["response"]["instructions"]
        assert "Conversation history:" not in instructions

    @pytest.mark.asyncio
    async def test_none_history_handled(self) -> None:
        result = await specialist_support(summary="internet down")
        assert result["type"] == "response.create"

    @pytest.mark.asyncio
    async def test_each_department_has_correct_identity(self) -> None:
        for tool, dept in [
            (specialist_sales, "sales"),
            (specialist_billing, "billing"),
            (specialist_support, "support"),
            (specialist_retention, "retention"),
        ]:
            result = await tool(summary="test")
            assert dept in result["response"]["instructions"]

    @pytest.mark.asyncio
    async def test_triage_steps_in_instructions(self) -> None:
        result = await specialist_retention(summary="cancel")
        instructions = result["response"]["instructions"]
        assert "triage has 3 steps" in instructions
        assert "clarifying questions" in instructions

    @pytest.mark.asyncio
    async def test_language_instruction_present(self) -> None:
        result = await specialist_billing(summary="test")
        instructions = result["response"]["instructions"]
        assert "same language" in instructions

    def test_register_specialist_tools(self) -> None:
        executor = MagicMock()
        register_specialist_tools(executor)
        assert executor.register_tool.call_count == 4
        registered_names = {call.args[0] for call in executor.register_tool.call_args_list}
        assert registered_names == {
            "specialist_sales",
            "specialist_billing",
            "specialist_support",
            "specialist_retention",
        }
