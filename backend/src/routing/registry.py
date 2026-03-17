from __future__ import annotations

from pathlib import Path

import yaml

from src.voice_runtime.types import RouteALabel, RouteBLabel


class ThresholdsConfig:
    def __init__(self, data: dict[str, object]) -> None:
        self.version: str = str(data["version"])

        ra = data["route_a"]
        self.route_a: dict[str, dict[str, float]] = {
            label.value: {"high": float(ra[label.value]["high"]), "medium": float(ra[label.value]["medium"])}
            for label in RouteALabel
        }

        rb = data["route_b"]
        self.route_b: dict[str, dict[str, float]] = {
            label.value: {"high": float(rb[label.value]["high"]), "medium": float(rb[label.value]["medium"])}
            for label in RouteBLabel
        }

        self.ambiguous_margin: float = float(data["ambiguous_margin"])
        self.short_text_len_chars: int = int(data["short_text_len_chars"])

        fb = data["fallback"]
        self.fallback_enable: bool = bool(fb["enable"])
        self.fallback_min_score: float = float(fb["min_score"])
        self.fallback_max_latency_budget_ms: int = int(fb["max_latency_budget_ms"])

        filler = data["filler"]
        self.filler_enable: bool = bool(filler["enable"])
        self.filler_start_after_ms: int = int(filler["start_after_ms"])
        self.filler_max_ms: int = int(filler["max_ms"])


class RouterRegistry:
    def __init__(self, thresholds: ThresholdsConfig) -> None:
        self.thresholds = thresholds


def load_registry(registry_path: str) -> RouterRegistry:
    root = Path(registry_path)
    thresholds = _load_thresholds(root / "thresholds.yaml")
    return RouterRegistry(thresholds=thresholds)


def _load_thresholds(path: Path) -> ThresholdsConfig:
    if not path.exists():
        msg = f"thresholds.yaml not found at {path}"
        raise FileNotFoundError(msg)
    with open(path) as f:
        data = yaml.safe_load(f)
    return ThresholdsConfig(data)
