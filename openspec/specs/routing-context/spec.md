## MODIFIED Requirements

### Requirement: Conversation history formatter for router prompt
The `RoutingContextBuilder` SHALL be simplified to format conversation history from the `ConversationBuffer` as message pairs suitable for the `input` array of `response.create`. It SHALL NOT produce enriched text for embedding classification or LLM fallback context. The builder SHALL accept `max_history_turns` (from buffer limits) and format prior turns as user/assistant message pairs.

#### Scenario: Format history with 2 prior turns
- **WHEN** the conversation buffer contains 2 entries with user texts "hola" and "quiero ver mi factura"
- **THEN** the builder SHALL return a list of message dicts: `[{"role": "user", "content": "hola"}, {"role": "assistant", "content": "<response_summary>"}, {"role": "user", "content": "quiero ver mi factura"}, {"role": "assistant", "content": "<response_summary>"}]`

#### Scenario: Empty buffer returns empty list
- **WHEN** the conversation buffer is empty (first turn)
- **THEN** the builder SHALL return an empty list

#### Scenario: History respects buffer limits
- **WHEN** the buffer has been truncated to `max_turns` entries
- **THEN** the builder SHALL format only the entries present in the buffer (no additional truncation)

## REMOVED Requirements

### Requirement: Routing context builder produces enriched classification inputs
**Reason**: Embedding-based routing is replaced by model-as-router. The builder no longer needs to produce enriched text for embedding classification or structured LLM fallback context. The Realtime model classifies directly from audio.
**Migration**: Use the simplified `format_history` method for conversation context in the router prompt.

### Requirement: LLM context window independent from embedding context window
**Reason**: No separate embedding and LLM context windows needed. The model receives conversation history directly — no distinction between embedding enrichment and LLM fallback context.
**Migration**: Single `max_history_turns` parameter from ConversationBuffer governs history length.

### Requirement: LLM fallback context includes previous turn
**Reason**: LLM fallback is removed. The Realtime model is the only classifier.
**Migration**: Conversation history is included in the router prompt's `input` array directly.

### Requirement: Original user text preserved
**Reason**: Still true conceptually but the requirement is moot — there is no enriched text that could replace the original. The buffer stores original text as before.
**Migration**: No action needed.

### Requirement: Context window respects configuration
**Reason**: The separate `routing_context_window` and `llm_context_window` parameters are removed. History is governed by `ConversationBuffer.max_turns` only.
**Migration**: Use `max_history_turns` configuration for history length.
