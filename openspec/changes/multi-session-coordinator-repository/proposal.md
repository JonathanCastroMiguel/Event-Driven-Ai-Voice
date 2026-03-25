## Why

Today, session management lives as an in-memory dict (`_sessions`) in calls.py—one coordinator, one process, no sharing. This architecture blocks multi-coordinator-per-process deployment, prevents process-level concurrency limits, and couples HTTP routing to session lifecycle. We need a repository abstraction to isolate session management, enforce concurrency constraints, integrate Redis for external visibility, and support future scaling patterns.

## What Changes

- **Create SessionRepository class** — Extract session lifecycle from calls.py into a dedicated repository holding the registry of active CallSession runtime stacks, keyed by call_id
- **Enforce concurrency limits** — Add configurable `max_sessions_per_process` (default 50); return 503 Service Unavailable when exceeded, enabling load balancer routing
- **Activate Redis secondary index** — Connect existing RedisSessionRegistry as a secondary index; external systems can query "which process handles call X?"
- **Implement graceful shutdown** — On SIGTERM, send termination events to all Coordinators, wait configurable drain period, force-close remaining sessions
- **Add call_id isolation guard** — Runtime assertion ensuring no session shares a call_id and Coordinators only process matching EventEnvelopes
- **Decouple calls.py** — Route handlers become thin HTTP-to-repository dispatchers; business logic moves to SessionRepository

No **BREAKING** changes; calls.py public API remains unchanged.

## Capabilities

### New Capabilities
- `session-repository`: Multi-call hosting per process with concurrency management, lifecycle hooks, and call_id isolation. Enables 1 Coordinator : 1 call with N calls per process; architecture open to 1 Coordinator : M calls.

### Modified Capabilities
- `coordinator`: Coordinator binding and lifecycle now managed via SessionRepository rather than direct calls.py dict access. Lifecycle hooks (create/remove/error) enable Redis and external service integration.

## Impact

- **Code**: calls.py route handlers, new SessionRepository class, RedisSessionRegistry activation, Coordinator initialization pattern
- **APIs**: POST /calls remains HTTP-level compatible; internal session resolution changes (dependency injection or repository lookup)
- **Dependencies**: Redis activation (existing); no new external dependencies
- **Systems**: Process-level lifecycle, graceful shutdown integration, call isolation and observability
