## Why

The original voice architecture used aiortc on the backend to relay audio between the browser and OpenAI's Realtime API via WebSocket. This introduced unnecessary latency (audio transcoding, server-side Opus decode/encode, PCM resampling), complexity (aiortc + websockets dependencies), and instability (garbled transcriptions from incorrect audio format conversion). OpenAI's native WebRTC endpoint (`/v1/realtime/calls`) allows the browser to connect directly, eliminating the backend audio relay entirely.

## What Changes

- **BREAKING** Remove backend audio relay (aiortc, websockets, RealtimeBridge, OpenAIRealtimeProvider, AudioOutputTrack)
- **BREAKING** Remove client-side VAD (Silero ONNX/WASM) — OpenAI handles VAD server-side
- Simplify `calls.py` to a pure SDP proxy: receives browser's SDP offer, forwards to OpenAI, returns SDP answer
- Frontend connects directly to OpenAI via WebRTC for audio and data channel (`oai-events`)
- Frontend translates OpenAI data channel events to internal transcription format
- Remove ICE candidate endpoint (not needed with direct OpenAI connection)
- Remove backend dependencies: `aiortc`, `websockets`
- Remove frontend dependency: `@ricky0123/vad-web`
- Remove ONNX model files and WASM runtime assets from frontend

## Capabilities

### New Capabilities

- `openai-webrtc-sdp-proxy`: Backend SDP signaling proxy that forwards browser SDP offers to OpenAI Realtime WebRTC API and returns SDP answers, keeping the API key server-side

### Modified Capabilities

- `webrtc-signaling`: Simplified from full WebRTC relay (ICE, aiortc peer connection, audio bridge) to pure SDP proxy (3 endpoints: create, offer, delete)
- `voice-client-ui`: Frontend now manages direct OpenAI WebRTC connection, data channel event handling, and OpenAI event translation (transcriptions, speech detection) instead of relying on backend-relayed events
- `openai-realtime-provider`: **REMOVED** — no longer needed; browser connects directly to OpenAI
- `realtime-voice-bridge`: **REMOVED** — no longer needed; no backend audio relay

## Impact

- **Backend API**: `/api/v1/calls/{id}/ice` endpoint removed; `/api/v1/calls/{id}/offer` now proxies to OpenAI instead of local aiortc
- **Backend dependencies**: aiortc and websockets removed from pyproject.toml
- **Frontend dependencies**: @ricky0123/vad-web removed from package.json
- **Frontend assets**: ~5MB of ONNX models and WASM runtime files deleted
- **Types**: `ControlOutMessage` (speech_started/speech_ended) removed — OpenAI handles VAD
- **Architecture gap**: Coordinator/TurnManager/AgentFSM are now disconnected from the voice flow; backend is only involved in SDP signaling, not in real-time event processing. Integration with the runtime is deferred to a future change.
