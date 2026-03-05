## Context

Greenfield Python 3.12 backend for a real-time voice AI call center runtime. No existing codebase to integrate with. The architecture follows Pattern A (Controlled Routing + Realtime Speech) where four in-process actors communicate through an async event bus. The MVP prioritizes stability and latency over horizontal scalability — all actors run in a single process.

Key constraints:
- Sub-150ms latency for common intents (greeting, guardrail) from turn finalized to voice start
- Must handle barge-in (user interrupts bot mid-speech) without double responses or orphaned tasks
- Must be provider-agnostic for the Realtime voice integration (adapter pattern)
- Must support idempotent event processing (network retries, duplicate deliveries)
- Must log routing decisions for threshold calibration from day 1

## Goals / Non-Goals

**Goals:**
- Deliver a stable, low-latency voice runtime that handles the full turn lifecycle (speech → classification → response/tool → voice output)
- Deterministic barge-in handling with full cancellation propagation
- Embedding-based intent routing with configurable thresholds and versioned registry
- Full observability: every event traced, every routing decision logged
- Clean adapter boundary for Realtime voice provider (swap without touching core logic)

**Non-Goals:**
- Multi-process / distributed deployment (MVP is single-process; event bus is in-process `asyncio.Queue`)
- Horizontal auto-scaling (future: replace `asyncio.Queue` with Redis Streams or Kafka)
- Frontend ops panel (separate change)
- Custom ASR/TTS model training
- Multi-tenant isolation (single tenant for MVP)
- Streaming partial responses (voice output is atomic per `voice_generation_id`)

## Decisions

### D1: In-process asyncio.Queue as event bus

**Choice**: `asyncio.Queue` with typed `EventEnvelope` structs.

**Alternatives considered**:
- Redis Streams: adds ~1-2ms per event hop; unnecessary when all actors are in-process
- RabbitMQ/Kafka: massive operational overhead for MVP; no multi-process need yet

**Rationale**: Zero network overhead. A single `coordinator_loop` consumes events and dispatches to handlers. Migration path to Redis Streams is straightforward — swap the Queue for a Stream consumer without changing actor logic.

### D2: Actors as asyncio Tasks (not threads, not processes)

**Choice**: Each actor (Coordinator, TurnManager, Agent FSM, ToolExecutor) is an `asyncio.Task` with a dedicated handler function.

**Alternatives considered**:
- Threading: GIL contention, harder to reason about shared state
- Multiprocessing: serialization overhead for every event, premature for MVP

**Rationale**: asyncio tasks share memory (no serialization), are lightweight, and naturally cooperative. CPU-heavy work (embeddings, MicroLLM) is offloaded to `loop.run_in_executor()` with a thread pool.

### D3: msgspec.Struct for all data structures on hot path

**Choice**: `msgspec.Struct` (frozen) for EventEnvelope, Turn, AgentGeneration, VoiceGeneration, ToolExecution, and all event payloads.

**Alternatives considered**:
- Pydantic v2: ~10-50x slower for encode/decode than msgspec
- dataclasses: no built-in serialization, weaker validation
- TypedDict: no runtime validation, no methods

**Rationale**: msgspec provides zero-copy decoding, compile-time struct validation, and frozen immutability. Critical for hot-path performance where every microsecond counts.

### D4: asyncpg raw queries on hot path, SQLAlchemy for admin

**Choice**: Dual-driver strategy. asyncpg with parameterized queries for runtime writes (turns, generations). SQLAlchemy 2.0 async for admin/CRUD endpoints.

**Alternatives considered**:
- SQLAlchemy everywhere: ORM overhead (query building, identity map) adds 2-5ms per operation on hot path
- asyncpg everywhere: loses productivity for admin endpoints where latency doesn't matter

**Rationale**: The hot path writes 3-5 rows per turn (turn, agent_generation, voice_generation, optionally tool_execution). Raw asyncpg keeps this under 1ms. Admin endpoints do complex joins/filters where SQLAlchemy shines.

### D5: FSM as Enum + dict (no library)

**Choice**: `AgentState(Enum)` with a `TRANSITIONS: dict[AgentState, dict[str, AgentState]]` mapping.

