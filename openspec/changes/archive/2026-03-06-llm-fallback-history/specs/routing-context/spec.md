## ADDED Requirements

### Requirement: LLM context window independent from embedding context window
The `RoutingContextBuilder` SHALL accept a separate `llm_context_window` parameter (default: 3) controlling how many prior turns are included in the `llm_context` output. This is independent of `routing_context_window` which controls embedding enrichment only.

#### Scenario: Builder instantiated with both window sizes
- **WHEN** the builder is created with `context_window=1` and `llm_context_window=3`
- **THEN** it SHALL use 1 entry for embedding enrichment and up to 3 entries for LLM context

#### Scenario: LLM context window defaults to 3
- **WHEN** `llm_context_window` is not explicitly provided
- **THEN** the builder SHALL default to `llm_context_window=3`

## MODIFIED Requirements

### Requirement: LLM fallback context includes previous turn
The `RoutingContextBuilder` SHALL always produce an `llm_context` string when the conversation buffer is non-empty, regardless of the short text threshold. The `llm_context` SHALL include up to `llm_context_window` prior turns in a structured multi-turn format with labeled turn entries.

#### Scenario: LLM context with 3 prior turns
- **WHEN** the conversation buffer contains 3+ entries with `user_text` values `["mi factura", "no me llega", "y ahora tampoco"]` and routes `["billing", "billing", "billing"]` AND `llm_context_window` is 3 AND current `user_text` is "de este mes" AND `language` is "es"
- **THEN** the builder SHALL return `llm_context` as:
```
language=es
turn[-3] user: mi factura
turn[-3] route: billing
turn[-2] user: no me llega
turn[-2] route: billing
turn[-1] user: y ahora tampoco
turn[-1] route: billing
```

#### Scenario: LLM context with fewer turns than window
- **WHEN** the conversation buffer contains 1 entry with `user_text="mi factura"` and `route_a_label="domain"` AND `llm_context_window` is 3
- **THEN** the builder SHALL return `llm_context` with only 1 turn block (no padding):
```
language=es
turn[-1] user: mi factura
turn[-1] route: domain
```

#### Scenario: LLM context is None on first turn
- **WHEN** the conversation buffer is empty
- **THEN** the builder SHALL return `llm_context` as `None`

#### Scenario: LLM context with window of 1 matches legacy format
- **WHEN** `llm_context_window` is 1 AND the buffer contains entries
- **THEN** the builder SHALL return a single-turn `llm_context` with the same information as the multi-turn format (1 turn block)

### Requirement: Context window respects configuration
The `RoutingContextBuilder` SHALL use only the most recent N entries from the buffer for embedding enrichment, where N equals `routing_context_window`. For LLM context, it SHALL use the most recent M entries, where M equals `llm_context_window`.

#### Scenario: Context window of 1 for embeddings, 3 for LLM
- **WHEN** `routing_context_window` is 1 AND `llm_context_window` is 3 AND the buffer contains entries for turns 1, 2, 3, 4, 5
- **THEN** the builder SHALL use only entry 5 (most recent) for embedding enrichment AND entries 3, 4, 5 for LLM context
