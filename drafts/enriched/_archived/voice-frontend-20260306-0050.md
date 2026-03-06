<!-- BEGIN_ENRICHED_USER_STORY -->
# Enriched User Story

design-linked: false
scope:
  backend: true
  frontend: true
source: Notion
reference: https://www.notion.so/31a72bde208c800ea684dd70bca68b99

## Title
Voice FrontEnd — Browser-based voice client for runtime testing

## Problem / Context
The voice runtime architecture (Coordinator, TurnManager, AgentFSM, Router) is fully implemented and tested with unit/e2e tests using mocks, but there is no way to test the full pipeline end-to-end with real audio from a browser. A web-based frontend is needed to validate the architecture with real voice interactions before building the VoIP integration. This is the first integration point between the frontend and the voice runtime backend.

## Desired Outcome
A browser-based voice client that:
1. Captures microphone audio and streams it continuously to the backend via WebRTC
2. Uses client-side VAD to signal speech boundaries to the Coordinator
3. Connects to a Realtime Voice API for streaming STT/TTS
4. Plays back agent responses in real-time through the speaker
5. Shows human/agent transcription with input/output animations
6. Provides an optional debug mode for real-time system telemetry

## Acceptance Criteria

### Frontend (FE)

#### AC-FE-1: Microphone capture and WebRTC streaming
- GIVEN the user grants microphone permission
- WHEN audio is captured by the browser
- THEN it SHALL be streamed continuously via WebRTC using Opus codec (paquetes every ~20ms)
- AND the frontend overhead SHALL be < 5ms total (VAD ~1-3ms + Opus encode ~2-3ms)

#### AC-FE-2: Client-side VAD signaling
- GIVEN the audio stream is active
- WHEN Silero VAD (WASM) detects speech start or end
- THEN it SHALL signal `speech_started` / `speech_ended` to the backend within ~1-3ms of detection
- AND the audio stream SHALL continue flowing regardless of VAD state (VAD only signals, does not gate audio)

#### AC-FE-3: Real-time transcription display
- GIVEN the STT service is transcribing
- WHEN partial or final transcriptions arrive
- THEN they SHALL be displayed in real-time in the UI
- AND both human transcription (input) and agent transcription (output) SHALL be visible

#### AC-FE-4: Audio playback
- GIVEN the agent generates a TTS response
- WHEN audio chunks arrive via WebRTC
- THEN the browser SHALL start playback immediately (streaming, not buffered)
- AND a speaker animation SHALL indicate active output

#### AC-FE-5: Input/output animations
- GIVEN the call is active
- WHEN the user speaks, a microphone animation SHALL indicate active input
- WHEN the agent speaks, a speaker animation SHALL indicate active output

#### AC-FE-6: Debug mode (toggleable)
- GIVEN debug mode is enabled via a UI toggle
- WHEN the system is processing
- THEN the following SHALL be displayed in real-time:
  - User speech duration (start to end)
  - Turn text: active turn and previous turns (loaded top-to-bottom)
  - FSM status (current state of AgentFSM)
  - Turn management time (TurnManager processing duration)
  - Agent processing time with Route A and Route B details
  - Recent events (loaded top-to-bottom, most recent first)
- AND debug mode SHALL NOT add measurable latency when disabled
- AND debug data SHALL be delivered via a separate data channel or WebSocket (not on the audio path)

#### AC-FE-7: Microphone permission handling
- GIVEN the user has not yet granted microphone access
- WHEN the app loads or the user initiates a call
- THEN it SHALL request microphone permission via MediaDevices API
- AND if denied, it SHALL show a clear fallback UX explaining how to enable it

#### AC-FE-8: Visual design
- Light mode with neutral colors
- Minimal, lightweight design
- No visual elements that could add rendering latency

### Backend (BE)

#### AC-BE-1: Session creation endpoint
- GIVEN a client wants to start a voice call
- WHEN `POST /calls` is called
- THEN it SHALL create a CallSession, return `call_id`, and initiate WebRTC signaling (SDP offer/answer)

