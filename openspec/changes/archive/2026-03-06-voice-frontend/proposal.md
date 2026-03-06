## Why

The voice runtime (Coordinator, TurnManager, AgentFSM, Router) is fully built and tested with mocks, but there is no way to test the full pipeline end-to-end with real audio from a browser. A web-based voice client is needed to validate the architecture with real voice interactions before building the VoIP integration.

## What Changes

- New WebRTC signaling and media pipeline connecting browser audio to the Coordinator
- New session creation endpoint (`POST /calls`) with WebRTC SDP offer/answer
- New Realtime Voice API integration (streaming STT/TTS) bridging browser audio and the Coordinator's event system
- New frontend voice client: microphone capture, client-side VAD (Silero WASM), streaming audio playback, real-time transcription display
- New debug mode overlay showing system telemetry (turns, FSM status, routing details, events) via a separate data channel
- Docker Compose configuration for full-stack deployment (frontend + backend)

## Capabilities

### New Capabilities

- `webrtc-signaling`: WebRTC session lifecycle — SDP offer/answer negotiation, ICE candidate exchange, STUN/TURN configuration, and `POST /calls` endpoint for session creation
- `realtime-voice-bridge`: Integration layer between WebRTC audio streams and the Coordinator — streaming STT feeding `transcript_final` events, streaming TTS from agent responses, VAD signal dispatch as EventEnvelopes
- `voice-client-ui`: Browser-based voice interface — microphone capture with Opus/WebRTC streaming, client-side Silero VAD, audio playback, input/output animations, real-time transcription display, microphone permission handling
- `debug-panel`: Toggleable debug overlay — turn history, FSM status, routing details (Route A/B), event log, latency metrics; delivered via separate data channel to avoid impacting audio latency

### Modified Capabilities

- `coordinator`: New integration point — Coordinator must accept events from the Realtime Voice Bridge (VAD signals mapped to `speech_started`/`speech_ended`, STT results mapped to `transcript_final`) and emit voice output commands back through the bridge

## Impact

- **Backend**: New modules for WebRTC signaling (aiortc or similar), Realtime Voice API client, and bridge layer connecting to existing Coordinator
- **Frontend**: New Next.js app with WebRTC, Web Audio API, Silero VAD WASM, and shadcn/ui components
- **APIs**: New `POST /calls` endpoint, WebRTC signaling protocol, debug data channel/WebSocket
- **Dependencies**: aiortc (Python WebRTC), @ricky0123/vad-web (Silero WASM), Realtime Voice API SDK
- **Infrastructure**: Docker Compose updated with frontend service, STUN/TURN server configuration
