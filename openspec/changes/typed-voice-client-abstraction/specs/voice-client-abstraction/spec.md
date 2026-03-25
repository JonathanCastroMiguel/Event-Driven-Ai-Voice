## ADDED Requirements

### Requirement: VoiceClientType enum for ingress type identification
The system SHALL define a `VoiceClientType` enum with values `BROWSER_WEBRTC` and `VOIP_ASTERISK` to distinguish between ingress types. The enum SHALL be designed for future extensibility (additional types can be added without breaking changes).

#### Scenario: Enum values defined
- **WHEN** the VoiceClientType enum is imported
- **THEN** it SHALL contain `BROWSER_WEBRTC` and `VOIP_ASTERISK` as valid values

#### Scenario: Enum is JSON-serializable
- **WHEN** a VoiceClientType value is serialized to JSON
- **THEN** it SHALL produce a string representation (e.g., `"browser_webrtc"`, `"voip_asterisk"`)

#### Scenario: Enum is deserializable from string
- **WHEN** a string value `"browser_webrtc"` is deserialized
- **THEN** it SHALL produce `VoiceClientType.BROWSER_WEBRTC`

### Requirement: VoiceClientInfo metadata structure
The system SHALL define a `VoiceClientInfo` dataclass with fields: `client_id` (UUID), `client_type` (VoiceClientType), `connected_at` (int, Unix timestamp in milliseconds), and `metadata` (dict[str, Any]). The `metadata` field SHALL support extensible client-specific data (e.g., SIP caller ID, browser user-agent).

#### Scenario: VoiceClientInfo creation with all fields
- **WHEN** a VoiceClientInfo is created with client_id, type, timestamp, and metadata
- **THEN** all fields SHALL be accessible as properties

#### Scenario: VoiceClientInfo is JSON-serializable
- **WHEN** a VoiceClientInfo instance is serialized to JSON
- **THEN** `client_id` SHALL be a string UUID, `client_type` SHALL be a string, `connected_at` SHALL be an integer, and `metadata` SHALL be a dict

#### Scenario: Metadata supports extensible fields
- **WHEN** VoiceClientInfo is created with metadata containing `{"sip_caller_id": "+1234567890"}`
- **THEN** the metadata dict SHALL contain the custom field and be accessible

### Requirement: VoiceClient protocol definition
The system SHALL define a `VoiceClient` protocol (typing.Protocol) that extends the existing client contract with type awareness. The protocol SHALL include: `client_type` property returning VoiceClientType, `client_info` property returning VoiceClientInfo, and preserve existing methods: `send_voice_start`, `send_voice_cancel`, `on_event`, `close`. The protocol SHALL remain transport-agnostic (no assumptions about WebSocket, RabbitMQ, etc.).

#### Scenario: Protocol defines required properties
- **WHEN** a class implements VoiceClient
- **THEN** it SHALL implement `client_type` property returning VoiceClientType
- **AND** it SHALL implement `client_info` property returning VoiceClientInfo

#### Scenario: Protocol preserves existing contract
- **WHEN** a class implements VoiceClient
- **THEN** it SHALL implement `send_voice_start`, `send_voice_cancel`, `on_event`, and `close` methods

#### Scenario: Protocol enables duck typing
- **WHEN** a class implements all VoiceClient methods without explicit inheritance
- **THEN** type checkers SHALL recognize it as implementing VoiceClient

### Requirement: VoiceClientFactory for type-based instantiation
The system SHALL implement a `VoiceClientFactory` class or function that accepts `client_type` (VoiceClientType) and configuration parameters, and returns a VoiceClient implementation. For `BROWSER_WEBRTC`, the factory SHALL return the browser client implementation. For `VOIP_ASTERISK`, the factory SHALL raise `NotImplementedError` with message: `"VoIP/Asterisk client not yet implemented (see US-XXX)"`. For unknown types, the factory SHALL raise a clear error.

#### Scenario: Factory returns browser client for BROWSER_WEBRTC
- **WHEN** `create_voice_client(VoiceClientType.BROWSER_WEBRTC, **config)` is called
- **THEN** the factory SHALL return a VoiceClient implementation with `client_type = BROWSER_WEBRTC`

#### Scenario: Factory raises NotImplementedError for VOIP_ASTERISK
- **WHEN** `create_voice_client(VoiceClientType.VOIP_ASTERISK, **config)` is called
- **THEN** the factory SHALL raise `NotImplementedError` with message containing "VoIP/Asterisk client not yet implemented"

