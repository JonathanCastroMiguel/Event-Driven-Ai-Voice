<!-- BEGIN_ENRICHED_USER_STORY -->
# Enriched User Story

design-linked: false
scope:
  backend: true
  frontend: false
source: Manual
reference: N/A

## Overview
Refactor session management from in-memory singleton dict in calls.py into a dedicated SessionRepository class. This enables a single process to host multiple Coordinators (N calls per process), with architectural readiness for future 1-Coordinator:M-calls scaling.

## Problem Statement
**Current State:** Session lifecycle and CallSessionEntry registry lives directly in calls.py as `_sessions` dict — one coordinator, one process, no sharing mechanism. RedisSessionRegistry exists but is unused.

**Impact:** 
- Blocks multi-coordinator-per-process deployment
- No process-level concurrency limits or load-balancing signals
- Tight coupling between HTTP route layer and session lifecycle
- No graceful shutdown pattern for in-flight calls
- Reduces horizontal scalability

**Goal:** Provide a repository abstraction that isolates session management, enforces concurrency constraints, integrates Redis for external visibility, and supports future 1:M coordinator mapping.

## Scope

### Backend: True
- SessionRepository class design & implementation
- CallSessionEntry lifecycle management
- Concurrency enforcement & rejection handling
- Redis secondary index integration
- Graceful shutdown orchestration
- call_id isolation enforcement & tests
- Decoupling calls.py route handlers

### Frontend: False
No UI/frontend changes required.

## Acceptance Criteria

### SessionRepository CRUD & Lifecycle
- [ ] SessionRepository class initialized per process (singleton pattern or dependency injection)
- [ ] `create_session(call_id: UUID, voice_client_type: str) -> CallSessionEntry` creates entry, registers with Redis, fires `session_created` hook
- [ ] `get_session(call_id: UUID) -> CallSessionEntry | None` retrieves live session
- [ ] `remove_session(call_id: UUID)` removes entry, deregisters from Redis, fires `session_ended` hook
- [ ] `list_sessions() -> List[CallSessionEntry]` returns all active sessions
- [ ] `session_count() -> int` returns current count

### Concurrency & Load Shedding
- [ ] Constructor accepts `max_sessions_per_process: int` parameter (default 50)
- [ ] `create_session()` checks count before creation; if exceeded, raises exception → HTTP 503 with Retry-After
- [ ] Integration test: verify 503 rejection when limit hit

### call_id Isolation
- [ ] Runtime guard in SessionRepository prevents duplicate call_id entries
- [ ] Coordinator receives call_id context; verifies all EventEnvelope.call_id matches its own
- [ ] Integration test: two concurrent sessions; verify no event leakage

### Redis Integration
- [ ] `RedisSessionRegistry.register(call_id, process_id, metadata)` called on `create_session`
- [ ] `RedisSessionRegistry.remove(call_id)` called on `remove_session`
- [ ] GET `/admin/sessions?process_id=X` returns active calls for process (or use Redis query directly)

### Graceful Shutdown
- [ ] Process SIGTERM handler calls `SessionRepository.shutdown(timeout_sec: int = 10)`
- [ ] Shutdown sends termination event to each Coordinator
- [ ] Waits up to timeout for graceful drain
- [ ] Force-closes remaining sessions; logs details for potential reconnection
- [ ] Integration test: two active sessions → SIGTERM → verify drain logging

### Decoupling calls.py
- [ ] POST /calls route resolves session from repository or creates new one
- [ ] No session business logic in route handlers
- [ ] calls.py becomes thin HTTP-to-session dispatcher

### Test Coverage
- [ ] Unit tests: CRUD, max-concurrency rejection, isolation guard, lifecycle hooks
- [ ] Integration test: two concurrent sessions verify isolation
- [ ] Integration test: graceful shutdown drain
- [ ] Minimum 85% line coverage for SessionRepository module

## Out of Scope
- 1 Coordinator : M calls (future optimization; architecture shall not block it)
- Cross-process session migration / reconnection
- Router/inference horizontal scaling
- Load balancer configuration

## Technical Notes
- **Architecture:** SessionRepository as indirection layer naturally supports future 1:M coordinator dispatch
- **Scaling Model:** Voice Clients scale by ingress volume, Coordinators scale by CPU/memory per call, Routers by inference throughput — independent scaling axes
- **Redis Integration:** Existing RedisSessionRegistry activated as secondary index; no new external dependencies
- **Concurrency Model:** Single-process event loop (FastAPI + async); SessionRepository methods are non-blocking by design

## Dependencies
- Existing: RedisSessionRegistry (activate unused code path)
- Related to: EventEnvelope call_id propagation

<!-- END_ENRICHED_USER_STORY -->
