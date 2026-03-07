"""Model-as-router: uses the Realtime voice model for intent classification.

The model receives a structured router prompt and either speaks directly
(simple intents) or returns a JSON action for specialist routing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()


class Department(str, Enum):
    SALES = "sales"
    BILLING = "billing"
    SUPPORT = "support"
    RETENTION = "retention"


@dataclass(frozen=True)
class ModelRouterAction:
    """Parsed JSON action from model response indicating specialist routing."""

    department: Department
    summary: str


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

        Args:
            history: Prior conversation turns as user/assistant message pairs
                     from ConversationBuffer.format_messages().

        Returns:
            A dict suitable for sending as a response.create event.
        """
        payload: dict[str, Any] = {
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"],
                "instructions": self._system_instruction,
            },
        }

        if history:
            input_messages: list[dict[str, Any]] = []
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                input_messages.append({
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text", "text": content}],
                })
            payload["response"]["input"] = input_messages

        return payload


def parse_model_action(transcript: str) -> ModelRouterAction | None:
    """Parse accumulated response transcript into a ModelRouterAction or None.

    Returns None if the transcript is a direct voice response (non-JSON).
    Returns None with a warning log if the JSON is malformed or doesn't match schema.
    """
    text = transcript.strip()
    if not text.startswith("{"):
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("model_router_malformed_json", transcript=text[:200])
        return None

    if not isinstance(data, dict):
        logger.warning("model_router_not_dict", transcript=text[:200])
        return None

    if data.get("action") != "specialist":
        logger.warning("model_router_wrong_action", action=data.get("action"))
        return None

    dept_str = data.get("department", "")
    try:
        department = Department(dept_str)
    except ValueError:
        logger.warning("model_router_unknown_department", department=dept_str)
        return None

    summary = str(data.get("summary", ""))
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
