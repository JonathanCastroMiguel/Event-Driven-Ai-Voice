"""Model-as-router: uses the Realtime voice model for intent classification.

The model receives a structured router prompt and always speaks naturally.
For specialist routing, the model calls a `route_to_specialist` function
(never vocalized) while simultaneously speaking a filler message.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class ToolConfig:
    """Specialist endpoint configuration loaded from router config."""

    type: str  # internal | mcp | rag | langgraph | rest
    name: str | None = None
    url: str | None = None
    auth: str | None = None


@dataclass(frozen=True)
class AgentConfig:
    """Agent configuration loaded from router config."""

    description: str
    triggers: list[str] = field(default_factory=list)
    fillers: list[str] = field(default_factory=list)
    tool: ToolConfig | None = None


@dataclass(frozen=True)
class RouterPromptConfig:
    """Structured router configuration loaded from JSON config."""

    identity: str
    agents: dict[str, AgentConfig]
    guardrails: list[str]
    language_instruction: str

    @property
    def valid_departments(self) -> set[str]:
        """Set of valid agent names (used as department values by the model)."""
        return set(self.agents.keys())


@dataclass(frozen=True)
class ModelRouterAction:
    """Parsed routing action from function call indicating specialist routing."""

    department: str
    summary: str


SYSTEM_MECHANIC: str = (
    "ALWAYS respond by speaking naturally AND calling route_to_specialist.\n"
    "You must ALWAYS call this function for every message — no exceptions.\n\n"
    "The function call is silent and invisible to the customer. Never say function "
    "names or syntax out loud — only speak natural language.\n\n"
    "When routing to a specialist, speak a brief filler in the customer's language "
    '(e.g., "Un momento, le conecto con facturación").'
)


def build_route_tool_definition(
    agents: dict[str, AgentConfig],
) -> dict[str, Any]:
    """Generate the route_to_specialist tool definition dynamically from config.

    The description is built from agent triggers so the model knows
    when to use each agent. No hardcoded routing logic.
    """
    agent_descriptions: list[str] = []
    for agent_name, agent_config in agents.items():
        triggers_text = "; ".join(agent_config.triggers)
        agent_descriptions.append(
            f"'{agent_name}': {agent_config.description} — {triggers_text}"
        )
    description = (
        "Classify every user message into one of these agents:\n"
        + "\n".join(agent_descriptions)
    )

    return {
        "type": "function",
        "name": "route_to_specialist",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "department": {
                    "type": "string",
                    "enum": list(agents.keys()),
                    "description": "The agent to route this message to.",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief English summary of what the customer needs.",
                },
            },
            "required": ["department", "summary"],
        },
    }


class RouterPromptBuilder:
    """Builds response.create payloads from structured router config + conversation history."""

    def __init__(self, config: RouterPromptConfig) -> None:
        self._config = config
        self._tool_definition = build_route_tool_definition(config.agents)
        self._system_instruction = self._assemble_system_instruction()

    def _assemble_system_instruction(self) -> str:
        """Assemble system prompt from structured config sections."""
        sections: list[str] = [SYSTEM_MECHANIC]

        # Identity
        sections.append(self._config.identity)

        # Routing rules generated from agents
        routing_lines: list[str] = ["Routing rules:"]
        for agent_name, agent_config in self._config.agents.items():
            triggers_text = ", ".join(agent_config.triggers)
            routing_lines.append(
                f"- {agent_name}: {agent_config.description}. "
                f"Triggers: {triggers_text}"
            )
        sections.append("\n".join(routing_lines))

        # Guardrails as bulleted list
        guardrails_text = "\n".join(
            f"- {g}" for g in self._config.guardrails
        )
        sections.append(guardrails_text)

        # Language instruction
        sections.append(self._config.language_instruction)

        return "\n\n".join(sections)

    @property
    def system_instruction(self) -> str:
        return self._system_instruction

    @property
    def tool_definition(self) -> dict[str, Any]:
        """The dynamically generated route_to_specialist tool definition."""
        return self._tool_definition

    @property
    def config(self) -> RouterPromptConfig:
        """The underlying router prompt configuration."""
        return self._config

    def get_department_tool(self, department: str) -> ToolConfig | None:
        """Resolve the specialist tool config for an agent.

        Returns the ToolConfig for specialist agents, None for direct or unknown.
        """
        agent_config = self._config.agents.get(department)
        if agent_config is None:
            return None
        return agent_config.tool

    def get_department_filler(self, department: str) -> str | None:
        """Get a random filler message for an agent.

        Returns None if the agent has no fillers or is unknown.
        """
        agent_config = self._config.agents.get(department)
        if agent_config is None or not agent_config.fillers:
            return None
        return random.choice(agent_config.fillers)

    def build_response_create(
        self,
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Build a response.create payload for the OpenAI Realtime API.

        Includes the route_to_specialist tool so the model can signal routing
        via function call (never vocalized) while speaking a filler message.
        """
        instructions = self._system_instruction

        if history:
            history_lines: list[str] = []
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                label = "User" if role == "user" else "Assistant"
                history_lines.append(f"{label}: {content}")
            history_text = "\n".join(history_lines)
            instructions = f"{instructions}\n\nConversation history:\n{history_text}"

        return {
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"],
                "instructions": instructions,
                "tools": [self._tool_definition],
                "tool_choice": "required",
                "temperature": 0.8,
            },
        }


