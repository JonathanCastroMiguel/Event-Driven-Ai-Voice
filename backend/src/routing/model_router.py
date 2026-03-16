"""Model-as-router: uses the Realtime voice model for intent classification.

The model receives a structured router prompt and always speaks naturally.
For specialist routing, the model calls a `route_to_specialist` function
(never vocalized) while simultaneously speaking a filler message.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()


class Department(str, Enum):
    DIRECT = "direct"
    SALES = "sales"
    BILLING = "billing"
    SUPPORT = "support"
    RETENTION = "retention"


@dataclass(frozen=True)
class ModelRouterAction:
    """Parsed routing action from function call indicating specialist routing."""

    department: Department
    summary: str


# Tool definition for the route_to_specialist function.
# Included in response.create so the model can signal routing
# without contaminating the audio stream.
ROUTE_TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "name": "route_to_specialist",
    "description": (
        "Classify every user message. "
        "Use 'direct' when you can answer directly (greetings, small talk, "
        "general questions, clarifications). "
        "Use a specialist department when the customer needs system access "
        "(account lookup, billing changes, technical troubleshooting, etc.)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "department": {
                "type": "string",
                "enum": ["direct", "sales", "billing", "support", "retention"],
                "description": (
                    "'direct' for messages you handle yourself. "
                    "A specialist department for requests requiring system access."
                ),
            },
            "summary": {
                "type": "string",
                "description": "Brief English summary of what the customer needs.",
            },
        },
        "required": ["department", "summary"],
    },
}


@dataclass(frozen=True)
class RouterPromptTemplate:
    """Loaded router prompt sections from router_prompt.yaml."""

    identity: str
    decision_rules: str
    departments: str
    guardrails: str
    language_instruction: str

    def to_system_instruction(self) -> str:
        """Combine all sections into a single system instruction string."""
        return "\n\n".join([
            self.identity.strip(),
            self.decision_rules.strip(),
            self.departments.strip(),
            self.guardrails.strip(),
            self.language_instruction.strip(),
        ])


class RouterPromptBuilder:
    """Builds response.create payloads from the router prompt template + conversation history."""

    def __init__(self, template: RouterPromptTemplate) -> None:
        self._template = template
        self._system_instruction = template.to_system_instruction()

    @property
    def system_instruction(self) -> str:
        return self._system_instruction

    def build_response_create(
        self,
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Build a response.create payload for the OpenAI Realtime API.

        Includes the route_to_specialist tool so the model can signal routing
        via function call (never vocalized) while speaking a filler message.

        Args:
            history: Prior conversation turns as user/assistant message pairs
                     from ConversationBuffer.format_messages().

        Returns:
            A dict suitable for sending as a response.create event.
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
                "tools": [ROUTE_TOOL_DEFINITION],
                "tool_choice": "required",
                "temperature": 0.8,
            },
        }


def parse_function_call_action(
    name: str,
    arguments: str,
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

    try:
        department = Department(dept_str)
    except ValueError:
        logger.warning("function_call_unknown_department", department=dept_str)
        return None

    return ModelRouterAction(department=department, summary=summary)


def load_router_prompt(registry_path: str) -> RouterPromptTemplate:
    """Load and validate the router prompt template from YAML.

    Raises FileNotFoundError if the file is missing.
    Raises ValueError if required sections are absent.
    """
    path = Path(registry_path) / "router_prompt.yaml"
    if not path.exists():
        msg = f"router_prompt.yaml not found at {path}"
        raise FileNotFoundError(msg)

    with open(path) as f:
        data = yaml.safe_load(f)

    required_sections = ["identity", "decision_rules", "departments", "guardrails", "language_instruction"]
    for section in required_sections:
        if not data.get(section):
            msg = f"router_prompt.yaml missing required section: {section}"
            raise ValueError(msg)

    return RouterPromptTemplate(
        identity=str(data["identity"]),
        decision_rules=str(data["decision_rules"]),
        departments=str(data["departments"]),
        guardrails=str(data["guardrails"]),
        language_instruction=str(data["language_instruction"]),
    )
