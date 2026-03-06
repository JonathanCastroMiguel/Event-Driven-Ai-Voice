## 1. [BE] WebRTC Signaling Endpoints

- [x] 1.1 [BE] Create `POST /calls` endpoint — creates CallSession, initializes Coordinator with actors, returns `call_id`
- [x] 1.2 [BE] Create `POST /calls/{call_id}/offer` endpoint — accepts SDP offer, creates aiortc RTCPeerConnection with audio transceiver (sendrecv) and DataChannels ("control", "debug"), returns SDP answer
- [x] 1.3 [BE] Create `POST /calls/{call_id}/ice` endpoint — adds ICE candidates to peer connection
- [x] 1.4 [BE] Create `DELETE /calls/{call_id}` endpoint — closes peer connection, cleans up Coordinator and actors
- [x] 1.5 [BE] Add STUN/TURN configuration from environment variables (`STUN_SERVERS`, `TURN_SERVERS`, `TURN_USERNAME`, `TURN_CREDENTIAL`) with Google STUN default
- [x] 1.6 [BE] Add peer connection disconnect detection — auto-cleanup when browser tab closes

## 2. [BE] RealtimeVoiceProvider Protocol

- [x] 2.1 [BE] Define `RealtimeVoiceProvider` Protocol — `send_audio(frame)`, `receive_transcription() -> AsyncIterator`, `send_text_for_tts(text) -> AsyncIterator[bytes]`, `close()`
- [x] 2.2 [BE] Implement stub `RealtimeVoiceProvider` for testing — returns canned transcriptions and silent audio frames

## 3. [BE] RealtimeVoiceBridge

- [x] 3.1 [BE] Create `RealtimeVoiceBridge` class implementing `RealtimeClient` Protocol — constructor takes aiortc peer connection and `RealtimeVoiceProvider`
- [x] 3.2 [BE] Implement audio forwarding — receive Opus frames from WebRTC audio track, decode to PCM16 if needed, forward to `RealtimeVoiceProvider.send_audio()`
- [x] 3.3 [BE] Implement STT → EventEnvelope — listen to `RealtimeVoiceProvider.receive_transcription()`, create `transcript_final` EventEnvelopes, dispatch via `on_event` callback
- [x] 3.4 [BE] Implement VAD signal handling — parse `speech_started`/`speech_ended` JSON from "control" DataChannel, create EventEnvelopes, dispatch to Coordinator
- [x] 3.5 [BE] Implement `send_voice_start` — send response text to `RealtimeVoiceProvider.send_text_for_tts()`, stream audio frames back to WebRTC audio track, emit `voice_generation_completed` when done
- [x] 3.6 [BE] Implement `send_voice_cancel` — stop active TTS stream immediately, cease sending audio frames
- [x] 3.7 [BE] Implement transcription forwarding — send transcription events to browser via "control" DataChannel as JSON

## 4. [BE] Debug Event Emission

- [x] 4.1 [BE] Add debug callback registration to Coordinator — optional callback for debug events, no-op when None
- [x] 4.2 [BE] Emit debug events from Coordinator — turn updates, FSM state changes, routing decisions, latency measurements (only when debug callback is set)
- [x] 4.3 [BE] Wire debug events in RealtimeVoiceBridge — forward Coordinator debug events to "debug" DataChannel as JSON, handle `debug_enable`/`debug_disable` from "control" DataChannel

## 5. [BE] Docker Configuration

- [x] 5.1 [BE] Add aiortc dependency to backend `pyproject.toml`
- [x] 5.2 [BE] Update Docker Compose with frontend service (Next.js) and backend service, configure networking

## 6. [FE] Project Setup

- [x] 6.1 [FE] Initialize Next.js 15 app in `frontend/` with TypeScript, Tailwind CSS 4, shadcn/ui
- [x] 6.2 [FE] Add dependencies: `@ricky0123/vad-web` (Silero VAD WASM)
- [x] 6.3 [FE] Create Dockerfile for frontend (multi-stage build: install → build → serve)

## 7. [FE] WebRTC Connection Manager

- [x] 7.1 [FE] Create `useVoiceSession` hook — manages call lifecycle: `POST /calls` → SDP exchange → ICE → connection established → cleanup on end
- [x] 7.2 [FE] Handle RTCPeerConnection states — detect "connected", "failed", "disconnected", trigger appropriate UI updates and cleanup
- [x] 7.3 [FE] Create DataChannel handlers — "control" channel for VAD signals + transcriptions, "debug" channel for telemetry

## 8. [FE] Audio Capture and VAD

- [x] 8.1 [FE] Create `useMicrophone` hook — request microphone permission via MediaDevices API, add audio track to RTCPeerConnection, handle permission denial with fallback UX
- [x] 8.2 [FE] Create `useVAD` hook — initialize Silero VAD (WASM), detect speech start/end, send signals on "control" DataChannel with timestamps

## 9. [FE] Voice UI Components

- [x] 9.1 [FE] Create `VoiceSession` component — orchestrates connection, wraps `useVoiceSession` + `useMicrophone` + `useVAD` hooks, provides start/end call buttons
- [x] 9.2 [FE] Create `MicAnimation` component — visual indicator for microphone active/idle state based on VAD
- [x] 9.3 [FE] Create `SpeakerAnimation` component — visual indicator for agent audio playback active/idle state
- [x] 9.4 [FE] Create `TranscriptionPanel` component — displays human and agent transcriptions from DataChannel messages
- [x] 9.5 [FE] Create main page layout — compose VoiceSession, MicAnimation, SpeakerAnimation, TranscriptionPanel with light/neutral design

## 10. [FE] Debug Panel

- [x] 10.1 [FE] Create `DebugPanel` component — toggleable overlay, lazy-loaded, renders turn history, FSM status, routing details, event log, latency metrics
- [x] 10.2 [FE] Create `useDebugChannel` hook — listens to "debug" DataChannel, parses messages, manages debug state (turns, fsm, routing, events, latencies)
- [x] 10.3 [FE] Add debug toggle button to main layout — sends `debug_enable`/`debug_disable` on control DataChannel

## 11. [TEST] Backend Tests

- [x] 11.1 [TEST] Unit tests for WebRTC signaling endpoints — session creation, SDP exchange, ICE, termination, error cases
- [x] 11.2 [TEST] Unit tests for RealtimeVoiceBridge — audio forwarding, STT→EventEnvelope, VAD signal dispatch, TTS streaming, voice cancellation
- [x] 11.3 [TEST] Unit tests for debug event emission — Coordinator debug callback, event types, no overhead when disabled
- [x] 11.4 [TEST] Integration test for full pipeline — browser stub → WebRTC → Bridge → Coordinator → Bridge → response

## 12. [TEST] Frontend Tests

- [x] 12.1 [TEST] Component tests for VoiceSession, MicAnimation, SpeakerAnimation, TranscriptionPanel (Vitest + Testing Library)
- [x] 12.2 [TEST] Hook tests for useVoiceSession, useMicrophone, useVAD, useDebugChannel (Vitest)

## 13. [E2E] End-to-End Test

- [x] 13.1 [E2E]
