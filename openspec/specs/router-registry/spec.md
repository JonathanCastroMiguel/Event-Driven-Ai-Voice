## ADDED Requirements

### Requirement: Versioned registry structure
The router registry SHALL be stored under `router_registry/v1/` with semantic versioning. Each deployment SHALL reference an explicit `router_version` (e.g., "v1.0.0"). The structure SHALL include: `thresholds.yaml`, `route_a/` (base.yaml + locale overrides), `route_b/` (base.yaml + locale overrides), `policies.yaml`, `lexicon_disallowed/` (per-language .txt files), `short_utterances/` (per-language .yaml files).

#### Scenario: Registry loaded at startup
- **WHEN** the runtime starts
- **THEN** it SHALL load the registry from the configured version path, compute centroids from text examples, and report the loaded `router_version` in logs

#### Scenario: Version bump for threshold change
- **WHEN** thresholds are recalibrated
- **THEN** a new minor version SHALL be created (e.g., v1.0.1) and deployed

### Requirement: Thresholds configuration
`thresholds.yaml` SHALL define per-class high thresholds and medium bands for Route A (`simple`, `disallowed`, `out_of_scope`, `domain`) and Route B (per-specialist). It SHALL also define `ambiguous_margin` (default 0.05), `short_text_len_chars` (default 5), and fallback settings (enable, min_score, max_latency_budget_ms).

#### Scenario: Threshold values loaded
- **WHEN** the router initializes
- **THEN** it SHALL parse `thresholds.yaml` and validate all required fields are present with numeric values

#### Scenario: Missing threshold field
- **WHEN** `thresholds.yaml` is missing a required field
- **THEN** the router SHALL fail to start with a descriptive error

### Requirement: Language inheritance for centroids
Route A and Route B examples SHALL support language inheritance: if a locale-specific file (e.g., `es.yaml`) exists, use it; otherwise fall back to `base.yaml`. Locale overrides replace (not merge with) the base examples for that class.

#### Scenario: Spanish locale used
- **WHEN** detected language is `es` and `route_a/es.yaml` exists
- **THEN** the router SHALL use `es.yaml` examples for classification

#### Scenario: Fallback to base
- **WHEN** detected language is `fr` and `route_a/fr.yaml` does not exist
- **THEN** the router SHALL use `base.yaml` examples

### Requirement: Centroid computation at build/startup time
Centroids SHALL be computed as the mean of embeddings of all text examples per class. Computation SHALL happen at startup (or build time). Runtime classification SHALL only use pre-computed centroids, never raw text examples.

#### Scenario: Centroids computed on startup
- **WHEN** the router loads `route_a/es.yaml` with 10 examples for `simple`
- **THEN** it SHALL embed all 10 examples and compute the centroid as their mean vector

### Requirement: Lexicon disallowed rules
Per-language `.txt` files under `lexicon_disallowed/` SHALL contain one disallowed word/phrase per line. Lexicon matching SHALL be case-insensitive and applied BEFORE embedding classification.

#### Scenario: Lexicon match found
- **WHEN** user text contains "idiota" and `lexicon_disallowed/es.txt` contains "idiota"
- **THEN** the router SHALL return `disallowed` immediately without running embeddings

#### Scenario: No lexicon match
- **WHEN** user text does not match any lexicon entry
- **THEN** the router SHALL proceed to short utterance check and embedding classification

### Requirement: Short utterance registry
Per-language `.yaml` files under `short_utterances/` SHALL contain categorized short phrases (greetings, acknowledgements). Matching SHALL be exact (case-insensitive) and applied AFTER lexicon but BEFORE embeddings.

#### Scenario: Short greeting matched
- **WHEN** user says "buenas" and `short_utterances/es.yaml` lists "buenas" under greetings
- **THEN** the router SHALL return `simple` immediately

### Requirement: Policies registry
`policies.yaml` SHALL define: a `base_system` instruction (constant across all policies) and a `policies` map where each key is a `PolicyKey` enum value with an `instructions` text block.

#### Scenario: Policy instructions retrieved
- **WHEN** Coordinator requests instructions for `policy_key="guardrail_out_of_scope"`
- **THEN** the registry SHALL return the corresponding `instructions` text block

#### Scenario: Unknown policy key
- **WHEN** a policy key not present in `policies.yaml` is requested
- **THEN** the registry SHALL raise an error (policy keys are a closed enum)

### Requirement: Filler configuration
`thresholds.yaml` SHALL include filler settings: `enable` (bool), `start_after_ms` (default 350), `max_ms` (default 1200).

#### Scenario: Filler disabled
- **WHEN** `filler.enable` is `false`
- **THEN** the Coordinator SHALL never emit filler voice starts, even if tool latency exceeds `start_after_ms`