#### AC-BE-2: WebRTC signaling
- GIVEN a call session exists
- WHEN the frontend sends an SDP offer
- THEN the backend SHALL respond with an SDP answer and establish the WebRTC connection
- AND ICE candidate exchange SHALL be handled (STUN/TURN configuration)

#### AC-BE-3: Realtime Voice API integration
- GIVEN WebRTC audio is flowing from the browser
- WHEN audio arrives at the backend
- THEN it SHALL be forwarded to the Realtime Voice API for streaming STT
- AND STT transcriptions SHALL be fed into the Coordinator as `transcript_final` events
- AND agent response text SHALL be sent to the Realtime Voice API for streaming TTS
- AND TTS audio SHALL be streamed back to the browser via WebRTC

#### AC-BE-4: VAD signal handling
- GIVEN the frontend sends a `speech_started` or `speech_ended` signal
- WHEN the backend receives it
- THEN it SHALL create the corresponding EventEnvelope and dispatch it to the Coordinator

#### AC-BE-5: Debug data endpoint
- GIVEN debug mode is enabled on the frontend
- WHEN system events occur (turns, routing decisions, FSM transitions, voice events)
- THEN telemetry data SHALL be pushed to the frontend via a data channel or secondary WebSocket
- AND this SHALL NOT impact the audio pipeline latency

#### AC-BE-6: Docker deployment
- GIVEN the full stack (frontend + backend)
- WHEN `docker compose up` is run
- THEN the system SHALL be fully operational with frontend accessible on a browser port

## Technical Decisions (pre-approved, latency-optimized)

| Decision | Choice | Rationale |
|---|---|---|
| Protocol browser-backend | WebRTC | UDP transport, no head-of-line blocking, native echo cancellation/noise suppression, adaptive jitter buffer |
| Audio format | Opus | Native WebRTC codec, zero transformation, ~20ms frames, hardware-accelerated in browsers |
| VAD | Client-side (Silero WASM) | Detection at source, no network RTT for speech boundary detection (~1-3ms inference) |
| STT | Realtime Voice API (streaming) | Transcribes while user speaks, no end-of-utterance wait |
| TTS | Realtime Voice API (streaming) | Browser starts playback before agent finishes generating |
| Session management | REST + WebRTC | POST /calls creates session, WebRTC SDP offer/answer for media |
| Audio flow | Continuous stream | Audio flows always, VAD only signals boundaries — no chunk accumulation |

## Audio Flow Diagram

```
Browser (mic)
  -> Web Audio API captures PCM
  -> Silero VAD (WASM): signals speech_started / speech_ended (~1-3ms)
  -> WebRTC continuous stream (Opus, packets every ~20ms)
  -> Backend
      -> Realtime Voice API (streaming STT in parallel)
      -> Coordinator processes turn -> routing -> prompt -> response
      -> Realtime Voice API (streaming TTS back)
      -> WebRTC stream to browser
  -> Browser plays audio immediately (speaker)
```

## Dependencies
- Existing voice runtime: Coordinator, TurnManager, AgentFSM, Router, ToolExecutor
- Existing event system: EventEnvelope, EventBus
- Existing data model: CallSession, Turn, AgentGeneration, VoiceGeneration
- Realtime Voice API provider (to be selected/configured)
- STUN/TURN server for WebRTC NAT traversal

## Non-Functional Requirements
- Frontend overhead: < 5ms (VAD + codec)
- Internal pipeline latency: ~80us (measured in benchmarks)
- Typical turn latency (no LLM fallback): ~3-7ms (pipeline + embeddings)
- Debug mode: zero latency impact when disabled
- Browser support: modern browsers with WebRTC and Web Audio API support

## Out of Scope
- VoIP integration (future work)
- Mobile app
- Multi-language UI (English only for MVP)
- Call recording/playback
- Authentication/authorization (internal testing tool)

## Constraints / Notes
- Latency is the #1 priority in every technical decision
- This is for browser testing only; VoIP integration comes later
- Frontend stack: Next.js 15, Tailwind CSS 4, shadcn/ui (per project standards)
- Backend stack: Python 3.12, asyncio, FastAPI (per project standards)
- Docker Compose for deployment
<!-- END_ENRICHED_USER_STORY -->
