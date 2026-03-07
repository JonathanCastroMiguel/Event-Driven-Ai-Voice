## Context

The voice runtime was built and unit-tested with mocks, but first real browser testing revealed that the OpenAI Realtime WebRTC API requires a specific session initialization flow that differs from the original implementation. Several wiring issues also prevented events from reaching the Coordinator.

## Goals / Non-Goals

**Goals:**
- Fix session configuration so transcription and auto-response control work correctly
- Wire the full runtime actor stack (Coordinator, TurnManager, AgentFSM, Bridge) into the call lifecycle
- Enable bidirectional event forwarding between browser and Coordinator via WebSocket
- Replace fasttext with a lighter language detection library

**Non-Goals:**
- Changing the Coordinator's routing logic or event handling (covered by `coordinator-realtime-integration`)
- Frontend UI changes beyond WebSocket event forwarding
- Persistence or database changes

## Decisions

### Decision 1: Two-step SDP exchange with ephemeral key

**Choice**: Split the SDP proxy into two HTTP calls: (1) `POST /v1/realtime/sessions` with session config (model, transcription, turn_detection) returns an ephemeral key, (2) `POST /v1/realtime` with the ephemeral key for SDP exchange.

**Rationale**: OpenAI's Realtime WebRTC API requires this two-step flow. The `/sessions` endpoint creates server-side config and returns a short-lived client key. The SDP exchange then uses this key instead of the server API key, which is never exposed to the browser.

### Decision 2: One-time session.update via WebSocket on connection

**Choice**: Send a `session.update` message through the WebSocket → frontend buffer → data channel immediately after WebSocket connection. This configures `input_audio_transcription: {model: "whisper-1"}` and `turn_detection: {type: "server_vad", create_response: false}`.

**Rationale**: Testing revealed that the `/v1/realtime/sessions` endpoint does NOT reliably apply `create_response: false` or `input_audio_transcription` settings. Without the explicit `session.update`, OpenAI auto-responds to every speech end (bypassing Coordinator) and transcription events never fire. The session.update is sent once at connection time, not per turn.

### Decision 3: Runtime actors instantiated per call in POST /calls

**Choice**: `POST /calls` creates the full actor stack (Coordinator, TurnManager, AgentFSM, ToolExecutor, Bridge) and stores them in `CallSessionEntry`. Events are wired bidirectionally: Bridge→Coordinator (input) and Coordinator→Bridge (output via callback).

**Rationale**: Each call needs its own isolated actor stack with per-call state. Wiring at creation time ensures the pipeline is ready before the first event arrives.

### Decision 4: langid replaces fasttext for language detection

**Choice**: Use `langid` library instead of `fasttext` for hot-path language detection.

**Rationale**: langid is ~0.02-0.04ms per call, supports 97 languages, has no NumPy dependency, and is a pure Python package. fasttext required a large model file download and NumPy. Detection accuracy is sufficient for routing purposes.

### Decision 5: Policies fallback stubs for development

**Choice**: If `PoliciesRegistry` is not initialized at startup (e.g., missing router registry files), `calls.py` falls back to stub policies with basic instructions for each policy key.

**Rationale**: Prevents crashes during development when the full router registry isn't configured. Logs a warning (`policies_not_initialized_using_stubs`) so the issue is visible.

## Risks / Trade-offs

**[Session.update race condition]** → The session.update is sent via WebSocket before the data channel may be open. Mitigation: Frontend uses `sendOrBuffer` mechanism that queues messages until the data channel opens, then flushes.

**[Stub policies in production]** → If policies aren't loaded, stubs provide minimal functionality. Mitigation: Warning log alerts operators. Startup should fail-fast in production if router registry is missing.
