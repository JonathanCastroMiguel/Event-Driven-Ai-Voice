<!-- BEGIN_ENRICHED_USER_STORY -->
# Enriched User Story

design-linked: false
scope:
  backend: true
  frontend: false
source: Manual
reference: N/A

## Title
Typed Voice Client abstraction for multi-ingress support (starting with Browser WebRTC)

## Problem / Context
The current system has a `RealtimeClient` protocol (`realtime_client.py`) and a concrete `OpenAIRealtimeEventBridge` (`realtime_event_bridge.py`) that assumes browser WebSocket transport. While the Coordinator (`coordinator.py`) is already transport-agnostic—consuming generic `EventEnvelope` and emitting `RealtimeVoiceStart`/`RealtimeVoiceCancel` via callbacks—coupling remains high at the bridge and route layers (`calls.py`).

The platform needs to support multiple voice ingress types in a plug-and-play manner:
- Browser WebRTC (existing)
- VoIP/Asterisk via RabbitMQ (ready externally, publishing to queue)
- Future SIP providers

**Current State:**
- `RealtimeClient` protocol defines: `send_voice_start`, `send_voice_cancel`, `on_event`, `close`
- `OpenAIRealtimeEventBridge` is a concrete implementation hardcoded to FastAPI WebSocket + OpenAI event format
- Session creation in `calls.py` instantiates the bridge directly with no type selection mechanism
- Asterisk SIP trunk publishes inbound call events to RabbitMQ but has no backend consumer

## Desired Outcome
A formalized Voice Client abstraction that:
1. Defines client types as first-class entities (enum + metadata struct)
2. Evolves the existing protocol to include type awareness
3. Refactors the existing browser bridge to align with the new abstraction (zero behavior change)
4. Provides a factory pattern for client instantiation based on type
5. Extends the API contract to accept client type selection
6. Tracks client type in the database for analytics
7. Establishes the extension point for future VoIP implementation

The Coordinator remains unchanged—it already operates on generic events.

## Acceptance Criteria

### AC-1: VoiceClientType enum and metadata structures
- GIVEN the system needs to distinguish between ingress types
- WHEN defining client types
- THEN a `VoiceClientType` enum SHALL be created with values:
  - `BROWSER_WEBRTC`
  - `VOIP_ASTERISK`
- AND the enum SHALL be designed for future extensibility (additional types can be added without breaking changes)
- AND a `VoiceClientInfo` dataclass/model SHALL be created with fields:
  - `client_id: UUID` — unique identifier for this client instance
  - `client_type: VoiceClientType` — the type of ingress
  - `connected_at: int` — Unix timestamp (milliseconds) of connection establishment
  - `metadata: dict[str, Any]` — extensible metadata (e.g., `{"sip_caller_id": "+1234567890", "user_agent": "Mozilla/5.0..."}`)
- AND both SHALL be properly typed and serializable (JSON-compatible for API responses)

### AC-2: VoiceClient protocol evolution
- GIVEN the need for a type-aware client abstraction
- WHEN defining the protocol
- THEN the existing `RealtimeClient` protocol SHALL be evolved into `VoiceClient` with:
  - `@property client_type() -> VoiceClientType` — returns the client's type
  - `@property client_info() -> VoiceClientInfo` — returns full client metadata
  - Existing methods preserved: `send_voice_start`, `send_voice_cancel`, `on_event`, `close`
- AND the protocol SHALL remain transport-agnostic (no assumptions about WebSocket, RabbitMQ, etc.)

### AC-3: Browser bridge refactoring
- GIVEN the existing `OpenAIRealtimeEventBridge` implementation
- WHEN refactoring to align with the new protocol
- THEN it SHALL:
  - Implement the `VoiceClient` protocol
  - Set `client_type = VoiceClientType.BROWSER_WEBRTC`
  - Populate `client_info` with appropriate metadata (e.g., WebSocket connection time, user-agent if available)
  - Optionally be renamed to `BrowserRealtimeVoiceClient` for clarity (rename if it improves readability)
- AND there SHALL be zero behavior changes (pure abstraction alignment)
- AND all existing tests SHALL pass without modification (proves no regression)

### AC-4: VoiceClientFactory
- GIVEN the need to instantiate clients based on type
- WHEN creating client instances
- THEN a `VoiceClientFactory` class or function SHALL be implemented that:
  - Accepts `client_type: VoiceClientType` and configuration parameters
  - Returns a `VoiceClient` implementation for supported types
  - For `BROWSER_WEBRTC`: returns the refactored browser client
  - For `VOIP_ASTERISK`: raises `NotImplementedError` with message: `"VoIP/Asterisk client not yet implemented (see US-XXX)"`
  - Raises clear errors for unknown/invalid types
- AND the factory SHALL be the single point of extension for new client types
- AND the factory SHALL be unit tested for all branches (supported, unsupported, invalid)