def parse_function_call_action(
    name: str,
    arguments: str,
    valid_departments: set[str],
) -> ModelRouterAction | None:
    """Parse a function call from the Realtime API into a routing action.

    Returns None if the function name doesn't match or arguments are invalid.
    """
    if name != "route_to_specialist":
        logger.warning("unexpected_function_call", name=name)
        return None

    import orjson

    try:
        args = orjson.loads(arguments)
    except Exception:
        logger.warning("function_call_invalid_json", arguments=arguments[:200])
        return None

    dept_str = str(args.get("department", "")).lower()
    summary = str(args.get("summary", "")).strip()

    if dept_str not in valid_departments:
        logger.warning("function_call_unknown_department", department=dept_str)
        return None

    return ModelRouterAction(department=dept_str, summary=summary)


def load_router_prompt_from_dict(data: dict[str, Any]) -> RouterPromptConfig:
    """Parse a router config dict into RouterPromptConfig.

    Accepts the exact target API payload structure (with 'agents' key).
    Raises ValueError if required fields are missing.
    """
    required_fields = ["identity", "agents", "guardrails", "language_instruction"]
    for field_name in required_fields:
        if field_name not in data or not data[field_name]:
            msg = f"Router config missing required field: {field_name}"
            raise ValueError(msg)

    agents: dict[str, AgentConfig] = {}
    for agent_name, agent_data in data["agents"].items():
        tool_data = agent_data.get("tool")
        tool: ToolConfig | None = None
        if tool_data is not None:
            tool = ToolConfig(
                type=tool_data["type"],
                name=tool_data.get("name"),
                url=tool_data.get("url"),
                auth=tool_data.get("auth"),
            )
        agents[agent_name] = AgentConfig(
            description=agent_data["description"],
            triggers=agent_data.get("triggers", []),
            fillers=agent_data.get("fillers", []),
            tool=tool,
        )

    return RouterPromptConfig(
        identity=str(data["identity"]),
        agents=agents,
        guardrails=list(data["guardrails"]),
        language_instruction=str(data["language_instruction"]),
    )


def load_router_prompt(registry_path: str) -> RouterPromptConfig:
    """Load and validate the router config from JSON.

    Reads the JSON file and delegates to load_router_prompt_from_dict.
    Raises FileNotFoundError if the file is missing.
    Raises ValueError if required fields are absent.
    """
    path = Path(registry_path) / "router_prompt.json"
    if not path.exists():
        msg = f"router_prompt.json not found at {path}"
        raise FileNotFoundError(msg)

    with open(path) as f:
        data = json.load(f)

    return load_router_prompt_from_dict(data)
