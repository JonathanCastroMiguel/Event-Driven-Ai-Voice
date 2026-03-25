## Context

The voice runtime has a `RealtimeClient` protocol and a concrete `OpenAIRealtimeEventBridge` implementation that is tightly coupled to browser WebSocket transport. The Coordinator is already transport-agnostic (consumes generic `EventEnvelope` and emits callbacks), but the bridge layer and `calls.py` route instantiate the bridge directly without regard to ingress type.

**Current State:**
- `RealtimeClient` protocol: defines `send_voice_start`, `send_voice_cancel`, `on_event`, `close`
- `OpenAIRealtimeEventBridge`: concrete implementation for browser WebSocket + OpenAI Realtime API
- `calls.py`: directly instantiates the bridge with no type selection
- Asterisk SIP trunk publishes to RabbitMQ but has no consumer

**Constraints:**
- Zero regression: all existing tests must pass unchanged
- Zero performance impact: abstraction is compile-time only (typing.Protocol)
- Backward compatibility: existing API calls without `client_type` must continue to work
- TDD required: write failing tests first per project standards

**Stakeholders:**
- Platform operators need multi-ingress support (browser, VoIP, future SIP)
- Analytics team needs client type tracking for segmentation
- Future VoIP bridge implementation (separate user story) depends on this extension point

## Goals / Non-Goals

**Goals:**
- Formalize Voice Client as a typed, first-class abstraction with enum-based type identification
- Establish the extension point for new ingress types via factory pattern
- Refactor existing browser bridge with zero behavior change (pure abstraction alignment)
- Enable API clients to specify ingress type with validation
- Track client type in database for analytics

**Non-Goals:**
- Implementing VoIP/Asterisk bridge (separate user story)
- Modifying Coordinator, TurnManager, AgentFSM, or ToolExecutor (already transport-agnostic)
- Audio transcoding or format conversion between ingress types
- Load balancing or scaling strategies across client types
- Runtime client type switching (client type is set at session creation)

## Decisions

### Decision 1: Protocol over Abstract Base Class

**Choice:** Use `typing.Protocol` for `VoiceClient` (runtime structural typing)

**Rationale:**
- Aligns with existing `RealtimeClient` protocol pattern
- No inheritance required - implementations can be independent
- Duck typing enables flexibility for future integrations
- Zero runtime overhead (compile-time only)

**Alternatives Considered:**
- ABC (Abstract Base Class): Requires explicit inheritance, more rigid
- Interface class with NotImplementedError: Less idiomatic Python, no type checking

### Decision 2: Enum Storage as String in Database

**Choice:** Store `VoiceClientType` enum values as strings in PostgreSQL (e.g., `"browser_webrtc"`)

**Rationale:**
- Human-readable in database queries and logs
- Compatible with SQLAlchemy enum handling
- Extensible (new enum values don't require schema changes)
- Serializes naturally to JSON for API responses

**Alternatives Considered:**
- Integer codes: Less readable, requires mapping table
- JSON field: Overkill for simple enum, harder to index

### Decision 3: Factory Pattern for Client Instantiation

**Choice:** Static factory function `create_voice_client(client_type: VoiceClientType, **config) -> VoiceClient`

**Rationale:**
- Single extension point for new client types
- Clear separation of concerns (factory owns instantiation logic)
- Testable in isolation
- Fails fast with clear error messages for unsupported types

**Alternatives Considered:**
- Registry pattern: More complex, unnecessary for small number of types
- Direct conditional in `calls.py`: Violates Open/Closed Principle, hard to test
- Plugin system: Overkill for this phase, adds complexity

### Decision 4: Default client_type in API

**Choice:** `POST /api/v1/calls` defaults `client_type` to `"browser_webrtc"` if omitted

**Rationale:**
- Backward compatibility: existing clients continue to work without changes
- Safe assumption: all current sessions are browser-based
- Explicit opt-in for new ingress types reduces accidental misconfiguration

**Alternatives Considered:**
- Require `client_type` explicitly: Breaking change for existing clients
- Infer from request (e.g., headers): Fragile, hard to test, implicit behavior

### Decision 5: Zero Changes to Coordinator

**Choice:** Do not modify Coordinator, TurnManager, AgentFSM, or event system

**Rationale:**
- Already fully transport-agnostic (consumes generic `EventEnvelope`)
- Abstraction boundary is at the bridge layer, not the core runtime
- Reduces risk of regression in critical path
- Validates that existing design is sound

**Alternatives Considered:**
- Add client_type to EventEnvelope: Unnecessary coupling, increases payload size
- Client-specific event handlers in Coordinator: Violates single responsibility

### Decision 6: NotImplementedError for VOIP_ASTERISK

**Choice:** Factory raises `NotImplementedError` with message: `"VoIP/Asterisk client not yet implemented (see US-XXX)"`

**Rationale:**
- Clear signal that type is planned but not yet available
- Explicit message guides users to future work
- API validation prevents reaching this code path in production (400 error at API layer)

**Alternatives Considered:**
- Return None: Ambiguous, requires null checks downstream
- Raise generic ValueError: Less informative

## Risks / Trade-offs

### Risk: Breaking existing tests during refactor
**Mitigation:** Run full test suite after each change. Refactor is pure abstraction alignment - behavior must be identical. Add integration test that compares Coordinator behavior before/after.

### Risk: API clients send unsupported client_type
**Mitigation:** API layer validates against supported types (currently only `browser_webrtc`). Return HTTP 400 with clear error message listing supported types. Factory is never called with invalid types in production.

### Risk: Database migration fails on column add
**Mitigation:** Use `server_default="browser_webrtc"` in Alembic migration for existing rows. Test migration on staging with production-sized dataset. Rollback plan: drop column (safe - not used by existing code until deploy completes).

### Risk: Future client types have incompatible configuration needs
**Mitigation:** Factory accepts `**config` dict for extensibility. Each client type can define its own config schema. Document expected config shape in factory docstring per type.

### Trade-off: Enum must be updated for new client types
**Impact:** Adding a new ingress type requires code changes (enum + factory). Acceptable - new ingress types are rare, controlled deployments. Alternative (config-driven types) would sacrifice type safety.

### Trade-off: CallSession stores client_type as string vs foreign key
**Impact:** No referential integrity, but simpler schema and no join overhead for analytics queries. Enum validation in application layer ensures data quality.

## Migration Plan

**Pre-deployment:**
1. Merge code with feature flag disabled (factory always returns browser client)
2. Run Alembic migration in staging: `alembic upgrade head`
3. Verify existing sessions populate `client_type="browser_webrtc"` correctly
4. Run full test suite including e2e tests

**Deployment:**
1. Apply database migration in production (low risk - adds nullable column with default)
2. Deploy backend code (zero behavior change for existing clients)
3. Update API documentation (`api-spec.yml`)
4. Monitor logs for any `client_type` validation errors (should be zero)

**Rollback:**
- Code rollback: Standard rollback, no data migration required (column unused in old code)
- Schema rollback: `alembic downgrade -1` (safe - drops column)

**Post-deployment:**
- Verify all new sessions have `client_type="browser_webrtc"` in database
- Analytics team can begin segmenting by client_type (currently all browser)
- VoIP bridge implementation (next user story) can extend factory with `VOIP_ASTERISK` support

## Open Questions

None - design is fully specified. Implementation can proceed directly to tasks.
