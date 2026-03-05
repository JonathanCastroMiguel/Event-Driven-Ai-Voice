## 1. Project Scaffolding

- [x] 1.1 [BE] Initialize Python 3.12 project with `uv init`, create `pyproject.toml` with ruff, mypy, pytest config
- [x] 1.2 [BE] Create backend directory structure (`src/voice_runtime/`, `src/routing/`, `src/domain/`, `src/infrastructure/`, `src/api/`, `tests/`)
- [x] 1.3 [BE] Add core dependencies: asyncpg, fastapi, uvicorn, uvloop, msgspec, orjson, structlog, redis, httpx, pydantic-settings
- [x] 1.4 [BE] Add dev dependencies: pytest, pytest-asyncio, pytest-cov, ruff, mypy, testcontainers, pre-commit
- [x] 1.5 [BE] Create `src/config.py` with pydantic-settings (DATABASE_URL, REDIS_URL, SENTRY_DSN, OTEL_ENDPOINT)
- [x] 1.6 [BE] Create `Dockerfile` (multi-stage, uv-based) and `docker-compose.yml` (app + postgres:16 + redis:7)

## 2. Event Bus & Core Types

- [x] 2.1 [BE] Define core identifiers and type aliases in `src/voice_runtime/types.py` (CallId, TurnId, AgentGenerationId, VoiceGenerationId, ToolRequestId, PolicyKey enum, AgentState enum, route labels)
- [x] 2.2 [BE] Implement `EventEnvelope` as `msgspec.Struct(frozen=True)` in `src/voice_runtime/events.py` with all required fields
- [x] 2.3 [BE] Define all typed event structs: speech events, turn events, agent events, coordinator events, tool events, voice output events
- [x] 2.4 [BE] Implement event bus in `src/voice_runtime/bus.py` — bounded `asyncio.Queue[EventEnvelope]` with typed dispatch
- [x] 2.5 [TEST] Unit tests for EventEnvelope creation, causal chain tracking, and event type validation
- [x] 2.6 [TEST] Unit tests for event bus dispatch, backpressure, and unknown event handling

## 3. Domain Entities & Persistence

- [x] 3.1 [BE] Define domain entities as `msgspec.Struct`: CallSessionContext, Turn, AgentGeneration, VoiceGeneration, ToolExecution
- [x] 3.2 [BE] Create Alembic setup and initial migration with 5 core tables (call_sessions, turns, agent_generations, voice_generations, tool_executions) with indexes
- [x] 3.3 [BE] Implement `src/infrastructure/db.py` — asyncpg pool factory and SQLAlchemy async engine factory
- [x] 3.4 [BE] Define repository Protocol interfaces in `src/domain/repositories/` (CallRepository, TurnRepository, AgentGenerationRepository, VoiceGenerationRepository, ToolExecutionRepository)
- [x] 3.5 [BE] Implement asyncpg repository implementations in `src/infrastructure/repositories/` for hot-path writes (insert/update with raw parameterized queries)
- [x] 3.6 [TEST] Integration tests for repositories using testcontainers (PostgreSQL) — insert, update, query for each entity

## 4. Redis Infrastructure

- [x] 4.1 [BE] Implement `src/infrastructure/redis_client.py` — Redis connection pool, TTLSet helper (seen_event_ids), TTLMap helper (tool_results)
- [x] 4.2 [BE] Implement Redis session registry (hset/hget/expire for active call sessions)
- [x] 4.3 [TEST] Integration tests for Redis TTLSet, TTLMap, and session registry using testcontainers (Redis)

## 5. Router Registry

- [x] 5.1 [BE] Create `router_registry/v1/` with all YAML files: thresholds.yaml, route_a/ (base.yaml, es.yaml, en.yaml), route_b/ (base.yaml, es.yaml, en.yaml), policies.yaml, lexicon_disallowed/ (es.txt, en.txt), short_utterances/ (es.yaml, en.yaml)
- [x] 5.2 [BE] Implement registry loader in `src/routing/registry.py` — parse YAML, validate thresholds, load lexicons, load short utterances, resolve language inheritance
- [x] 5.3 [BE] Implement policies loader — parse policies.yaml, validate all PolicyKey enum values have entries, expose base_system + per-key instructions
- [x] 5.4 [TEST] Unit tests for registry loader: valid config, missing fields, language fallback, unknown policy key

