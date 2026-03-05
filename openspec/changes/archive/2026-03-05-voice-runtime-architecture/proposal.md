## Why

The business needs a voice AI runtime capable of handling real-time call center interactions with sub-150ms response latency for common intents. No existing open-source runtime provides the combination of controlled routing (embedding-based classification), policy-driven speech generation, and deterministic barge-in handling required. Building the Event-Driven Voice Runtime as the foundational layer enables all future voice agent capabilities.

## What Changes

- Introduce an in-process async event bus (`asyncio.Queue`) connecting four actors: Coordinator, TurnManager, Agent FSM, and ToolExecutor
- Implement the Coordinator (CallSession) as the single point of tool execution, speech output, cancellation, and idempotency
- Implement TurnManager for human turn detection from VAD/transcript events
- Implement Agent FSM for intent classification with Route A (simple/disallowed/out_of_scope/domain) and Route B (sales/billing/support/retention) using embedding-based routing
- Implement policy-key-driven prompt construction for Realtime voice output (closed enum, no free-text)
- Implement barge-in handling with full cancellation propagation (voice + agent generation + tools)
- Implement filler strategy for tool latency > 350ms
- Implement idempotency via Redis TTL sets (event dedup) and TTL maps (tool result caching)
- Implement the router registry (versioned YAML) with centroids, thresholds, lexicon rules, and short utterance matching
- Define the event contract v1: EventEnvelope with correlation_id/causation_id for full traceability
- Persist runtime entities: CallSessionContext, Turn, AgentGeneration, VoiceGeneration, ToolExecution
- Add OpenTelemetry tracing, Prometheus metrics, and Sentry error tracking
- Add FastAPI admin/health endpoints (not on the voice hot path)

## Capabilities

### New Capabilities

- `event-bus`: In-process async event bus with EventEnvelope, typed event definitions, and actor-to-actor routing
- `coordinator`: CallSession actor — runtime state management, barge-in cancellation, idempotency, filler orchestration, and prompt construction via policy keys
- `turn-manager`: Human turn detection from speech/transcript events, turn lifecycle (open/finalized/cancelled)
- `agent-fsm`: Intent classification FSM with Route A/B embedding-based routing, MicroLLM fallback, and policy key emission
- `tool-executor`: Deterministic tool execution with timeout, cancellation, result caching, and idempotency
- `router-registry`: Versioned YAML registry of thresholds, centroids (text examples), lexicon rules, short utterances, and policies — with language inheritance (base + locale overrides)
- `runtime-persistence`: PostgreSQL schema and repositories for CallSessionContext, Turn, AgentGeneration, VoiceGeneration, and ToolExecution entities
- `observability`: OpenTelemetry tracing across the event pipeline, Prometheus metrics (latency histograms, counters), Sentry integration, and router calibration logging

### Modified Capabilities

(none — greenfield project)

## Impact

- **New codebase**: Entire `backend/src/` directory with voice_runtime, routing, domain, infrastructure, and api modules
- **Database**: New PostgreSQL schema with 5 core tables (call_sessions, turns, agent_generations, voice_generations, tool_executions)
- **Redis**: TTL-based idempotency sets and tool result cache; session registry
- **Configuration**: Router registry YAML files under `router_registry/v1/`
- **Infrastructure**: Docker Compose with Python 3.12, PostgreSQL 16, and Redis 7
- **Dependencies**: asyncpg, FastAPI, uvicorn, msgspec, orjson, sentence-transformers, onnxruntime, hnswlib, fasttext, structlog, opentelemetry-sdk, sentry-sdk, redis
- **External integrations**: Realtime voice provider (adapter interface — provider-agnostic)