### AC-5: API surface extension
- GIVEN the need to support type selection at session creation
- WHEN defining the API contract
- THEN `POST /api/v1/calls` SHALL:
  - Accept an optional `client_type` field (string, e.g., `"browser_webrtc"`, `"voip_asterisk"`)
  - Default to `"browser_webrtc"` if not provided
  - Validate the provided type against supported values
  - Return HTTP 400 with a clear error message for unsupported types (e.g., `{"error": "Unsupported client type: voip_asterisk. Supported types: browser_webrtc"}`)
  - Pass the `client_type` to the factory for client instantiation
- AND the endpoint SHALL remain backward-compatible (existing clients without `client_type` continue to work)
- AND the OpenAPI spec (`api-spec.yml`) SHALL be updated to document the new field

### AC-6: Database tracking
- GIVEN the need to segment analytics by ingress type
- WHEN storing call session data
- THEN the `CallSession` entity SHALL:
  - Add a new field: `client_type: str` (stores the enum value as string, e.g., `"browser_webrtc"`)
  - Store the client type for every session
  - Be indexed if needed for analytics queries
- AND the Alembic migration SHALL be created to add the column with default value `"browser_webrtc"` for backward compatibility

### AC-7: Comprehensive testing
- GIVEN the refactored architecture
- WHEN validating the implementation
- THEN the following tests SHALL be implemented:

**Unit Tests:**
- `test_voice_client_protocol_compliance`: Verify the refactored browser client implements all protocol methods
- `test_voice_client_factory_supported_type`: Factory returns correct client for `BROWSER_WEBRTC`
- `test_voice_client_factory_unsupported_type`: Factory raises `NotImplementedError` for `VOIP_ASTERISK`
- `test_voice_client_factory_invalid_type`: Factory handles unknown types gracefully
- `test_voice_client_type_serialization`: Enum serializes to/from JSON correctly
- `test_voice_client_info_serialization`: `VoiceClientInfo` serializes correctly

**Integration Tests:**
- `test_coordinator_with_abstraction`: Coordinator processes events identically through the new abstraction (compare with baseline behavior)
- `test_api_client_type_default`: `POST /calls` works without `client_type` (defaults to browser)
- `test_api_client_type_unsupported`: `POST /calls` with unsupported type returns 400
- `test_db_client_type_stored`: Call sessions persist `client_type` correctly

## Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Protocol vs ABC | Protocol (typing.Protocol) | Runtime duck typing, no inheritance required, aligns with existing `RealtimeClient` |
| Enum storage in DB | String (serialized enum value) | Readable in DB queries, compatible with ORMs, extensible |
| Factory pattern | Static factory function or class | Single extension point, testable, clear separation of concerns |
| Coordinator changes | Zero | Already event-driven and transport-agnostic |
| Default client type | `browser_webrtc` | Backward compatibility, existing deployments continue to work |

## Architecture Impact

**No changes required:**
- `Coordinator` — already consumes generic `EventEnvelope`
- `TurnManager`, `AgentFSM`, `ToolExecutor` — downstream of Coordinator, type-agnostic
- `EventBus`, `EventEnvelope` — remain generic
- Event routing logic — operates on event types, not client types

**Changes required:**
- `src/voice_runtime/voice_client.py` (new) — protocol definition, enum, info struct
- `src/voice_runtime/voice_client_factory.py` (new) — factory implementation
- `src/voice_runtime/realtime_event_bridge.py` — refactor to implement `VoiceClient`
- `src/api/routes/calls.py` — accept `client_type` parameter, use factory
- `src/domain/models.py` — add `client_type` to `CallSession`
- `alembic/versions/XXXX_add_client_type_to_call_session.py` (new) — migration
- `ai-specs/specs/api-spec.yml` — document `client_type` field

## Dependencies
- Existing `RealtimeClient` protocol
- Existing `OpenAIRealtimeEventBridge` implementation
- Existing `Coordinator`, `TurnManager`, `AgentFSM`
- SQLAlchemy/Alembic for DB migration
- FastAPI for API endpoint modification

## Non-Functional Requirements
- Zero regression: All existing tests must pass
- Zero performance impact: Abstraction is compile-time only
- Backward compatibility: Existing API consumers continue to work
- Clear error messages: Unsupported types fail fast with actionable errors

## Out of Scope
- **VoIP/Asterisk bridge implementation** — consuming RabbitMQ, translating Asterisk events → `EventEnvelope` (separate user story)
- **Coordinator scaling** (separate user story)
- **Router/inference scaling**
- **Audio transcoding/format conversion**
- **Load balancing across client types**

## Constraints / Notes
- The `EventSource` enum in `events.py` remains `REALTIME` for now (both client types feed the Realtime API)
- The VoIP bridge (future US) will implement `VoiceClient` with `client_type = VOIP_ASTERISK`, consume from RabbitMQ, and translate Asterisk events into `EventEnvelope`
- This US is **pure refactoring + extension point** — no new runtime behavior except API validation
- All code must follow `backend-standards.mdc`
- TDD: Write failing tests first, implement to pass
<!-- END_ENRICHED_USER_STORY -->
