## Why

End-to-end testing with real browser audio revealed critical integration bugs: the voice model ignored user speech on turns 2+, Whisper forced Spanish-only transcription, and there was no ms-level timing instrumentation to diagnose latency issues in production.

## What Changes

- **Fix response.input override bug**: Move conversation history from `response.input` (which overrides OpenAI's native conversation context including committed audio) to `instructions` (system prompt text), so the model always hears the current turn's audio.
- **Enable multilingual Whisper**: Remove forced `language: "es"` from Whisper transcription config; let auto-detection handle English and Spanish.
- **Dynamic language routing**: Update router prompt to respond in the customer's language instead of defaulting to Spanish.
- **Add pipeline timing instrumentation**: Add ms-level timing at every Coordinator event handler and bridge round-trip measurement for latency debugging.
- **Refactor conversation buffer**: Replace simple list with TurnEntry model supporting async population of user_text/agent_text, and store agent transcripts from bridge responses.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `model-router`: History embedding strategy changed from `response.input` to `instructions` to preserve OpenAI native audio context.
- `coordinator`: Added ms-level timing instrumentation at every FSM transition and event handler. Updated fallback prompt to use instructions-based history.
- `realtime-event-bridge`: Added round-trip timing (send→created→done), agent transcript included in `voice_generation_completed` payload.
- `conversation-buffer`: Refactored to TurnEntry model with async field population and agent transcript storage.

## Impact

- **Backend code**: `model_router.py`, `coordinator.py`, `realtime_event_bridge.py`, `conversation_buffer.py`, `state.py`, `calls.py`, `router_prompt.yaml`
- **Tests**: Updated `test_model_router.py`, `test_coordinator.py`, `test_conversation_buffer.py` to match new behavior
- **APIs**: No API contract changes (internal event payloads only)
- **Breaking**: `RouterPromptBuilder.build_response_create()` no longer produces `response.input` — callers that relied on it must use `instructions` instead
