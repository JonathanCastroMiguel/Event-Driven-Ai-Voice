## MODIFIED Requirements

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