## 6. Routing Engine

- [x] 6.1 [BE] Implement `src/routing/language.py` — fasttext language detection, supported language check, default fallback
- [x] 6.2 [BE] Implement `src/routing/lexicon.py` — case-insensitive lexicon matching, per-language loading
- [x] 6.3 [BE] Implement `src/routing/embeddings.py` — model loading (sentence-transformers/onnxruntime), centroid computation from text examples, cosine similarity scoring
- [x] 6.4 [BE] Implement `src/routing/llm_fallback.py` — async HTTP call to 3rd-party LLM for classification (httpx.AsyncClient, temperature 0, structured JSON, 2s timeout, graceful fallback)
- [x] 6.5 [BE] Implement `src/routing/router.py` — full classification pipeline: (1) detect language, (2) lexicon check, (3) short utterance check, (4) Route A embedding, (5) Route B embedding, (6) LLM fallback if ambiguous
- [x] 6.6 [TEST] Unit tests for language detection, lexicon matching, short utterance matching
- [x] 6.7 [TEST] Unit tests for Route A classification (each class, high/medium/low confidence)
- [x] 6.8 [TEST] Unit tests for Route B classification (each specialist, ambiguity detection)
- [x] 6.9 [TEST] Unit tests for LLM fallback (success, timeout, disabled)
- [x] 6.10 [TEST] Unit tests for full pipeline order (lexicon short-circuits, short utterance short-circuits)

## 7. TurnManager Actor

- [x] 7.1 [BE] Implement `src/voice_runtime/turn_manager.py` — turn detection from speech/transcript events, turn state machine (open → finalized | cancelled), sequential seq numbering, barge-in turn replacement
- [x] 7.2 [TEST] Unit tests for turn lifecycle: complete turn, cancelled turn (no transcript), barge-in creates new turn, sequential numbering

## 8. Agent FSM Actor

- [x] 8.1 [BE] Implement `src/voice_runtime/agent_fsm.py` — FSM with Enum states + dict transitions, event handling for handle_turn and cancel_agent_generation
- [x] 8.2 [BE] Integrate routing engine into Agent FSM — classification pipeline invocation, emit request_guided_response or request_agent_action based on result
- [x] 8.3 [TEST] Unit tests for FSM state transitions (valid, invalid, cancellation from any active state)
- [x] 8.4 [TEST] Unit tests for Agent FSM routing integration (simple→greeting, disallowed→guardrail, domain→specialist, ambiguous→clarify)

## 9. Tool Executor Actor

- [x] 9.1 [BE] Implement `src/voice_runtime/tool_executor.py` — deterministic tool_request_id generation, tool whitelist validation, execution with timeout (asyncio.wait_for), cancellation support
- [x] 9.2 [BE] Integrate Redis tool result caching — check cache before execution, cache on success
- [x] 9.3 [TEST] Unit tests for tool_request_id determinism, timeout, cancellation, cache hit/miss, unknown tool rejection

## 10. Coordinator Actor

- [x] 10.1 [BE] Implement `src/voice_runtime/state.py` — CoordinatorRuntimeState dataclass (active IDs, cancelled sets)
- [x] 10.2 [BE] Implement `src/voice_runtime/coordinator.py` — coordinator loop consuming from event bus, handler dispatch by event type
- [x] 10.3 [BE] Implement turn lifecycle orchestration in Coordinator — on human_turn_finalized: create agent_generation_id, dispatch handle_turn, handle rapid successive turns
- [x] 10.4 [BE] Implement barge-in handling in Coordinator — on speech_started with active voice: cancel voice, cancel agent, add to cancelled sets, forward to TurnManager
- [x] 10.5 [BE] Implement prompt construction — combine base_system + policy_key instructions + user_text, validate policy_key against enum
- [x] 10.6 [BE] Implement filler strategy in Coordinator — emit filler when estimated latency > 350ms, cancel filler on tool_result, auto-cancel at 1200ms
- [x] 10.7 [BE] Implement idempotency in Coordinator — event dedup via Redis TTLSet (fallback to in-memory), tool result caching via TTLMap
- [x] 10.8 [BE] Implement late result handling — ignore tool_result and voice callbacks for cancelled generation/voice IDs
- [x] 10.9 [BE] Wire persistence — call Coordinator repositories on state changes (turn insert, generation insert/update, voice generation insert/update, tool execution insert/update)

