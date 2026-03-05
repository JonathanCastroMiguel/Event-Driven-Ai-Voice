## ADDED Requirements

### Requirement: Agent FSM states and transitions
The Agent FSM SHALL implement the following states: `idle`, `thinking`, `waiting_tools`, `waiting_voice`, `done`, `cancelled`, `error`. Transitions SHALL be defined as a dict mapping and enforced — invalid transitions SHALL raise an error.

#### Scenario: Valid state transition
- **WHEN** Agent FSM is in `idle` state and receives `handle_turn`
- **THEN** it SHALL transition to `thinking` and emit `agent_state_changed(state="thinking")`

#### Scenario: Invalid state transition rejected
- **WHEN** Agent FSM is in `done` state and receives `handle_turn`
- **THEN** it SHALL raise an error and log the invalid transition attempt

#### Scenario: Cancellation from any active state
- **WHEN** Agent FSM receives `cancel_agent_generation` while in `thinking` or `waiting_tools`
- **THEN** it SHALL transition to `cancelled` and stop all processing for that generation

### Requirement: Route A classification (intent level 1)
The Agent FSM SHALL classify user text into one of four Route A labels: `simple`, `disallowed`, `out_of_scope`, `domain`. Classification uses embedding cosine similarity against pre-computed centroids.

#### Scenario: High-confidence simple intent
- **WHEN** user says "hola" and embedding similarity to `simple` centroid >= 0.85
- **THEN** Agent FSM SHALL emit `request_guided_response(policy_key="greeting")`

#### Scenario: Disallowed intent via lexicon match
- **WHEN** user text contains a word from the disallowed lexicon (e.g., "idiota")
- **THEN** Agent FSM SHALL classify as `disallowed` without running embeddings and emit `request_guided_response(policy_key="guardrail_disallowed")`

#### Scenario: Out-of-scope intent
- **WHEN** user asks "who will win the election" and embedding similarity to `out_of_scope` >= 0.82
- **THEN** Agent FSM SHALL emit `request_guided_response(policy_key="guardrail_out_of_scope")`

#### Scenario: Domain intent passes to Route B
- **WHEN** user says "tengo un problema con mi factura" and embedding similarity to `domain` >= 0.78
- **THEN** Agent FSM SHALL proceed to Route B classification

### Requirement: Route B classification (specialist routing)
For `domain` intents, the Agent FSM SHALL classify into specialist departments: `sales`, `billing`, `support`, `retention`. Classification uses embedding similarity against Route B centroids.

#### Scenario: High-confidence billing route
- **WHEN** Route B embedding similarity to `billing` >= 0.82
- **THEN** Agent FSM SHALL emit `request_agent_action(specialist="billing")`

#### Scenario: Ambiguous Route B (low margin)
- **WHEN** top-1 Route B score minus top-2 score < 0.05
- **THEN** Agent FSM SHALL emit `request_guided_response(policy_key="clarify_department")`

### Requirement: Short utterance handling
For utterances with normalized length <= 5 characters, the Agent FSM SHALL first check the short utterance registry. If matched, classify as `simple` regardless of embedding score.

#### Scenario: Short greeting matched
- **WHEN** user says "hola" (4 chars) and it matches `short_utterances/es.yaml` greetings list
- **THEN** Agent FSM SHALL classify as `simple` without running embeddings

#### Scenario: Short non-matching utterance
- **WHEN** user says "cobro" (5 chars) but it is not in short utterances
- **THEN** Agent FSM SHALL proceed with normal embedding classification

### Requirement: 3rd-party LLM fallback for ambiguous classification
When Route A or Route B confidence is below the high threshold AND the margin between top-2 classes < 0.05, the Agent FSM SHALL invoke a 3rd-party LLM via async HTTP for classification (temperature 0, structured JSON output). When `llm_context` is provided (non-None), the LLM fallback prompt SHALL include the conversation context string, enabling the LLM to reason about follow-up intent.

#### Scenario: LLM fallback invoked
- **WHEN** Route A embedding scores are `domain=0.72, simple=0.70` (both below threshold, margin=0.02)
- **THEN** Agent FSM SHALL call the 3rd-party LLM for classification and use the LLM result

#### Scenario: LLM fallback with conversation context
- **WHEN** Route A is ambiguous AND `llm_context` is `"language=es; previous_turn: tengo un problema con mi factura"`
- **THEN** the LLM fallback prompt SHALL include the conversation context so the LLM can reason that a short follow-up relates to the billing domain

#### Scenario: LLM fallback without conversation context
- **WHEN** Route A is ambiguous AND `llm_context` is `None` (first turn)
- **THEN** the LLM fallback prompt SHALL use only `language={lang}` as context, matching current behavior

#### Scenario: LLM fallback timeout
- **WHEN** 3rd-party LLM call exceeds 2s timeout
- **THEN** Agent FSM SHALL use the best embedding result as-is and log the timeout

#### Scenario: LLM fallback disabled
- **WHEN** `thresholds.yaml` has `fallback.enable_microllm: false`
- **THEN** Agent FSM SHALL always use embedding results, never calling the LLM

### Requirement: Language detection
The Agent FSM SHALL detect the language of user text using fasttext before classification. Detected language SHALL determine which locale-specific examples (centroids) to use.

#### Scenario: Spanish detected
- **WHEN** user text is "quiero darme de baja" and fasttext detects `es`
- **THEN** routing SHALL use `es.yaml` centroids (with `base.yaml` fallback)

#### Scenario: Unsupported language
- **WHEN** fasttext detects a language not in `thresholds.yaml` `language.supported`
- **THEN** routing SHALL fall back to the default language centroids

### Requirement: Classification pipeline order
The Agent FSM SHALL classify in this exact order: (1) detect language, (2) check disallowed lexicon, (3) check short utterances, (4) embedding Route A, (5) if domain: embedding Route B, (6) if ambiguous: LLM fallback.

#### Scenario: Lexicon match short-circuits pipeline
- **WHEN** user text matches a disallowed lexicon entry
- **THEN** classification SHALL stop at step 2 — no embeddings or LLM called

#### Scenario: Full pipeline for ambiguous domain intent
- **WHEN** user text is complex and Route B is ambiguous
- **THEN** all 6 steps SHALL execute in order, with LLM fallback as the final classification step

### Requirement: Agent FSM does not execute tools or speak
The Agent FSM SHALL NOT directly execute tools, call the Realtime API, or generate final response text. It SHALL only emit intent/routing events to the Coordinator.

#### Scenario: Agent emits routing event only
- **WHEN** Agent FSM classifies an intent as `billing`
- **THEN** it SHALL emit `request_agent_action(specialist="billing")` and NOT call any tool or Realtime API
