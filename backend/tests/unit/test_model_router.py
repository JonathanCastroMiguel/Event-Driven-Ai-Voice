"""Unit tests for model router: RouterPromptBuilder, parse_model_action, load_router_prompt."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.routing.model_router import (
    Department,
    ModelRouterAction,
    RouterPromptBuilder,
    RouterPromptTemplate,
    load_router_prompt,
    parse_model_action,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def template() -> RouterPromptTemplate:
    return RouterPromptTemplate(
        identity="You are a test assistant.",
        decision_rules="Speak directly or return JSON.",
        departments="sales, billing, support, retention",
        guardrails="Be safe.",
        language_instruction="Respond in user's language.",
    )


@pytest.fixture
def builder(template: RouterPromptTemplate) -> RouterPromptBuilder:
    return RouterPromptBuilder(template)


# ---------------------------------------------------------------------------
# RouterPromptBuilder tests
# ---------------------------------------------------------------------------


class TestRouterPromptBuilder:
    def test_build_first_turn_empty_history(self, builder: RouterPromptBuilder) -> None:
        payload = builder.build_response_create(history=[])

        assert payload["type"] == "response.create"
        assert payload["response"]["modalities"] == ["text", "audio"]
        assert "You are a test assistant." in payload["response"]["instructions"]
        assert "input" not in payload["response"]

    def test_build_with_history(self, builder: RouterPromptBuilder) -> None:
        history = [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "[greeting] Guided response"},
        ]
        payload = builder.build_response_create(history=history)

        assert "input" in payload["response"]
        input_msgs = payload["response"]["input"]
        assert len(input_msgs) == 2
        assert input_msgs[0]["role"] == "user"
        assert input_msgs[0]["content"][0]["text"] == "hola"
        assert input_msgs[1]["role"] == "assistant"

    def test_build_with_multi_turn_history(self, builder: RouterPromptBuilder) -> None:
        history = [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "greeting response"},
            {"role": "user", "content": "mi factura"},
            {"role": "assistant", "content": "[billing] Specialist: billing"},
        ]
        payload = builder.build_response_create(history=history)

        input_msgs = payload["response"]["input"]
        assert len(input_msgs) == 4

    def test_instructions_contain_all_sections(self, builder: RouterPromptBuilder) -> None:
        instructions = builder.system_instruction
        assert "You are a test assistant." in instructions
        assert "Speak directly or return JSON." in instructions
        assert "sales, billing, support, retention" in instructions
        assert "Be safe." in instructions
        assert "Respond in user's language." in instructions

    def test_history_truncation_handled_by_buffer(self, builder: RouterPromptBuilder) -> None:
        """Builder doesn't truncate — it trusts the ConversationBuffer's limits."""
        history = [
            {"role": "user", "content": f"turn {i}"}
            for i in range(20)
        ]
        payload = builder.build_response_create(history=history)
        assert len(payload["response"]["input"]) == 20


# ---------------------------------------------------------------------------
# parse_model_action tests
# ---------------------------------------------------------------------------


class TestParseModelAction:
    def test_valid_specialist_action(self) -> None:
        transcript = '{"action": "specialist", "department": "billing", "summary": "billing issue"}'
        result = parse_model_action(transcript)

        assert result is not None
        assert isinstance(result, ModelRouterAction)
        assert result.department == Department.BILLING
        assert result.summary == "billing issue"

    def test_valid_action_all_departments(self) -> None:
        for dept in Department:
            transcript = f'{{"action": "specialist", "department": "{dept.value}", "summary": "test"}}'
            result = parse_model_action(transcript)
            assert result is not None
            assert result.department == dept

    def test_direct_voice_non_json(self) -> None:
        result = parse_model_action("Buenos días, ¿en qué puedo ayudarle?")
        assert result is None

    def test_direct_voice_empty_string(self) -> None:
        result = parse_model_action("")
        assert result is None

    def test_direct_voice_whitespace(self) -> None:
        result = parse_model_action("   ")
        assert result is None

    def test_malformed_json(self) -> None:
        result = parse_model_action('{"action": "specialist", "department": ')
        assert result is None

    def test_wrong_schema_no_action(self) -> None:
        result = parse_model_action('{"type": "something_else", "data": 123}')
        assert result is None

    def test_wrong_action_value(self) -> None:
        result = parse_model_action('{"action": "not_specialist", "department": "billing"}')
        assert result is None

    def test_unknown_department(self) -> None:
        result = parse_model_action('{"action": "specialist", "department": "unknown_dept", "summary": "test"}')
        assert result is None

    def test_json_with_whitespace_padding(self) -> None:
        transcript = '  {"action": "specialist", "department": "sales", "summary": "wants upgrade"}  '
        result = parse_model_action(transcript)
        assert result is not None
        assert result.department == Department.SALES

    def test_not_dict_json(self) -> None:
        result = parse_model_action("[1, 2, 3]")
        assert result is None


# ---------------------------------------------------------------------------
# load_router_prompt tests
# ---------------------------------------------------------------------------


class TestLoadRouterPrompt:
    def test_load_valid_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "identity": "Test identity",
                "decision_rules": "Test rules",
                "departments": "Test departments",
                "guardrails": "Test guardrails",
                "language_instruction": "Test language",
            }
            path = Path(tmpdir) / "router_prompt.yaml"
            with open(path, "w") as f:
                yaml.dump(data, f)

            template = load_router_prompt(tmpdir)
            assert template.identity == "Test identity"
            assert template.decision_rules == "Test rules"

    def test_load_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError, match="router_prompt.yaml not found"):
                load_router_prompt(tmpdir)

    def test_load_missing_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "identity": "Test identity",
                # missing other sections
            }
            path = Path(tmpdir) / "router_prompt.yaml"
            with open(path, "w") as f:
                yaml.dump(data, f)

            with pytest.raises(ValueError, match="missing required section"):
                load_router_prompt(tmpdir)

    def test_load_actual_prompt_file(self) -> None:
        """Integration test: load the actual router_prompt.yaml from the repo."""
        registry_path = "router_registry/v1"
        if not Path(registry_path).exists():
            pytest.skip("router_registry not available in test CWD")

        template = load_router_prompt(registry_path)
        assert "call center" in template.identity.lower() or "assistant" in template.identity.lower()
        instruction = template.to_system_instruction()
        assert len(instruction) > 100
