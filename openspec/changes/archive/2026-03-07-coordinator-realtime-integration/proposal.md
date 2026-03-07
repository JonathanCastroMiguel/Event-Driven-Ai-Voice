## Why

The Coordinator, TurnManager, AgentFSM, and Router exist and are fully tested, but they are completely disconnected from the live voice flow. The backend currently only proxies SDP signaling — all audio and events flow directly between browser and OpenAI with no server-side intelligence. Without this integration, the system cannot perform custom routing, policy-based responses, tool execution, or barge-in handling. This is the critical gap between "WebRTC works" and "the voice runtime works."

## What Changes

- Introduce a server-side WebSocket connection to OpenAI's Realtime API that runs alongside the browser's WebRTC connection, giving the backend access to transcription and speech events
- Translate OpenAI Realtime events (speech detection, transcriptions, response completion) into Coordinator EventEnvelopes
- Translate Coordinator output events (RealtimeVoiceStart, RealtimeVoiceCancel) into OpenAI Realtime API commands (response.create, response.cancel)
- Instantiate the full runtime actor stack (Coordinator, TurnManager, AgentFSM, ToolExecutor, Router) when a call session is created
- Tear down actors and close the server-side WebSocket when a call ends

## Capabilities

### New Capabilities

- `realtime-event-bridge`: Server-side bridge between OpenAI Realtime WebSocket API and the Coordinator. Translates OpenAI events to EventEnvelopes (input), and Coordinator output events to OpenAI API commands (output). Implements the existing `RealtimeClient` protocol.

### Modified Capabilities

- `webrtc-signaling`: Session creation now instantiates the full runtime actor stack (Coordinator, TurnManager, AgentFSM, ToolExecutor, Router) and opens the server-side Realtime WebSocket. Session termination tears down all actors.

## Impact

- **Backend code**: `calls.py` session lifecycle, new `realtime_event_bridge.py` module in `voice_runtime/`
- **Dependencies**: No new dependencies (httpx already available for WebSocket upgrade, or use websockets lib already in stack)
- **Configuration**: OpenAI API key already configured; may need `OPENAI_REALTIME_WS_URL` for the WebSocket endpoint
- **APIs**: No new HTTP endpoints; existing POST/DELETE /calls behavior changes (actors now start/stop)
- **Frontend**: No changes — browser still connects directly to OpenAI for audio and data channel events
- **Testing**: New unit tests for bridge, integration tests for full Coordinator-to-OpenAI flow
