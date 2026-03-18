"""Unit tests for model router: RouterPromptBuilder, parse_function_call_action, load_router_prompt."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.routing.model_router import (
    AgentConfig,
    ModelRouterAction,
    RouterPromptBuilder,
    RouterPromptConfig,
    ToolConfig,
    build_route_tool_definition,
    load_router_prompt,
    load_router_prompt_from_dict,
    parse_function_call_action,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONFIG_DICT: dict[str, Any] = {
    "identity": "You are a test assistant.",
    "agents": {
        "direct": {
            "description": "Handle directly",
            "triggers": ["Greetings", "Small talk"],
            "fillers": [],
            "tool": None,
        },
        "billing": {
            "description": "Billing specialist",
            "triggers": ["Invoices", "Charges"],
            "fillers": [
                "Let me connect you with billing.",
                "One moment, checking your account.",
            ],
            "tool": {"type": "internal", "name": "specialist_billing"},
        },
        "sales": {
            "description": "Sales specialist",
            "triggers": ["Upgrades", "Plans"],
            "fillers": ["Let me get a sales specialist."],
            "tool": {"type": "internal", "name": "specialist_sales"},
        },
    },
    "guardrails": ["Never provide medical advice", "Stay calm if user is aggressive"],
    "language_instruction": "Respond in the user's language.",
}


@pytest.fixture
def config() -> RouterPromptConfig:
    return load_router_prompt_from_dict(SAMPLE_CONFIG_DICT)


@pytest.fixture
def builder(config: RouterPromptConfig) -> RouterPromptBuilder:
    return RouterPromptBuilder(config)


# ---------------------------------------------------------------------------
# Config loading tests
# ---------------------------------------------------------------------------


class TestLoadRouterPromptFromDict:
    def test_load_valid_config(self) -> None:
        config = load_router_prompt_from_dict(SAMPLE_CONFIG_DICT)
        assert config.identity == "You are a test assistant."
        assert len(config.agents) == 3
        assert "direct" in config.agents
        assert "billing" in config.agents
        assert config.guardrails == ["Never provide medical advice", "Stay calm if user is aggressive"]
        assert config.language_instruction == "Respond in the user's language."

    def test_agent_config_with_tool(self) -> None:
        config = load_router_prompt_from_dict(SAMPLE_CONFIG_DICT)
        billing = config.agents["billing"]
        assert billing.description == "Billing specialist"
        assert billing.triggers == ["Invoices", "Charges"]
        assert len(billing.fillers) == 2
        assert billing.tool is not None
        assert isinstance(billing.tool, ToolConfig)
        assert billing.tool.type == "internal"
        assert billing.tool.name == "specialist_billing"

    def test_direct_agent_no_tool(self) -> None:
        config = load_router_prompt_from_dict(SAMPLE_CONFIG_DICT)
        direct = config.agents["direct"]
        assert direct.tool is None
        assert direct.fillers == []

    def test_valid_departments_set(self) -> None:
        config = load_router_prompt_from_dict(SAMPLE_CONFIG_DICT)
        assert config.valid_departments == {"direct", "billing", "sales"}

    def test_missing_required_field(self) -> None:
        for field in ["identity", "agents", "guardrails", "language_instruction"]:
            incomplete = {k: v for k, v in SAMPLE_CONFIG_DICT.items() if k != field}
            with pytest.raises(ValueError, match="missing required field"):
                load_router_prompt_from_dict(incomplete)

    def test_tool_with_url_and_auth(self) -> None:
        data = {
            **SAMPLE_CONFIG_DICT,
            "agents": {
                "support": {
                    "description": "Support",
                    "triggers": ["Issues"],
                    "fillers": [],
                    "tool": {"type": "mcp", "url": "https://mcp.example.com", "auth": "key_ref"},
                },
            },
        }
        config = load_router_prompt_from_dict(data)
        tool = config.agents["support"].tool
        assert tool is not None
        assert tool.type == "mcp"
        assert tool.url == "https://mcp.example.com"
        assert tool.auth == "key_ref"
        assert tool.name is None


class TestLoadRouterPrompt:
    def test_load_from_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "router_prompt.json"
            with open(path, "w") as f:
                json.dump(SAMPLE_CONFIG_DICT, f)

            config = load_router_prompt(tmpdir)
            assert config.identity == "You are a test assistant."
            assert len(config.agents) == 3

    def test_load_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError, match="router_prompt.json not found"):
                load_router_prompt(tmpdir)

    def test_load_actual_config_file(self) -> None:
        """Integration test: load the actual router_prompt.json from the repo."""
        registry_path = "router_registry/v1"
        if not Path(registry_path).exists():
            pytest.skip("router_registry not available in test CWD")

        config = load_router_prompt(registry_path)
        assert "assistant" in config.identity.lower() or "call center" in config.identity.lower()
        assert len(config.agents) >= 2


# ---------------------------------------------------------------------------
# Dynamic tool definition tests
# ---------------------------------------------------------------------------


class TestBuildRouteToolDefinition:
    def test_enum_matches_agent_keys(self, config: RouterPromptConfig) -> None:
        tool_def = build_route_tool_definition(config.agents)
        enum_values = tool_def["parameters"]["properties"]["department"]["enum"]
        assert set(enum_values) == {"direct", "billing", "sales"}

    def test_adding_agent_updates_enum(self) -> None:
        data = {**SAMPLE_CONFIG_DICT}
        data["agents"] = {
            **SAMPLE_CONFIG_DICT["agents"],
            "escalation": {
                "description": "Escalation",
                "triggers": ["Urgent"],
                "fillers": [],
                "tool": {"type": "internal", "name": "specialist_escalation"},
            },
        }
        config = load_router_prompt_from_dict(data)
        tool_def = build_route_tool_definition(config.agents)
        enum_values = tool_def["parameters"]["properties"]["department"]["enum"]
        assert "escalation" in enum_values

    def test_tool_definition_structure(self, config: RouterPromptConfig) -> None:
        tool_def = build_route_tool_definition(config.agents)
        assert tool_def["type"] == "function"
        assert tool_def["name"] == "route_to_specialist"
        assert "department" in tool_def["parameters"]["properties"]
        assert "summary" in tool_def["parameters"]["properties"]
        assert tool_def["parameters"]["required"] == ["department", "summary"]

    def test_description_contains_agent_triggers(self, config: RouterPromptConfig) -> None:
        tool_def = build_route_tool_definition(config.agents)
        description = tool_def["description"]
        assert "direct" in description
        assert "Greetings" in description
        assert "billing" in description
        assert "Invoices" in description
        assert "sales" in description
        assert "Upgrades" in description


# ---------------------------------------------------------------------------
# RouterPromptBuilder tests
# ---------------------------------------------------------------------------


class TestRouterPromptBuilder:
    def test_build_first_turn_empty_history(self, builder: RouterPromptBuilder) -> None:
        payload = builder.build_response_create(history=[])
        assert payload["type"] == "response.create"
        assert payload["response"]["modalities"] == ["text", "audio"]
        assert "You are a test assistant." in payload["response"]["instructions"]

    def test_build_with_history(self, builder: RouterPromptBuilder) -> None:
        history = [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "greeting response"},
        ]
        payload = builder.build_response_create(history=history)
        instructions = payload["response"]["instructions"]
        assert "Conversation history:" in instructions
        assert "User: hola" in instructions
        assert "Assistant: greeting response" in instructions

    def test_instructions_contain_all_sections(self, builder: RouterPromptBuilder) -> None:
        instructions = builder.system_instruction
        # System mechanic
        assert "ALWAYS" in instructions
        assert "route_to_specialist" in instructions
        # Identity
        assert "You are a test assistant." in instructions
        # Routing rules from agents
        assert "billing" in instructions
        assert "Invoices" in instructions
        # Guardrails
        assert "- Never provide medical advice" in instructions
        assert "- Stay calm if user is aggressive" in instructions
        # Language instruction
        assert "Respond in the user's language." in instructions

    def test_tool_definition_in_payload(self, builder: RouterPromptBuilder) -> None:
        payload = builder.build_response_create(history=[])
        tools = payload["response"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "route_to_specialist"
        enum_values = tools[0]["parameters"]["properties"]["department"]["enum"]
        assert set(enum_values) == {"direct", "billing", "sales"}

    def test_tool_choice_required(self, builder: RouterPromptBuilder) -> None:
        payload = builder.build_response_create(history=[])
        assert payload["response"]["tool_choice"] == "required"

    def test_get_department_tool_specialist(self, builder: RouterPromptBuilder) -> None:
        tool = builder.get_department_tool("billing")
        assert tool is not None
        assert isinstance(tool, ToolConfig)
        assert tool.type == "internal"
        assert tool.name == "specialist_billing"

    def test_get_department_tool_direct(self, builder: RouterPromptBuilder) -> None:
        tool = builder.get_department_tool("direct")
        assert tool is None

    def test_get_department_tool_unknown(self, builder: RouterPromptBuilder) -> None:
        tool = builder.get_department_tool("nonexistent")
        assert tool is None

    def test_get_department_filler_with_fillers(self, builder: RouterPromptBuilder) -> None:
        filler = builder.get_department_filler("billing")
        assert filler is not None
        assert filler in [
            "Let me connect you with billing.",
            "One moment, checking your account.",
        ]

    def test_get_department_filler_direct(self, builder: RouterPromptBuilder) -> None:
        filler = builder.get_department_filler("direct")
        assert filler is None

    def test_get_department_filler_unknown(self, builder: RouterPromptBuilder) -> None:
        filler = builder.get_department_filler("nonexistent")
        assert filler is None

    def test_tool_definition_property(self, builder: RouterPromptBuilder) -> None:
        assert builder.tool_definition["name"] == "route_to_specialist"

    def test_config_property(self, builder: RouterPromptBuilder) -> None:
        assert builder.config.identity == "You are a test assistant."


# ---------------------------------------------------------------------------
# parse_function_call_action tests
# ---------------------------------------------------------------------------

VALID_DEPARTMENTS = {"direct", "billing", "sales", "support", "retention"}


class TestParseFunctionCallAction:
    def test_valid_specialist_action(self) -> None:
        result = parse_function_call_action(
            "route_to_specialist",
            '{"department": "billing", "summary": "billing issue"}',
            VALID_DEPARTMENTS,
        )
        assert result is not None
        assert isinstance(result, ModelRouterAction)
        assert result.department == "billing"
        assert result.summary == "billing issue"

    def test_valid_action_all_departments(self) -> None:
        for dept in VALID_DEPARTMENTS:
            result = parse_function_call_action(
                "route_to_specialist",
                f'{{"department": "{dept}", "summary": "test"}}',
                VALID_DEPARTMENTS,
            )
            assert result is not None
            assert result.department == dept

    def test_wrong_function_name(self) -> None:
        result = parse_function_call_action(
            "wrong_function",
            '{"department": "billing", "summary": "test"}',
            VALID_DEPARTMENTS,
        )
        assert result is None

    def test_malformed_json(self) -> None:
        result = parse_function_call_action(
            "route_to_specialist",
            '{"department": ',
            VALID_DEPARTMENTS,
        )
        assert result is None

    def test_unknown_department(self) -> None:
        result = parse_function_call_action(
            "route_to_specialist",
            '{"department": "unknown_dept", "summary": "test"}',
            VALID_DEPARTMENTS,
        )
        assert result is None

    def test_direct_department(self) -> None:
        result = parse_function_call_action(
            "route_to_specialist",
            '{"department": "direct", "summary": "greeting"}',
            VALID_DEPARTMENTS,
        )
        assert result is not None
        assert result.department == "direct"
        assert result.summary == "greeting"