## 11. Realtime Adapter

- [x] 11.1 [BE] Define Realtime adapter Protocol in `src/voice_runtime/realtime_client.py` — typed methods: send_voice_start, send_voice_cancel, on_event callback registration
- [x] 11.2 [BE] Implement a stub/mock Realtime adapter for testing (emits voice_generation_completed after configurable delay)
- [x] 11.3 [TEST] Unit tests verifying the Protocol contract with the stub adapter

## 12. Application Wiring & FastAPI

- [x] 12.1 [BE] Implement `src/main.py` — startup: create pools (asyncpg, Redis), load router registry + embedding models, instantiate actors, start actor tasks with TaskGroup
- [x] 12.2 [BE] Implement `src/api/app.py` — FastAPI factory with CORS, error middleware, request ID middleware
- [x] 12.3 [BE] Implement health check endpoint (`GET /health`) — check asyncpg pool, Redis, models loaded
- [x] 12.4 [BE] Implement metrics endpoint (`GET /metrics`) — Prometheus exposition
- [x] 12.5 [BE] Implement admin endpoints: `GET /api/v1/calls` (list), `GET /api/v1/calls/{call_id}` (detail with turns, generations)

## 13. Observability

- [x] 13.1 [BE] Implement `src/infrastructure/telemetry.py` — OpenTelemetry SDK setup (tracer provider, span processor, exporter config)
- [x] 13.2 [BE] Add span instrumentation to Coordinator event loop — span per event with call_id, turn_id, agent_generation_id attributes
- [x] 13.3 [BE] Add Prometheus metrics — register histograms (turn_latency, route_confidence, tool_execution), counters (barge_in, fallback_llm, filler_emitted), gauge (active_calls)
- [x] 13.4 [BE] Add Sentry integration — init with call_id tag, capture unhandled exceptions
- [x] 13.5 [BE] Add structured router calibration logging — log every routing decision with all required fields (router_version, scores, margin, fallback_used, final_action)

## 14. Integration Tests (Event Pipeline)

- [x] 14.1 [E2E] Implement FakeRealtime fixture (injects speech/transcript events, captures voice output events)
- [x] 14.2 [E2E] Implement OutputCapture fixture (waits for specific event types with timeout)
- [x] 14.3 [E2E] Test: simple turn lifecycle (greeting → guided response → voice completed → cleanup)
- [x] 14.4 [E2E] Test: turn with specialist agent (domain → Route B → tool execution → voice response)
- [x] 14.5 [E2E] Test: barge-in during voice output (cancel voice + cancel agent → new turn)
- [x] 14.6 [E2E] Test: barge-in during tool execution (cancel tool → late tool_result ignored)
- [x] 14.7 [E2E] Test: filler emitted + cancelled on tool result + final response
- [x] 14.8 [E2E] Test: idempotency — duplicate event_id ignored
- [x] 14.9 [E2E] Test: rapid successive turns — previous generation cancelled
- [x] 14.10 [E2E] Test: guardrail disallowed (lexicon match → guided response)
- [x] 14.11 [E2E] Test: guardrail out_of_scope (embedding match → guided response)
- [x] 14.12 [E2E] Test: ambiguous Route B → clarify_department
- [x] 14.13 [E2E] Test: tool timeout → error response
- [x] 14.14 [E2E] Test: voice generation error → retry or error response
- [x] 14.15 [E2E] Test: call cleanup — all tasks cancelled, state clean, no orphaned tasks
