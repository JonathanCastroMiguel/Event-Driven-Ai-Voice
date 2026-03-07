## Why

During end-to-end testing of the voice runtime with a real browser, several critical issues were discovered that prevented the Coordinator pipeline from functioning. These are bugfixes and wiring changes needed to make the existing architecture work correctly with the OpenAI Realtime WebRTC API.

## What Changes

- **Two-step SDP exchange**: Replace single-step SDP proxy with the correct OpenAI Realtime flow: (1) `POST /v1/realtime/sessions` to create session config + ephemeral key, (2) `POST /v1/realtime` for SDP exchange using the ephemeral key. The `/sessions` endpoint configures transcription and turn detection.
- **One-time session.update for auto-response control**: Send a `session.update` message on WebSocket connection to configure `input_audio_transcription: {model: "whisper-1"}` and `turn_detection: {type: "server_vad", create_response: false}`. The `/sessions` endpoint does not reliably apply `create_response: false`, so an explicit `session.update` is required.
- **Runtime actor wiring in calls.py**: `POST /calls` now instantiates the full actor stack (Coordinator, TurnManager, AgentFSM, ToolExecutor, Bridge) and wires events bidirectionally: Bridge → Coordinator (input) and Coordinator → Bridge (output).
- **WebSocket event forwarding endpoint**: Add `WS /calls/{call_id}/events` for bidirectional event forwarding between the browser data channel and the Coordinator.
- **Bridge send_to_frontend made public**: Rename `_send_to_frontend` → `send_to_frontend` so the session.update can be sent from `calls.py`.
- **Language detection switch to langid**: Replace fasttext with langid for language detection (0.02-0.04ms, 97 languages, no NumPy dependency).
- **Turn manager debug logging**: Add `text=text` to `turn_finalized` log entry for debugging transcript content.
- **App startup wiring**: Add `set_shared_router_and_policies()` call in `main.py` lifespan to initialize shared singletons.
- **Policies fallback stubs**: Add stub `PoliciesRegistry` fallback in `calls.py` when policies aren't initialized yet, preventing crashes during development.

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
- `webrtc-signaling`: Two-step SDP exchange (sessions + SDP), runtime actor instantiation, WebSocket event forwarding endpoint, session.update on connection
- `realtime-event-bridge`: `send_to_frontend` method made public for external callers
- `coordinator`: Wired to receive events from Bridge and emit output events back to Bridge via callback

## Impact

- **Backend code**: `calls.py` (major refactor — actor wiring, two-step SDP, WebSocket endpoint), `main.py` (startup wiring), `realtime_event_bridge.py` (public method rename), `turn_manager.py` (logging), `language.py` (langid switch)
- **Dependencies**: Added `langid` to pyproject.toml, removed `fasttext` hot-path usage
- **API**: Added `WS /calls/{call_id}/events` endpoint. `POST /calls/{call_id}/offer` now uses two-step flow (same external contract).
- **Frontend**: `use-voice-session.ts` updated to connect to events WebSocket and forward data channel events
- **Tests**: `test_webrtc_signaling.py` needs update for two-step SDP mock