**Alternatives considered**:
- transitions library: adds dependency, magic methods, harder to trace
- pytransitions: same concerns

**Rationale**: The FSM has ~6 states and ~10 transitions. A dict lookup is explicit, traceable in logs, and testable with a simple assertion. No framework overhead.

### D6: Embedding-first routing with 3rd-party LLM fallback

**Choice**: Pre-computed centroids from text examples (build-time), cosine similarity at runtime. When confidence is below threshold or margin between top-2 classes < 0.05, fallback to a 3rd-party LLM API call (async HTTP) for classification.

**Alternatives considered**:
- LLM-only classification: 50-200ms per call, unpredictable latency, cost per request
- Local GGUF model (llama.cpp): eliminates network dependency but adds 2-4GB RAM and operational complexity
- Rule-based only: brittle, requires constant maintenance, poor multilingual coverage

**Rationale**: Embeddings handle 80-90% of intents in <20ms. The remaining 10-20% ambiguous cases use an async HTTP call to a 3rd-party LLM for classification (temperature 0, structured JSON output). No local model to manage. Latency depends on the provider but the fallback path is non-blocking (async).

### D7: Router registry as versioned YAML with language inheritance

**Choice**: `router_registry/v1/` with `base.yaml` (multilingual seed) + per-locale overrides (`es.yaml`, `en.yaml`). Thresholds in `thresholds.yaml`. Centroids computed at startup from text examples.

**Alternatives considered**:
- Database-stored config: harder to version, review, and audit
- Hardcoded thresholds: no calibration path

**Rationale**: YAML is git-versionable, auditable, and editable by non-engineers (business team can add examples). Semantic versioning (`v1.0.0`) enables safe rollout. Language inheritance avoids duplication.

### D8: Redis for idempotency and session state

**Choice**: Redis TTL sets for `seen_event_ids` (300s TTL), Redis TTL maps for `tool_results` cache. Redis hash for active session registry.

**Alternatives considered**:
- In-memory sets: lost on restart, no sharing if we scale to multi-process
- PostgreSQL: too slow for hot-path dedup checks

**Rationale**: Redis provides sub-millisecond reads with automatic TTL expiry. Survives process restarts. Natural migration path to multi-process.

### D9: Coordinator owns all cancellation logic

**Choice**: The Coordinator is the single authority for cancelling voice generations, agent generations, and tool executions. No actor cancels directly.

**Alternatives considered**:
- Distributed cancellation (each actor cancels its own work): race conditions, inconsistent state

**Rationale**: Single cancellation authority eliminates race conditions. On barge-in: Coordinator cancels voice → cancels agent generation → marks both in cancelled sets → any late results are ignored via set lookup.

### D10: Policy keys as closed enum

**Choice**: `PolicyKey(str, Enum)` with values like `greeting`, `guardrail_disallowed`, `handoff_offer`. Agent FSM emits a policy key; Coordinator maps it to prompt instructions from `policies.yaml`.

**Alternatives considered**:
- Free-text prompts from Agent: non-deterministic, unauditable, prompt injection risk
- Hardcoded prompts in Coordinator: not configurable

**Rationale**: Closed enum ensures every possible response is auditable and testable. Prompt templates live in the registry and are reviewable by business. Agent FSM complexity stays minimal.

## Data Model

### PostgreSQL Schema (5 core tables)

