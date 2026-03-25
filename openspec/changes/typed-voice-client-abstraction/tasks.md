## 1. Core Abstraction Layer

- [x] 1.1 Create `src/voice_runtime/voice_client.py` with VoiceClientType enum (BROWSER_WEBRTC, VOIP_ASTERISK)
- [x] 1.2 Add VoiceClientInfo dataclass with client_id, client_type, connected_at, metadata fields
- [x] 1.3 Define VoiceClient protocol (typing.Protocol) with client_type, client_info properties and existing methods
- [x] 1.4 Write unit tests for VoiceClientType enum serialization (to/from JSON)
- [x] 1.5 Write unit tests for VoiceClientInfo creation and JSON serialization
- [x] 1.6 Write unit tests for VoiceClient protocol type checking compliance

## 2. Factory Implementation

- [x] 2.1 Create `src/voice_runtime/voice_client_factory.py` with create_voice_client function
- [x] 2.2 Implement factory to return browser client for BROWSER_WEBRTC type
- [x] 2.3 Implement factory to raise NotImplementedError for VOIP_ASTERISK with clear message
- [x] 2.4 Add error handling for invalid/unknown client types
- [x] 2.5 Write unit test: factory returns correct client for BROWSER_WEBRTC
- [x] 2.6 Write unit test: factory raises NotImplementedError for VOIP_ASTERISK
- [x] 2.7 Write unit test: factory handles invalid types gracefully

## 3. Bridge Refactoring

- [x] 3.1 Refactor OpenAIRealtimeEventBridge to implement VoiceClient protocol
- [x] 3.2 Add client_type property returning VoiceClientType.BROWSER_WEBRTC
- [x] 3.3 Add client_info property with UUID, timestamp, and WebSocket metadata
- [x] 3.4 Generate stable client_id (UUID) at bridge instantiation
- [x] 3.5 Populate metadata with user-agent from WebSocket headers (when available)
- [x] 3.6 Write unit test: bridge implements client_type property correctly
- [x] 3.7 Write unit test: bridge implements client_info property with all fields
- [x] 3.8 Write unit test: client_id remains stable across multiple accesses
- [x] 3.9 Write unit test: different bridge instances have different client_ids
- [x] 3.10 Run existing bridge unit tests to verify zero regression

## 4. API Layer Integration

- [x] 4.1 Update POST /api/v1/calls request schema to accept optional client_type string field
- [x] 4.2 Add validation logic to check client_type against supported types (default: "browser_webrtc")
- [x] 4.3 Implement error response (HTTP 400) for unsupported client_type with clear message
- [x] 4.4 Modify calls.py to use VoiceClientFactory instead of direct bridge instantiation
- [x] 4.5 Pass client_type from API request to factory
- [x] 4.6 Write integration test: API call without client_type defaults to browser_webrtc
- [x] 4.7 Write integration test: API call with client_type="browser_webrtc" succeeds
- [x] 4.8 Write integration test: API call with client_type="voip_asterisk" returns HTTP 400
- [x] 4.9 Write integration test: API call with invalid client_type format returns HTTP 400

## 5. Database Schema & Domain Model

- [x] 5.1 Add client_type field to CallSession entity (String type)
- [x] 5.2 Create Alembic migration: add client_type column (VARCHAR, nullable=False, server_default="browser_webrtc")
- [x] 5.3 Test migration on development database (verify existing rows get default value)
- [x] 5.4 Write downgrade migration to remove client_type column
- [x] 5.5 Write unit test: CallSession includes client_type field
- [x] 5.6 Write integration test: CallSession with client_type persists correctly to database
- [x] 5.7 Write integration test: new sessions created after migration have correct client_type

## 6. Documentation Updates

- [x] 6.1 Update ai-specs/specs/api-spec.yml to document client_type field in POST /api/v1/calls
- [x] 6.2 Document supported values, default behavior, and error responses in API spec
- [x] 6.3 Add comments/docstrings to VoiceClient protocol explaining extension pattern
- [x] 6.4 Add docstring to VoiceClientFactory explaining how to add new client types

## 7. Comprehensive Testing & Validation

- [x] 7.1 Write integration test: Coordinator processes events identically through refactored bridge
- [x] 7.2 Run full backend test suite (unit + integration + e2e)
- [x] 7.3 Verify all existing tests pass without modification (zero regression requirement)
- [x] 7.4 Verify type checking passes (mypy/pyright) for all new code
- [x] 7.5 Run performance benchmarks to confirm zero performance impact
- [x] 7.6 Test backward compatibility: existing API clients (without client_type) work unchanged

## 8. Deployment Preparation

- [x] 8.1 Review migration plan from design.md
- [x] 8.2 Test migration rollback scenario in development
- [x] 8.3 Verify factory returns browser client by default (backward compatibility)
- [x] 8.4 Confirm all acceptance criteria from specs are met
- [x] 8.5 Update backend README if deployment steps changed
