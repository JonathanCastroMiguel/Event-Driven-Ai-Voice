## ADDED Requirements

### Requirement: Session creation with call_id binding
The SessionRepository SHALL provide a `create_session(call_id: UUID, voice_client_type: str) -> CallSessionEntry` method that creates and registers a new session. The method SHALL instantiate a CallSessionEntry holding the voice_client, Coordinator, EventBridge, FSM, TurnManager, and ToolExecutor for the given call_id. The method SHALL register the call_id with RedisSessionRegistry and fire the `session_created` lifecycle hook.

#### Scenario: Successful session creation
- **WHEN** `create_session(call_id=UUID(...), voice_client_type="webrtc")` is called
- **THEN** SessionRepository SHALL create a CallSessionEntry, instantiate all runtime actors, add to internal registry, call `redis.register(call_id, process_id, ...)`, and fire `session_created` hook

#### Scenario: Duplicate call_id rejected
- **WHEN** `create_session()` is called with a call_id that already exists in the registry
- **THEN** SessionRepository SHALL raise a `DuplicateSessionError`

#### Scenario: Max concurrency limit exceeded
- **WHEN** `create_session()` is called and `session_count() >= max_sessions_per_process`
- **THEN** SessionRepository SHALL raise `ConcurrencyLimitExceeded` (to be translated to HTTP 503 by route handler)

### Requirement: Session retrieval
The SessionRepository SHALL provide a `get_session(call_id: UUID) -> CallSessionEntry | None` method that retrieves an active session by call_id.

#### Scenario: Existing session retrieved
- **WHEN** `get_session(call_id=ID1)` is called and ID1 exists
- **THEN** SessionRepository SHALL return the CallSessionEntry for ID1

#### Scenario: Non-existent session returns None
- **WHEN** `get_session(call_id=ID_UNKNOWN)` is called
- **THEN** SessionRepository SHALL return `None`

### Requirement: Session removal with lifecycle notification
The SessionRepository SHALL provide a `remove_session(call_id: UUID) -> void` method that removes a session, deregisters from Redis, and fires the `session_ended` lifecycle hook.

#### Scenario: Session removed and Redis deregistered
- **WHEN** `remove_session(call_id=ID1)` is called
- **THEN** SessionRepository SHALL remove CallSessionEntry from registry, call `redis.remove(call_id)`, and fire `session_ended` hook

#### Scenario: Removing non-existent session is no-op
- **WHEN** `remove_session(call_id=ID_UNKNOWN)` is called
- **THEN** SessionRepository SHALL log a debug message and return without error

### Requirement: Session enumeration
The SessionRepository SHALL provide `list_sessions() -> List[CallSessionEntry]` and `session_count() -> int` methods for querying all active sessions.

#### Scenario: List all sessions
- **WHEN** `list_sessions()` is called with 3 active sessions
- **THEN** SessionRepository SHALL return a list of 3 CallSessionEntry objects

#### Scenario: Count sessions
- **WHEN** `session_count()` is called with 2 active sessions
- **THEN** SessionRepository SHALL return 2

#### Scenario: Empty registry
- **WHEN** there are no active sessions and `list_sessions()` is called
- **THEN** SessionRepository SHALL return an empty list; `session_count()` SHALL return 0

### Requirement: Concurrency limit enforcement
The SessionRepository SHALL accept a `max_sessions_per_process` configuration parameter (default 50). When the count reaches this limit, `create_session()` SHALL reject further creation.

#### Scenario: Default concurrency limit
- **WHEN** SessionRepository is instantiated without explicit max_sessions_per_process
- **THEN** max_sessions_per_process SHALL default to 50

#### Scenario: Custom concurrency limit
- **WHEN** SessionRepository is instantiated with `max_sessions_per_process=100`
- **THEN** up to 100 concurrent sessions SHALL be allowed; the 101st SHALL be rejected

#### Scenario: Concurrency limit rejection
- **WHEN** `create_session()` is called at the limit
- **THEN** SessionRepository SHALL raise `ConcurrencyLimitExceeded` with a message indicating the limit and current count

