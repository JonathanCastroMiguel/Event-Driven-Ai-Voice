## Why

The voice runtime currently has high coupling at the bridge and route layers, with a concrete `OpenAIRealtimeEventBridge` hardcoded to browser WebSocket transport. The Coordinator is already transport-agnostic, but adding new ingress types (VoIP/Asterisk via RabbitMQ, future SIP providers) requires formalization of the Voice Client as a first-class abstraction. This enables plug-and-play support for multiple ingress types without modifying the Coordinator or core runtime logic.

## What Changes

- Define `VoiceClientType` enum (BROWSER_WEBRTC, VOIP_ASTERISK) and `VoiceClientInfo` metadata struct for type identification and tracking
- Evolve `RealtimeClient` protocol into `VoiceClient` protocol with type awareness (`client_type`, `client_info` properties)
- Refactor `OpenAIRealtimeEventBridge` to implement the new `VoiceClient` protocol with zero behavior changes
- Implement `VoiceClientFactory` for type-based client instantiation (BROWSER_WEBRTC supported, VOIP_ASTERISK raises NotImplementedError)
- Extend `POST /api/v1/calls` to accept optional `client_type` field with validation
- Add `client_type` column to `CallSession` entity for analytics segmentation
- Comprehensive testing: protocol compliance, factory resolution, API validation, Coordinator regression tests

## Capabilities

### New Capabilities

- `voice-client-abstraction`: VoiceClient protocol, VoiceClientType enum, VoiceClientInfo metadata struct, and VoiceClientFactory for multi-ingress type support

### Modified Capabilities

- `realtime-event-bridge`: Refactor to implement VoiceClient protocol with client_type = BROWSER_WEBRTC (zero behavior change, pure abstraction alignment)

## Impact

**Backend Code:**
- New: `src/voice_runtime/voice_client.py` (protocol, enum, info struct)
- New: `src/voice_runtime/voice_client_factory.py` (factory implementation)
- Modified: `src/voice_runtime/realtime_event_bridge.py` (implement VoiceClient protocol)
- Modified: `src/api/routes/calls.py` (accept client_type parameter, use factory)
- Modified: `src/domain/models.py` (add client_type field to CallSession)

**Database:**
- Alembic migration: add `client_type` column to `call_sessions` table with default "browser_webrtc"

**API:**
- `POST /api/v1/calls` accepts optional `client_type` field (backward-compatible, defaults to "browser_webrtc")
- OpenAPI spec (`ai-specs/specs/api-spec.yml`) updated to document new field

**Tests:**
- New unit tests: protocol compliance, factory resolution, enum serialization
- New integration tests: API validation, database persistence, Coordinator regression

**No Impact:**
- Coordinator, TurnManager, AgentFSM, ToolExecutor remain unchanged (already event-driven)
- EventBus, EventEnvelope remain generic
- Zero performance impact (compile-time abstraction only)
