## ADDED Requirements

### Requirement: Routing context builder produces enriched classification inputs
The `RoutingContextBuilder` SHALL read from the `ConversationBuffer` and produce two outputs: (a) enriched text for embedding classification and (b) a context string for LLM fallback. The builder SHALL be instantiated with `routing_short_text_chars` (default: 20) and `routing_context_window` (default: 1).

#### Scenario: Short follow-up text enriched with previous turn
- **WHEN** the current `user_text` has fewer than `routing_short_text_chars` characters AND the conversation buffer contains at least one entry
- **THEN** the builder SHALL return `enriched_text` as `"{prev_user_text}. {current_text}"` using the most recent buffer entry's `user_text`

#### Scenario: Long self-contained text not enriched
- **WHEN** the current `user_text` has `routing_short_text_chars` or more characters
- **THEN** the builder SHALL return `enriched_text` as `None` (no enrichment)

#### Scenario: Empty buffer produces no enrichment
- **WHEN** the conversation buffer is empty (first turn of the call)
- **THEN** the builder SHALL return `enriched_text` as `None` and `llm_context` as `None`

### Requirement: LLM fallback context includes previous turn
The `RoutingContextBuilder` SHALL always produce an `llm_context` string when the conversation buffer is non-empty, regardless of the short text threshold.

#### Scenario: LLM context produced for any non-first turn
- **WHEN** the conversation buffer contains at least one entry AND `user_text` is "de este mes"
- **THEN** the builder SHALL return `llm_context` as `"language={lang}; previous_turn: {prev_user_text}"` where `prev_user_text` is the most recent entry's `user_text`

#### Scenario: LLM context is None on first turn
- **WHEN** the conversation buffer is empty
- **THEN** the builder SHALL return `llm_context` as `None`

### Requirement: Original user text preserved
The `RoutingContextBuilder` SHALL NOT modify the original `user_text`. The enriched outputs are for classification only — prompt construction and buffer storage SHALL continue using the original text.

#### Scenario: Enriched text does not replace original
- **WHEN** the builder produces `enriched_text = "mi factura. de este mes"`
- **THEN** the original `user_text` "de este mes" SHALL be used for prompt construction, buffer append, and logging

### Requirement: Context window respects configuration
The `RoutingContextBuilder` SHALL use only the most recent N entries from the buffer, where N equals `routing_context_window`.

#### Scenario: Context window of 1
- **WHEN** `routing_context_window` is 1 AND the buffer contains entries for turns 1, 2, 3
- **THEN** the builder SHALL use only the entry from turn 3 (most recent) for enrichment
