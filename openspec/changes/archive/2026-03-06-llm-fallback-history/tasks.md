## 1. Backend: Configuration

- [x] 1.1 [BE] Add `llm_context_window: int = 3` to `Settings` in `src/config.py`

## 2. Backend: RoutingContextBuilder multi-turn LLM context

- [x] 2.1 [BE] Add `llm_context_window` parameter to `RoutingContextBuilder.__init__()` (default: 3)
- [x] 2.2 [BE] Implement multi-turn `llm_context` format in `RoutingContextBuilder.build()` — use up to `llm_context_window` entries from buffer with structured `turn[-N] user: / turn[-N] route:` format
- [x] 2.3 [BE] Ensure embedding enrichment (`enriched_text`) still uses only `routing_context_window` entries (no regression)

## 3. Backend: Coordinator wiring

- [x] 3.1 [BE] Pass `llm_context_window` from Settings to `RoutingContextBuilder` in Coordinator constructor

## 4. Unit Tests: RoutingContextBuilder

- [x] 4.1 [TEST] Test builder accepts `llm_context_window` parameter and defaults to 3
- [x] 4.2 [TEST] Test `llm_context` with 3 prior turns produces structured multi-turn format
- [x] 4.3 [TEST] Test `llm_context` with 1 prior turn (fewer than window) produces single turn block
- [x] 4.4 [TEST] Test `llm_context` is `None` when buffer is empty (first turn)
- [x] 4.5 [TEST] Test `llm_context_window=1` produces single-turn format
- [x] 4.6 [TEST] Test embedding enrichment still uses `routing_context_window` (independence check)
- [x] 4.7 [TEST] Test `llm_context` with buffer larger than window only uses most recent N entries

## 5. Unit Tests: Router / LLM fallback

- [x] 5.1 [TEST] Test multi-turn `llm_context` string is passed through `Router._llm_classify_a` to `LLMFallbackClient.classify(context=...)`
- [x] 5.2 [TEST] Test multi-turn `llm_context` string is passed through `Router._llm_classify_b` to `LLMFallbackClient.classify(context=...)`

## 6. Unit Tests: Coordinator

- [x] 6.1 [TEST] Test Coordinator passes `llm_context_window` setting to `RoutingContextBuilder`
- [x] 6.2 [TEST] Test multi-turn `llm_context` reaches `Router.classify()` for a 3rd-turn transcript

## 7. E2E Tests

- [x] 7.1 [E2E] Test 3-turn conversation produces multi-turn `llm_context` in `Router.classify()` call
