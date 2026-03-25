## 1. Setup & Infrastructure

- [x] 1.1 Create `src/infrastructure/session_repository.py` with SessionRepository class skeleton
- [x] 1.2 Create `src/infrastructure/session_models.py` with CallSessionEntry, SessionError exceptions (DuplicateSessionError, ConcurrencyLimitExceeded)
- [x] 1.3 Add SessionRepository to FastAPI dependency system (e.g., `app.dependency` or injector)
- [x] 1.4 Create lifecycle hook types (on_session_created, on_session_ended, on_session_error callbacks)

## 2. SessionRepository CRUD Implementation

- [x] 2.1 Implement `SessionRepository.__init__(max_sessions_per_process: int = 50)`
- [x] 2.2 Implement `create_session(call_id: UUID, voice_client_type: str) -> CallSessionEntry` with duplicate check and concurrency limit
- [x] 2.3 Implement `get_session(call_id: UUID) -> CallSessionEntry | None`
- [x] 2.4 Implement `remove_session(call_id: UUID) -> void`
- [x] 2.5 Implement `list_sessions() -> List[CallSessionEntry]`
- [x] 2.6 Implement `session_count() -> int`
- [x] 2.7 Test CRUD methods manually (quick smoke test) - 24 unit tests all passing

## 3. Lifecycle Hooks & Callbacks

- [x] 3.1 Implement `register_hook(event: str, callback: Callable)` in SessionRepository
- [x] 3.2 Implement hook firing in `create_session()` (on_session_created)
- [x] 3.3 Implement hook firing in `remove_session()` (on_session_ended)
- [x] 3.4 Implement hook firing on errors (on_session_error)
- [x] 3.5 Verify hooks are invoked during session lifecycle - tested and verified

## 4. Redis Integration

- [x] 4.1 Update `create_session()` to call `RedisSessionRegistry.register(call_id, process_id, metadata)`
- [x] 4.2 Update `remove_session()` to call `RedisSessionRegistry.remove(call_id)`
- [x] 4.3 Add graceful error handling for Redis unavailability (log warning, continue)
- [x] 4.4 Test Redis integration (may need test Redis instance or mock)

## 5. Graceful Shutdown

- [x] 5.1 Implement `shutdown(timeout_sec: int = 10)` method in SessionRepository
- [x] 5.2 Implement coordinator termination event emission in shutdown flow
- [x] 5.3 Implement timeout-based drain wait (using asyncio.wait_for or similar)
- [x] 5.4 Implement force-close fallback for sessions exceeding timeout
- [x] 5.5 Add logging for graceful vs. force-closed sessions
- [x] 5.6 Add SIGTERM signal handler in main.py that triggers repository.shutdown()

## 6. call_id Isolation Enforcement

- [x] 6.1 Add `call_id: UUID` field to Coordinator class (in runtime initializer)
- [x] 6.2 Add runtime assertion in SessionRepository to prevent duplicate call_id
- [x] 6.3 Add `call_id` validation in Coordinator event processing loop (drop events with mismatched call_id)
- [x] 6.4 Add observability counter for call_id mismatch events
- [x] 6.5 Update EventEnvelope routing to ensure all events have call_id set

## 7. Decoupling calls.py from Session Management

- [x] 7.1 Refactor `POST /calls` endpoint to use `SessionRepository.create_session()` instead of direct `_sessions` dict
- [x] 7.2 Handle `ConcurrencyLimitExceeded` exception in POST /calls and return 503 with Retry-After header
- [x] 7.3 Refactor session resolution pattern in route handlers to use `repository.get_session()` instead of `_sessions.get()`
- [x] 7.4 Remove or deprecate direct `_sessions` dict access; update to use repository as backend
- [x] 7.5 Verify calls.py HTTP API is backward compatible (same request/response contracts) - ✓ All existing tests pass

## 8. Unit Tests: SessionRepository CRUD

- [x] 8.1 Write test: `create_session()` with valid input
- [x] 8.2 Write test: `create_session()` rejects duplicate call_id
- [x] 8.3 Write test: `create_session()` rejects when concurrency limit exceeded
- [x] 8.4 Write test: `get_session()` returns existing session
- [x] 8.5 Write test: `get_session()` returns None for non-existent session
- [x] 8.6 Write test: `remove_session()` removes and is idempotent
- [x] 8.7 Write test: `list_sessions()` and `session_count()` are consistent

## 9. Unit Tests: Concurrency & Limits

- [x] 9.1 Write test: default `max_sessions_per_process` is 50
- [x] 9.2 Write test: custom `max_sessions_per_process` is respected
- [x] 9.3 Write test: `create_session()` at limit raises exception
- [x] 9.4 Write test: after `remove_session()`, count decreases and new sessions allowed

## 10. Unit Tests: Lifecycle Hooks

- [x] 10.1 Write test: `on_session_created` hook fires on create
- [x] 10.2 Write test: `on_session_ended` hook fires on remove
- [x] 10.3 Write test: `on_session_error` hook fires on exception
- [x] 10.4 Write test: multiple hooks can be registered

## 11. Unit Tests: call_id Isolation

- [x] 11.1 Write test: SessionRepository prevents duplicate call_id
- [x] 11.2 Write test: EventEnvelope mismatch counter increments on call_id mismatch in Coordinator
- [x] 11.3 Write test: get_session(call_id) returns distinct sessions for different call_ids

## 12. Unit Tests: Graceful Shutdown

- [x] 12.1 Write test: `shutdown()` with no sessions completes immediately
- [x] 12.2 Write test: `shutdown()` sends termination events to all coordinators
- [x] 12.3 Write test: `shutdown()` with timeout force-closes stalled sessions
- [x] 12.4 Write test: `shutdown()` logs graceful vs. force-closed outcome

## 13. Integration Tests

- [ ] 13.1 Write integration test: two concurrent sessions (different call_ids) in same process
- [ ] 13.2 In integration test: verify events from session 1 don't reach session 2
- [ ] 13.3 Write integration test: graceful shutdown with two active sessions
- [ ] 13.4 Verify integration tests pass locally

## 14. Documentation & Standards Compliance

- [ ] 14.1 Update `backend-standards.mdc` to document SessionRepository pattern (if missing)
- [ ] 14.2 Add docstrings to SessionRepository public methods (required by code standards)
- [ ] 14.3 Add docstrings to exception types
- [ ] 14.4 Add example usage documentation (how to instantiate repository, create sessions, etc.)
- [ ] 14.5 Update API spec or internal API docs if calls.py endpoint signatures changed

## 15. Redis Secondary Index Verification

- [ ] 15.1 Write integration test: session registered in Redis on create
- [ ] 15.2 Write integration test: session deregistered from Redis on remove
- [ ] 15.3 Test Redis unavailability graceful degradation (mock Redis failure)
- [ ] 15.4 Verify external systems can query Redis for "which process owns call X?"

## 16. Final Integration & Smoke Test

- [ ] 16.1 Start backend with new SessionRepository
- [ ] 16.2 Make a POST /calls request and verify session created and registered
- [ ] 16.3 Make a second concurrent call and verify two sessions coexist
- [ ] 16.4 Verify calls don't interfere with each other
- [ ] 16.5 Send SIGTERM to process and verify graceful shutdown drain

## 17. Code Review & Cleanup

- [ ] 17.1 Code review: SessionRepository for style, type hints, error handling
- [ ] 17.2 Code review: calls.py refactoring for full decoupling
- [ ] 17.3 Code review: test coverage report (verify >85% for SessionRepository)
- [ ] 17.4 Clean up debug logs or temporary code
- [ ] 17.5 Run full backend test suite (existing tests still pass)
