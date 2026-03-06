# Performance Benchmarks

**Date:** 2026-03-06

> Living document. We'll refine and expand these benchmarks as the system evolves.

---

## 1. Router.classify() Micro-Benchmark

**Setup:** 5000 iterations per scenario, mocked embeddings + LLM, `time.perf_counter_ns()`

| Scenario | Mean | Median | P95 | P99 | Min | Max |
|---|---|---|---|---|---|---|
| Lexicon short-circuit ("die") | 3.76 us | 2.92 us | 5.42 us | 20.71 us | 2.54 us | 254.42 us |
| Short utterance ("hola") | 4.78 us | 3.75 us | 7.00 us | 18.42 us | 3.33 us | 186.96 us |
| Embedding → simple | 8.45 us | 7.08 us | 12.08 us | 30.88 us | 6.21 us | 269.83 us |
| Embedding → domain + Route B | 13.72 us | 11.67 us | 19.00 us | 49.29 us | 10.25 us | 277.88 us |
| Embedding → domain, ambiguous B (no LLM) | 13.34 us | 11.38 us | 18.33 us | 50.58 us | 9.96 us | 268.58 us |
| Embedding → ambiguous A, LLM fallback | 19.49 us | 16.63 us | 26.42 us | 73.08 us | 14.46 us | 272.46 us |
| Embedding → out_of_scope | 8.34 us | 7.00 us | 11.79 us | 34.00 us | 6.13 us | 281.38 us |
| Embedding → disallowed | 8.61 us | 7.17 us | 12.42 us | 34.50 us | 6.25 us | 331.08 us |

### What's real vs mocked (Router)

| Component | Status | Notes |
|---|---|---|
| Lexicon matching | Real | In-memory set lookup |
| Short utterance matching | Real | In-memory dict lookup |
| Embedding inference | Mocked | Returns fake scores instantly |
| LLM fallback | Mocked | Returns immediately |
| Margin calculation | Real | top1 - top2 arithmetic |
| structlog calibration log | Real | Full `routing_completed` log emitted |

---

## 2. Full Coordinator Pipeline Benchmark

**Setup:** 2000 iterations per scenario, full event pipeline (speech_started → TurnManager → AgentFSM → Router → prompt build → RealtimeVoiceStart), `time.perf_counter_ns()`

| Scenario | Mean | Median | P95 | P99 | Min | Max |
|---|---|---|---|---|---|---|
| Lexicon short-circuit | 83.92 us | 75.17 us | 120.92 us | 195.46 us | 63.50 us | 1133.25 us |
| Short utterance | 83.55 us | 75.58 us | 116.71 us | 174.21 us | 63.96 us | 1010.38 us |
| Embedding → simple | 82.53 us | 74.75 us | 115.42 us | 189.67 us | 63.38 us | 988.54 us |
| Embedding → domain + Route B | 82.73 us | 74.88 us | 117.58 us | 193.29 us | 63.42 us | 1262.88 us |
| Embedding → ambiguous A + LLM fallback | 84.42 us | 75.79 us | 120.79 us | 184.08 us | 64.46 us | 1084.17 us |
| Embedding → out_of_scope | 83.37 us | 74.96 us | 119.46 us | 200.58 us | 63.21 us | 968.00 us |
| Embedding → disallowed | 82.37 us | 74.38 us | 117.67 us | 188.79 us | 62.75 us | 909.54 us |

### What's real vs mocked (Coordinator)

| Component | Status | Notes |
|---|---|---|
| EventEnvelope creation | Real | UUID generation, timestamps |
| Coordinator.handle_event() | Real | Full event dispatch, dedup, routing |
| TurnManager | Real | Turn lifecycle, state transitions |
| AgentFSM | Real | State machine transitions |
| Router.classify() | Mocked | Returns preset RoutingResult |
| Policy/prompt construction | Real | PoliciesRegistry lookup, system prompt build |
| Output event creation | Real | RealtimeVoiceStart events |
| StubRealtimeClient | Stub | 10ms delay configured but not awaited in pipeline |

---

## 3. Production Latency Estimates

| Layer | Estimated Latency | Notes |
|---|---|---|
| Internal pipeline (Coordinator + TurnManager + FSM + policies) | ~80 us | Measured above |
| Embedding inference (sentence-transformers/ONNX) | ~2-5 ms | CPU, depends on model & text length |
| LLM fallback (3rd-party API) | ~50-200 ms | Network-bound, only on ambiguous cases |
| **Typical turn (no fallback)** | **~3-7 ms** | Pipeline + embeddings |
| **Worst case (with LLM fallback)** | **~50-207 ms** | Pipeline + embeddings + LLM |

---

## Notes

- All benchmarks run on local dev machine (Apple Silicon), single-threaded asyncio.
- Embedding and LLM latencies are estimates based on typical production values; will be validated with real models.
- The internal pipeline overhead (~80us) is negligible compared to embedding/LLM costs.
- `structlog` calibration logging adds < 1us per call.