### Requirement: Lifecycle hooks
The SessionRepository SHALL support lifecycle hooks called at session creation, removal, and error. Each hook is a callback that receives the session context (call_id, voice_client_type, and other metadata).

#### Scenario: session_created hook fires
- **WHEN** a session is successfully created
- **THEN** SessionRepository SHALL invoke the registered `session_created` callback (if any) with call_id and session metadata

#### Scenario: session_ended hook fires
- **WHEN** a session is removed
- **THEN** SessionRepository SHALL invoke the registered `session_ended` callback (if any) with call_id and final session state

#### Scenario: session_error hook fires
- **WHEN** an error occurs during session management (e.g., Redis unavailable)
- **THEN** SessionRepository SHALL invoke the registered `session_error` callback (if any) with call_id, session metadata, and error details

### Requirement: Redis secondary index integration
The SessionRepository SHALL register and deregister sessions with RedisSessionRegistry. On `create_session()`, the repository SHALL call `redis.register(call_id, process_id, metadata)`. On `remove_session()`, it SHALL call `redis.remove(call_id)`.

#### Scenario: Session registered in Redis on creation
- **WHEN** `create_session(call_id=ID1)` completes successfully
- **THEN** SessionRepository SHALL have called `RedisSessionRegistry.register(ID1, process_id, ...)` so external systems can query "which process owns ID1?"

#### Scenario: Session deregistered from Redis on removal
- **WHEN** `remove_session(call_id=ID1)` completes
- **THEN** SessionRepository SHALL have called `RedisSessionRegistry.remove(ID1)` so Redis no longer lists ID1 as active

#### Scenario: Redis unavailable handled gracefully
- **WHEN** `redis.register()` raises an exception (e.g., connection timeout)
- **THEN** SessionRepository SHALL log a warning, but continue (i.e., session is created in-memory; Redis visibility is lost but in-process functionality remains)

### Requirement: Graceful shutdown orchestration
The SessionRepository SHALL provide a `shutdown(timeout_sec: int = 10)` method for graceful termination. The method SHALL iterate all active sessions, send a termination event to each Coordinator, wait up to `timeout_sec` for drain, then force-close remaining sessions.

#### Scenario: Graceful shutdown completes within timeout
- **WHEN** `shutdown(timeout_sec=10)` is called with 2 active sessions
- **THEN** SessionRepository SHALL send termination events to both Coordinators and wait up to 10s for them to finalize
- **AND** if both drain within the timeout, remove_session SHALL be called + logged as graceful

#### Scenario: Graceful shutdown timeout with force-close
- **WHEN** `shutdown(timeout_sec=10)` is called and one Coordinator does not drain within 10s
- **THEN** SessionRepository SHALL force-close that session after the timeout
- **AND** log the session as force-closed with call_id for potential reconnection

#### Scenario: No sessions on shutdown
- **WHEN** `shutdown()` is called with an empty registry
- **THEN** SessionRepository SHALL return immediately

### Requirement: call_id isolation enforcement
The SessionRepository SHALL enforce that no two sessions share the same call_id (runtime guard). If a caller attempts to create a duplicate session, the repository SHALL raise an error. Additionally, the repository SHALL ensure that Coordinators only process events with matching call_id.

#### Scenario: No duplicate call_id allowed
- **WHEN** `create_session(call_id=ID1)` succeeds and then `create_session(call_id=ID1)` is called again
- **THEN** SessionRepository SHALL raise `DuplicateSessionError`

#### Scenario: Each session has unique call_id
- **WHEN** two sessions are created with unique call_ids (ID1, ID2)
- **THEN** `get_session(ID1)` and `get_session(ID2)` SHALL return distinct CallSessionEntry objects

#### Scenario: Coordinator receives call_id context
- **WHEN** a Coordinator is instantiated via `create_session(call_id=ID1)`
- **THEN** the Coordinator SHALL be initialized with `call_id=ID1` in its context; all EventEnvelope processing SHALL validate matching call_id
