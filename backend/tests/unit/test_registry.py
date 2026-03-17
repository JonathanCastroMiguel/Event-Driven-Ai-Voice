from pathlib import Path

import pytest
import yaml

from src.routing.policies import PoliciesRegistry, load_policies
from src.routing.registry import RouterRegistry, load_registry
from src.voice_runtime.types import PolicyKey


@pytest.fixture
def registry() -> RouterRegistry:
    return load_registry("router_registry/v1")


@pytest.fixture
def policies() -> PoliciesRegistry:
    return load_policies("router_registry/v1")


# ---------------------------------------------------------------------------
# Registry Loader
# ---------------------------------------------------------------------------


class TestRegistryLoader:
    def test_loads_thresholds(self, registry: RouterRegistry) -> None:
        assert registry.thresholds.version == "v1.0.0"
        assert registry.thresholds.ambiguous_margin == 0.05
        assert registry.thresholds.short_text_len_chars == 5

    def test_route_a_thresholds_all_labels(self, registry: RouterRegistry) -> None:
        for label in ["simple", "disallowed", "out_of_scope", "domain"]:
            assert label in registry.thresholds.route_a
            assert "high" in registry.thresholds.route_a[label]
            assert "medium" in registry.thresholds.route_a[label]

    def test_route_b_thresholds_all_labels(self, registry: RouterRegistry) -> None:
        for label in ["sales", "billing", "support", "retention"]:
            assert label in registry.thresholds.route_b

    def test_fallback_config(self, registry: RouterRegistry) -> None:
        assert registry.thresholds.fallback_enable is True
        assert registry.thresholds.fallback_min_score == 0.50
        assert registry.thresholds.fallback_max_latency_budget_ms == 2000

    def test_filler_config(self, registry: RouterRegistry) -> None:
        assert registry.thresholds.filler_enable is True
        assert registry.thresholds.filler_start_after_ms == 350
        assert registry.thresholds.filler_max_ms == 1200

    def test_missing_thresholds_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="thresholds.yaml"):
            load_registry(str(tmp_path))


# ---------------------------------------------------------------------------
# Policies Loader
# ---------------------------------------------------------------------------


class TestPoliciesLoader:
    def test_base_system_loaded(self, policies: PoliciesRegistry) -> None:
        assert "professional" in policies.base_system.lower()

    def test_all_policy_keys_have_instructions(self, policies: PoliciesRegistry) -> None:
        for key in PolicyKey:
            instr = policies.get_instructions(key)
            assert len(instr) > 0

    def test_build_prompt(self, policies: PoliciesRegistry) -> None:
        prompt = policies.build_prompt(PolicyKey.GREETING, "hola")
        assert "hola" in prompt
        assert policies.base_system in prompt

    def test_unknown_policy_key_raises(self, policies: PoliciesRegistry) -> None:
        # Create a fake enum-like value to test the error path
        class FakeKey:
            value = "nonexistent_key"

        with pytest.raises(KeyError, match="nonexistent_key"):
            policies.get_instructions(FakeKey())  # type: ignore[arg-type]

    def test_missing_policies_yaml_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="policies.yaml"):
            load_policies(str(tmp_path))

    def test_missing_policy_key_in_yaml_raises(self, tmp_path: Path) -> None:
        data = {
            "base_system": "test system",
            "policies": {
                "greeting": {"instructions": "greet"},
                # Missing other required keys
            },
        }
        (tmp_path / "policies.yaml").write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="missing entry for PolicyKey"):
            load_policies(str(tmp_path))

    def test_missing_base_system_raises(self, tmp_path: Path) -> None:
        data = {"policies": {}}
        (tmp_path / "policies.yaml").write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="base_system"):
            load_policies(str(tmp_path))
