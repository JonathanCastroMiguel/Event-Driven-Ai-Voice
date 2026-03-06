## Why

The LLM fallback classifier currently receives only 1 prior turn as a flat string (`"language=es; previous_turn: ..."`). Unlike the embedding router, the LLM can natively reason about multi-turn conversation flow to disambiguate short or ambiguous follow-ups. Expanding the context window to 2-3 prior turns will significantly improve classification accuracy for sequential domain interactions (e.g., billing follow-ups, multi-step support queries).

## What Changes

- Expand `RoutingContextBuilder` to produce structured multi-turn `llm_context` (up to 3 prior turns) instead of a single `previous_turn` string.
- Add a new `llm_context_window` setting (default: 3) independent of the embedding `routing_context_window` (stays at 1).
- Update `LLMFallbackClient._build_classification_prompt()` to format multi-turn conversation history as labeled turns in the prompt.
- Update `Router._llm_classify_a` and `_llm_classify_b` to pass the richer context through.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `routing-context`: RoutingContextBuilder produces multi-turn `llm_context` with configurable window size, separate from embedding enrichment window.
- `agent-fsm`: LLM fallback prompt includes structured multi-turn conversation context when available.
- `coordinator`: Reads new `llm_context_window` setting and passes it to the RoutingContextBuilder.

## Impact

- **Code**: `src/routing/context.py`, `src/routing/llm_fallback.py`, `src/routing/router.py`, `src/config.py`, `src/voice_runtime/coordinator.py`
- **APIs**: No external API changes. Internal `classify()` signature unchanged (llm_context remains `str | None`).
- **Dependencies**: None.
- **Backward compatibility**: Fully backward-compatible. When buffer has 0-1 entries, behavior is identical to current. When `llm_context_window=1`, output matches the previous single-turn format.
