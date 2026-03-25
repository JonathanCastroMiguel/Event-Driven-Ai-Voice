## Context

**Current State:**
- Session management (`_sessions` dict) lives in calls.py as an in-memory registry
- One Coordinator per process; one call per Coordinator
- RedisSessionRegistry exists but is unused; no external visibility
- HTTP route layer tightly coupled to session lifecycle
- No process-level concurrency limits or graceful shutdown

**Stakeholders:**
- Backend infrastructure (deployment, load balancing)
- Voice runtime (Coordinator lifecycle)
- Observability (process and call visibility)

**Constraints:**
- Single-process event loop (FastAPI + async)
- Redis available (existing)
- Must support future 1 Coordinator : M calls without redesign
- Current HTTP/WS API surface must remain stable

## Goals / Non-Goals

**Goals:**
- Isolate session management into a dedicated SessionRepository class
- Enable N Coordinators per process (N calls per process)
- Enforce process-level concurrency limits (configurable max_sessions_per_process)
- Activate Redis secondary index for load-balancer and observability queries
- Implement graceful shutdown with event drain and force-close fallback
- Add runtime call_id isolation guard (no event leakage between sessions)
- Decouple HTTP routing from session business logic
- Maintain HTTP/WS API compatibility (calls.py public interface unchanged)

**Non-Goals:**
- Implement 1 Coordinator : M calls (future optimization; architecture shall not block it)
- Cross-process session migration or reconnection
- Router/inference scaling
- Load balancer configuration
- Real-time session metrics dashboard (Redis queries available; UI is out of scope)

## Decisions

### Decision 1: SessionRepository as Singleton or Dependency Injection

**Choice:** Dependency injection via FastAPI dependency (recommended).

**Rationale:**
- Testability: Easier to mock in unit tests
- Multi-instance support: Future use (e.g., multiple coordinator processes)
- Explicit lifecycle: Aligned with FastAPI application lifecycle

**Alternative:** Global singleton (simpler, less flexible for testing and scaling)

---

### Decision 2: Concurrency Enforcement Strategy

**Choice:** Enforce `max_sessions_per_process` at create_session time; reject with 503 Service Unavailable + Retry-After header.

**Rationale:**
- Simple and predictable (fail fast, not under-the-hood queueing)
- Enables external load balancer to route to another process
- Retry-After allows client backoff
- Prevents unbounded resource growth

**Alternative:** Queue requests (complex, unpredictable latency)

---

### Decision 3: Redis Integration Timing

**Choice:** Activate Redis on session create/remove (synchronous, non-blocking).

**Rationale:**
- Existing RedisSessionRegistry code path; minimal new logic
- External systems (load balancer query, admin dashboard) get immediate visibility
- Non-blocking design (Redis calls are async-compatible)

**Alternative:** Batch Redis updates (delayed visibility) or polling (inefficient)

---

### Decision 4: Graceful Shutdown Mechanism

**Choice:** On SIGTERM, iterate sessions, send termination event to each Coordinator, wait up to `shutdown_timeout` (default 10s), then force-close.

**Rationale:**
- Coordinator can flush queued events and clean resources
- Configurable timeout prevents indefinite hangs
- Force-close ensures eventual shutdown
- Logs active calls for potential reconnection by load balancer

**Alternative:** Immediate hard shutdown (loses graceful drain)

---

### Decision 5: call_id Isolation Guard Implementation

**Choice:** 
1. SessionRepository enforces unique call_id on create (no duplicates in dict)
2. Coordinator receives call_id context; validates each EventEnvelope.call_id matches
3. Runtime assert if mismatch; log and drop event

**Rationale:**
- Defense in depth (guard at repository + Coordinator level)
- Early detection of bugs or misconfiguration
- Prevents silent event leakage

**Alternative:** Single guard point (less robust to future refactors)

---

### Decision 6: Architecture for Future 1:M Coordinator Scaling

**Choice:** SessionRepository keyed by call_id, not by Coordinator instance. Coordinator holds call_id set (or subscribes to events filtered by call_id).

**Rationale:**
- Naturally extends to 1 Coordinator : M calls
- Repository remains indirection layer; Coordinator scales independently
- Minimal re-architecture needed later

**Alternative:** Coordinator-to-sessions map (must rewrite on upscale)

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| **Thundering Herd on 503 rejection** — All clients retry simultaneously | Implement exponential backoff on client side; Retry-After header guides backoff |
| **Redis unavailability** — redis.SessionRegistry calls fail | Graceful degradation: log warning, continue (external visibility lost, but in-process calls still work) |
| **Graceful shutdown timeout too short** — In-flight calls are force-closed | Make timeout configurable; document recommended duration (10s default); monitor shutdown logs |
| **call_id isolation guard spurious fires** — Edge case in EventEnvelope routing | Comprehensive test coverage; monitor assert logs; validate event flow in integration tests |
| **Future 1:M Coordinator scaling unknown costs** — Coordinator memory/CPU per call count | Benchmark early; profile at 5, 10, 50 calls; adjust max_sessions_per_process cap |

## Migration Plan

**Phase 1: Add SessionRepository (backward-compat)**
- Create `SessionRepository` class; keep `_sessions` dict in calls.py
- Add lifecycle hooks (session_created, session_ended, session_error)
- Populate repository from calls.py on HTTP request
- Redis integration activated but update-only (no queueing)

**Phase 2: Route Migration**
- Update POST /calls to use SessionRepository.create_session()
- Update GET /calls/{call_id} to use SessionRepository.get_session()
- Remove direct `_sessions` dict access from route handlers
- Keep `_sessions` dict as internal fallback (log if used)

**Phase 3: Graceful Shutdown & Tests**
- Add SIGTERM handler to SessionRepository.shutdown()
- Write unit tests (CRUD, concurrency, isolation, lifecycle hooks)
- Write integration test (two concurrent sessions, verify isolation)
- Integration test for graceful shutdown drain

**Rollback:**
- Session state is in-memory; restart process to revert
- Redis secondary index is optional (degraded observability, no functional impact)

## Open Questions

1. **Timeout for graceful drain**: Default 10s — is this sufficient? Should it be configurable per environment?
2. **Coordinator event filtering**: Does Coordinator need to actively filter by call_id, or is session isolation sufficient?
3. **Redis retry logic**: If Redis temporarily unavailable, should SessionRepository retry or fail fast?
4. **Metrics**: Should SessionRepository emit metrics (e.g., concurrent session count, rejections)? Integration with existing observability system?
5. **Future 1:M Coordinator dispatch**: Should Coordinator receive a "dispatch by call_id" callback, or iterate internally?

---

**Next Steps:**
- Create specs for `session-repository` capability
- Create delta spec for `coordinator` (lifecycle binding changes)
- Implement tasks based on acceptance criteria