```
call_sessions
  call_id         UUID PK
  provider_call_id TEXT
  started_at      BIGINT NOT NULL
  ended_at        BIGINT
  status          TEXT NOT NULL (active, ended)
  locale_hint     TEXT
  customer_context JSONB

turns
  turn_id         UUID PK
  call_id         UUID FK -> call_sessions
  seq             INT NOT NULL
  started_at      BIGINT NOT NULL
  finalized_at    BIGINT
  text_final      TEXT
  language        TEXT
  state           TEXT NOT NULL (open, finalized, cancelled)
  cancel_reason   TEXT
  asr_confidence  FLOAT

agent_generations
  agent_generation_id UUID PK
  call_id             UUID FK -> call_sessions
  turn_id             UUID FK -> turns
  created_at          BIGINT NOT NULL
  started_at          BIGINT
  ended_at            BIGINT
  state               TEXT NOT NULL (thinking, waiting_tools, waiting_voice, done, cancelled, error)
  route_a_label       TEXT
  route_a_confidence  FLOAT
  policy_key          TEXT
  specialist          TEXT
  final_outcome       TEXT
  cancel_reason       TEXT
  error               TEXT

voice_generations
  voice_generation_id          UUID PK
  provider_voice_generation_id TEXT
  call_id                      UUID FK -> call_sessions
  agent_generation_id          UUID FK -> agent_generations
  turn_id                      UUID FK -> turns
  kind                         TEXT NOT NULL (filler, response)
  state                        TEXT NOT NULL (starting, speaking, completed, cancelled, error)
  started_at                   BIGINT
  ended_at                     BIGINT
  cancel_reason                TEXT
  error                        TEXT

tool_executions
  tool_request_id     UUID PK
  call_id             UUID FK -> call_sessions
  agent_generation_id UUID FK -> agent_generations
  turn_id             UUID FK -> turns
  tool_name           TEXT NOT NULL
  args_hash           TEXT NOT NULL
  args_json           JSONB
  state               TEXT NOT NULL (running, succeeded, failed, cancelled, timeout)
  started_at          BIGINT
  ended_at            BIGINT
  result_json         JSONB
  error               TEXT
```

### Indexes

- `turns(call_id, seq)` — turn ordering per call
- `agent_generations(turn_id)` — lookup generation by turn
- `voice_generations(agent_generation_id)` — all voice outputs per generation
- `tool_executions(agent_generation_id)` — all tools per generation
- `call_sessions(status)` — active call lookup

## Risks / Trade-offs

**[Single-process bottleneck]** → All actors share one event loop. If CPU-heavy work (embeddings) blocks the loop, all calls degrade.
→ *Mitigation*: Offload embeddings and MicroLLM to `loop.run_in_executor(thread_pool)`. Monitor event loop lag via OpenTelemetry. Migration to multi-process with Redis Streams is a known path.

**[Embedding model cold start]** → First classification after startup is slow (~2-5s model load).
→ *Mitigation*: Load models eagerly at startup (before accepting calls). Health check returns unhealthy until models are ready.

**[3rd-party LLM availability]** → Fallback classification depends on external API uptime and latency.
→ *Mitigation*: Set aggressive timeout (2s). If LLM call fails or times out, use the embedding result as-is (best-effort classification). Log the fallback for monitoring. Provider is swappable via config.

**[Redis as single point of failure]** → If Redis goes down, idempotency and session registry fail.
→ *Mitigation*: Coordinator falls back to in-memory TTL sets if Redis is unreachable. Log a warning. For MVP, Redis downtime is acceptable with degraded idempotency.

**[Threshold calibration requires traffic]** → Initial thresholds are educated guesses.
→ *Mitigation*: Log every routing decision with scores/margins from day 1. Recalibrate after 1-2 days of real traffic. Thresholds are hot-reloadable via registry version bump.

**[Provider lock-in risk]** → Realtime voice adapter must remain truly agnostic.
→ *Mitigation*: Define adapter as a Python Protocol with typed methods. Integration tests verify the Protocol contract, not a specific provider.

## Resolved Questions

- **Q1**: CoordinatorRuntimeState lives **in-memory only** during the call. No Redis persistence per state change — zero added latency. State is reconstructable from the event log if needed post-crash. Acceptable trade-off for MVP (10 concurrent calls).
- **Q2**: MicroLLM fallback uses a **3rd-party LLM API via async HTTP** (`httpx.AsyncClient`). No local model, no thread pool needed — it's pure async I/O. Concurrency is managed by the async client's connection pool (max=10).
- **Q3**: **10 concurrent calls** for MVP. This determines: asyncpg pool (min=5, max=20), Redis connection pool (max=20), embedding thread pool (size=4), LLM HTTP client pool (max=10). Total RAM budget: ~2GB (app + embedding model, no local GGUF).
