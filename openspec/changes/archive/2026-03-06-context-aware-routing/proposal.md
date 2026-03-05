## Why

The router currently classifies each turn's text in isolation — it receives only the current `user_text` and `language`, with no knowledge of prior turns. This causes misclassification when users produce short follow-up phrases that complement the previous turn (e.g., "de este mes" after "tengo un problema con mi factura"). While the LLM voice agent receives conversation history via the `ConversationBuffer`, the routing decision that selects the policy/specialist happens before history is consulted, leading to wrong policy instructions on the prompt.

## What Changes

Two-layer context enrichment for short/ambiguous follow-up turns:

- **Layer 1 — Embedding enrichment**: When the current turn's text is short (below a configurable `routing_short_text_chars` threshold, default: 20), prepend the previous turn's `user_text` to create a concatenated string for embedding classification. This gives the cosine similarity a richer signal without changing centroids or the pipeline. Long, self-contained utterances are classified as-is.
- **Layer 2 — LLM fallback context**: When the LLM fallback is invoked (ambiguous embedding scores), include the previous turn's `user_text` as additional context in the LLM prompt. The LLM can reason about conversational continuity natively, unlike embeddings.
- A new **context builder** module handles both layers: it reads from the `ConversationBuffer` and produces (a) enriched text for embeddings and (b) context string for LLM fallback.
- The original `user_text` is preserved for prompt construction and buffer storage — only the classification inputs are enriched.
- Configurable **context window** (number of prior turns, default: 1) and **short text threshold** (default: 20 chars).

## Capabilities

### New Capabilities
- `routing-context`: Context enrichment logic that builds classification-ready inputs from the current user text and recent conversation buffer entries. Produces enriched text for embeddings (concatenation) and context for LLM fallback (conversational framing). Decides when to enrich based on short text threshold.

### Modified Capabilities
- `coordinator`: The Coordinator SHALL build enriched classification text before calling `Router.classify()` when the conversation buffer is non-empty and the current text is short. Passes both enriched text and context to the router.
- `agent-fsm`: The LLM fallback prompt SHALL include conversation context when available, enabling the LLM to reason about follow-up intent.

## Impact

- **Code**: New `backend/src/routing/context.py`, modified `backend/src/voice_runtime/coordinator.py` (enrichment before classify), modified `backend/src/routing/llm_fallback.py` (context parameter in prompt)
- **Config**: New settings `routing_context_window` (default: 1) and `routing_short_text_chars` (default: 20) in `backend/src/config.py`
- **No API changes**: Internal routing improvement, no external API surface affected
- **No data model changes**: ConversationBuffer is read-only for this feature
- **Risk**: Concatenated context may shift embedding distances for edge cases. Mitigated by only enriching short texts (< 20 chars) and keeping context window to 1 turn. LLM fallback provides a safety net for ambiguous cases.