#### Scenario: Factory raises error for invalid type
- **WHEN** an invalid client_type is provided
- **THEN** the factory SHALL raise a clear error indicating the type is not recognized

#### Scenario: Factory accepts extensible configuration
- **WHEN** the factory is called with additional keyword arguments in `**config`
- **THEN** it SHALL pass configuration to the appropriate client implementation

### Requirement: API endpoint accepts client_type parameter
The `POST /api/v1/calls` endpoint SHALL accept an optional `client_type` field (string, e.g., `"browser_webrtc"`, `"voip_asterisk"`). If not provided, it SHALL default to `"browser_webrtc"`. The endpoint SHALL validate the provided type against supported values. For unsupported types, it SHALL return HTTP 400 with error message: `{"error": "Unsupported client type: <type>. Supported types: browser_webrtc"}`.

#### Scenario: API defaults to browser_webrtc when client_type omitted
- **WHEN** `POST /api/v1/calls` is called without `client_type` field
- **THEN** the session SHALL be created with `client_type = "browser_webrtc"`

#### Scenario: API accepts browser_webrtc explicitly
- **WHEN** `POST /api/v1/calls` is called with `client_type = "browser_webrtc"`
- **THEN** the session SHALL be created with `client_type = "browser_webrtc"`

#### Scenario: API rejects unsupported client types
- **WHEN** `POST /api/v1/calls` is called with `client_type = "voip_asterisk"`
- **THEN** the endpoint SHALL return HTTP 400 with error message listing supported types

#### Scenario: API validates client_type format
- **WHEN** `POST /api/v1/calls` is called with invalid `client_type` format (e.g., uppercase, unknown value)
- **THEN** the endpoint SHALL return HTTP 400 with clear validation error

### Requirement: CallSession entity stores client_type
The `CallSession` entity SHALL include a `client_type` field (string) that stores the enum value as a string (e.g., `"browser_webrtc"`). The field SHALL be persisted to the database and indexed if needed for analytics queries.

#### Scenario: CallSession includes client_type field
- **WHEN** a CallSession is created
- **THEN** it SHALL have a `client_type` field of type string

#### Scenario: Client type is persisted to database
- **WHEN** a CallSession with `client_type = "browser_webrtc"` is saved
- **THEN** the database record SHALL contain `client_type = "browser_webrtc"`

#### Scenario: Existing sessions have default client_type
- **WHEN** database migration adds client_type column
- **THEN** existing rows SHALL have `client_type = "browser_webrtc"` as default value

### Requirement: Database migration for client_type column
An Alembic migration SHALL add a `client_type` column to the `call_sessions` table with type `VARCHAR`, nullable=False, and server default `"browser_webrtc"` for backward compatibility with existing rows.

#### Scenario: Migration adds client_type column
- **WHEN** the migration is applied
- **THEN** the `call_sessions` table SHALL have a `client_type` column

#### Scenario: Migration sets default for existing rows
- **WHEN** the migration is applied to a database with existing call_sessions
- **THEN** all existing rows SHALL have `client_type = "browser_webrtc"`

#### Scenario: Migration is reversible
- **WHEN** the migration is rolled back
- **THEN** the `client_type` column SHALL be removed from `call_sessions`

### Requirement: Coordinator remains unchanged
The Coordinator, TurnManager, AgentFSM, ToolExecutor, EventBus, and EventEnvelope SHALL remain unchanged. No modifications to the core event-driven runtime are required.

#### Scenario: Coordinator processes events identically
- **WHEN** events are emitted through the new VoiceClient abstraction
- **THEN** the Coordinator SHALL process them identically to before the refactor

#### Scenario: Event types remain unchanged
- **WHEN** the VoiceClient emits EventEnvelope instances
- **THEN** the event types and payloads SHALL match the existing contract

### Requirement: Zero behavior change for existing clients
All existing functionality SHALL behave identically after the refactor. Existing tests SHALL pass without modification. The change is pure abstraction alignment with no runtime behavior changes.

#### Scenario: Existing API calls continue to work
- **WHEN** an existing client calls `POST /api/v1/calls` without `client_type`
- **THEN** the call SHALL succeed and create a session with browser WebRTC client

#### Scenario: All existing tests pass
- **WHEN** the full test suite is run after implementation
- **THEN** all existing unit, integration, and e2e tests SHALL pass without modification

#### Scenario: No performance regression
- **WHEN** call sessions are created and processed
- **THEN** performance metrics SHALL be identical to pre-refactor baseline (abstraction is compile-time only)
