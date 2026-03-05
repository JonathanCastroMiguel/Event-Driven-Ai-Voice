## 1. Configuration

- [x] 1.1 [BE] Add `routing_context_window` (default: 1) and `routing_short_text_chars` (default: 20) to `Settings` in `backend/src/config.py`

## 2. Routing Context Builder

- [x] 2.1 [BE] Create `backend/src/routing/context.py` with `RoutingContextBuilder` class — constructor accepts `short_text_chars` and `context_window`
- [x] 2.2 [BE] Implement `build(user_text, language, buffer)` method returning `(enriched_text: str | None, llm_context: str | None)`
- [x] 2.3 [BE] Enriched text: concatenate previous turn's `user_text` + `. ` + current text when `len(user_text) < short_text_chars` and buffer is non-empty
- [x] 2.4 [BE] LLM context: produce `"language={lang}; previous_turn: {prev_text}"` when buffer is non-empty (regardless of text length)

## 3. Router Interface Changes

- [x] 3.1 [BE] Add optional `enriched_text: str | None = None` parameter to `Router.classify()`
- [x] 3.2 [BE] Use `enriched_text` (when provided) for embedding classification in Route A and Route B, while keeping original `text` for lexicon and short-utterance checks
- [x] 3.3 [BE] Add optional `llm_context: str | None = None` parameter to `Router.classify()` and pass it to LLM fallback calls (`_llm_classify_a`, `_llm_classify_b`)

## 4. Coordinator Integration

- [x] 4.1 [BE] Instantiate `RoutingContextBuilder` in `Coordinator.__init__()` using settings
- [x] 4.2 [BE] In `_on_human_turn_finalized`, call `builder.build()` before `Router.classify()` and pass enriched outputs

## 5. Unit Tests — RoutingContextBuilder

- [x] 5.1 [TEST] Test short text (< 20 chars) with non-empty buffer returns enriched text
- [x] 5.2 [TEST] Test long text (>= 20 chars) returns `enriched_text=None`
- [x] 5.3 [TEST] Test empty buffer returns both outputs as `None`
- [x] 5.4 [TEST] Test `llm_context` always produced when buffer is non-empty (even for long text)
- [x] 5.5 [TEST] Test context window of 1 uses only the most recent entry
- [x] 5.6 [TEST] Test custom `short_text_chars` threshold

## 6. Unit Tests — Router with Enrichment

- [x] 6.1 [TEST] Test `Router.classify()` uses `enriched_text` for embedding when provided
- [x] 6.2 [TEST] Test `Router.classify()` uses original `text` for lexicon check even when `enriched_text` is provided
- [x] 6.3 [TEST] Test `Router.classify()` uses original `text` for short utterance check even when `enriched_text` is provided
- [x] 6.4 [TEST] Test `llm_context` passed through to LLM fallback when ambiguous

## 7. Unit Tests — Coordinator Context Integration

- [x] 7.1 [TEST] Test Coordinator builds enriched text for short follow-up and passes to router
- [x] 7.2 [TEST] Test Coordinator does not enrich on first turn (empty buffer)
- [x] 7.3 [TEST] Test Coordinator does not enrich long text but still passes `llm_context`

## 8. E2E Tests

- [x] 8.1 [E2E] Two-turn flow: first turn "tengo un problema con mi factura" then short follow-up "de este mes" — verify router receives enriched text
- [x] 8.2 [E2E] First turn with short text (no prior context) — verify no enrichment applied
