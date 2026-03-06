## MODIFIED Requirements

### Requirement: Router calibration logging
Every routing decision SHALL be logged as a single `routing_completed` structured log entry at the end of `Router.classify()`. The log SHALL include: `router_version` (from ThresholdsConfig), `language`, `route_a_label`, `route_a_score` (float), `route_a_margin` (top1 - top2, float), `route_b_label` (str or None), `route_b_score` (float or None), `route_b_margin` (float or None), `short_circuit` (str or None: "lexicon" / "short_utterance"), `fallback_used` (bool). The log SHALL be emitted for every code path including lexicon short-circuit, short utterance match, embedding classification, LLM fallback, and ambiguous Route B.

#### Scenario: Routing decision logged for domain with Route B
- **WHEN** Router classifies user text as `domain` with Route B `billing` (score 0.88, margin 0.15) without fallback
- **THEN** a structured log entry `routing_completed` SHALL include `router_version="v1.0.0"`, `route_a_label="domain"`, `route_a_score=0.82`, `route_a_margin=0.10`, `route_b_label="billing"`, `route_b_score=0.88`, `route_b_margin=0.15`, `short_circuit=None`, `fallback_used=false`

#### Scenario: Routing decision logged for lexicon short-circuit
- **WHEN** Router classifies user text via lexicon match as `disallowed`
- **THEN** a structured log entry `routing_completed` SHALL include `route_a_label="disallowed"`, `route_a_score=1.0`, `route_a_margin=0.0`, `route_b_label=None`, `route_b_score=None`, `route_b_margin=None`, `short_circuit="lexicon"`, `fallback_used=false`

#### Scenario: Routing decision logged for short utterance
- **WHEN** Router classifies user text via short utterance match as `simple`
- **THEN** a structured log entry `routing_completed` SHALL include `route_a_label="simple"`, `route_a_score=1.0`, `route_a_margin=0.0`, `short_circuit="short_utterance"`, `fallback_used=false`

#### Scenario: Routing decision logged with LLM fallback
- **WHEN** Router classifies user text using LLM fallback for ambiguous Route A
- **THEN** a structured log entry `routing_completed` SHALL include `fallback_used=true` and the LLM-determined `route_a_label`

#### Scenario: Routing decision logged for ambiguous Route B (no LLM)
- **WHEN** Router classifies Route B as ambiguous and LLM fallback is disabled or times out
- **THEN** a structured log entry `routing_completed` SHALL include `route_b_label=None`, `fallback_used=false`

#### Scenario: Router version included in every log
- **WHEN** any routing decision is logged
- **THEN** the `router_version` field SHALL match the `version` field from `thresholds.yaml`
