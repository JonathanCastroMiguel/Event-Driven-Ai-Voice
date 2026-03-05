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
    def __init__(
        self,
        thresholds: ThresholdsConfig,
        route_a_examples: dict[str, dict[str, list[str]]],
        route_b_examples: dict[str, dict[str, list[str]]],
        lexicon_disallowed: dict[str, set[str]],
        short_utterances: dict[str, dict[str, list[str]]],
    ) -> None:
        self.thresholds = thresholds
        self.route_a_examples = route_a_examples
        self.route_b_examples = route_b_examples
        self.lexicon_disallowed = lexicon_disallowed
        self.short_utterances = short_utterances

    def get_route_a_examples(self, language: str) -> dict[str, list[str]]:
        if language in self.route_a_examples:
            return self.route_a_examples[language]
        return self.route_a_examples["base"]

    def get_route_b_examples(self, language: str) -> dict[str, list[str]]:
        if language in self.route_b_examples:
            return self.route_b_examples[language]
        return self.route_b_examples["base"]

    def get_lexicon(self, language: str) -> set[str]:
        return self.lexicon_disallowed.get(language, set())

    def get_short_utterances(self, language: str) -> dict[str, list[str]]:
        return self.short_utterances.get(language, {})


def load_registry(registry_path: str) -> RouterRegistry:
    root = Path(registry_path)

    thresholds = _load_thresholds(root / "thresholds.yaml")
    route_a = _load_examples(root / "route_a")
    route_b = _load_examples(root / "route_b")
    lexicon = _load_lexicons(root / "lexicon_disallowed")
    short_utts = _load_short_utterances(root / "short_utterances")

    return RouterRegistry(
        thresholds=thresholds,
        route_a_examples=route_a,
        route_b_examples=route_b,
        lexicon_disallowed=lexicon,
        short_utterances=short_utts,
    )


def _load_thresholds(path: Path) -> ThresholdsConfig:
    if not path.exists():
        msg = f"thresholds.yaml not found at {path}"
        raise FileNotFoundError(msg)
    with open(path) as f:
        data = yaml.safe_load(f)
    return ThresholdsConfig(data)


def _load_examples(directory: Path) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, list[str]]] = {}
    if not directory.exists():
        msg = f"Examples directory not found: {directory}"
        raise FileNotFoundError(msg)
    for yaml_file in sorted(directory.glob("*.yaml")):
        locale = yaml_file.stem  # "base", "es", "en"
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        result[locale] = {k: list(v) for k, v in data.items()}
    return result


def _load_lexicons(directory: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    if not directory.exists():
        return result
    for txt_file in sorted(directory.glob("*.txt")):
        lang = txt_file.stem
        with open(txt_file) as f:
            words = {line.strip().lower() for line in f if line.strip()}
        result[lang] = words
    return result


def _load_short_utterances(directory: Path) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, list[str]]] = {}
    if not directory.exists():
        return result
    for yaml_file in sorted(directory.glob("*.yaml")):
        lang = yaml_file.stem
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        result[lang] = {k: [s.lower() for s in v] for k, v in data.items()}
    return result
