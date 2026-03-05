from __future__ import annotations

from pathlib import Path

import yaml

from src.voice_runtime.types import PolicyKey


class PoliciesRegistry:
    def __init__(self, base_system: str, policies: dict[str, str]) -> None:
        self.base_system = base_system
        self._policies = policies

    def get_instructions(self, policy_key: PolicyKey) -> str:
        if policy_key.value not in self._policies:
            msg = f"Unknown policy key: {policy_key.value}"
            raise KeyError(msg)
        return self._policies[policy_key.value]

    def build_prompt(self, policy_key: PolicyKey, user_text: str) -> str:
        instructions = self.get_instructions(policy_key)
        return f"{self.base_system}\n\n{instructions}\n\nUser said: {user_text}"


def load_policies(registry_path: str) -> PoliciesRegistry:
    path = Path(registry_path) / "policies.yaml"
    if not path.exists():
        msg = f"policies.yaml not found at {path}"
        raise FileNotFoundError(msg)

    with open(path) as f:
        data = yaml.safe_load(f)

    base_system = data.get("base_system")
    if not base_system:
        msg = "policies.yaml must contain 'base_system' field"
        raise ValueError(msg)

    raw_policies = data.get("policies", {})

    # Validate all PolicyKey enum values have entries
    for key in PolicyKey:
        if key.value not in raw_policies:
            msg = f"policies.yaml missing entry for PolicyKey '{key.value}'"
            raise ValueError(msg)

    policies = {k: v["instructions"] for k, v in raw_policies.items()}

    return PoliciesRegistry(base_system=base_system.strip(), policies=policies)
