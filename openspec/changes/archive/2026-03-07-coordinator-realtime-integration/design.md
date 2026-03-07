## Context

The voice runtime actors (Coordinator, TurnManager, AgentFSM, Router, ToolExecutor) are fully implemented and tested but completely disconnected from the live voice flow. Currently:

- Browser connects directly to OpenAI via WebRTC (audio + data channel)
- Backend only proxies SDP signaling (3 endpoints)
- No runtime actors are instantiated during a call
- OpenAI handles all conversation logic autonomously

The Coordinator expects `EventEnvelope` inputs (speech_started, transcript_final, etc.) and produces output events (RealtimeVoiceStart, RealtimeVoiceCancel). A bridge is needed to translate between OpenAI Realtime API events and the Coordinator's event protocol.

## Goals / Non-Goals

**Goals:**

- Connect the Coordinator to the live OpenAI Realtime API so it controls routing, policies, and tool execution
- Instantiate the full actor stack per call session (Coordinator, TurnManager, AgentFSM, ToolExecutor, Router)
- Translate OpenAI events → Coordinator EventEnvelopes (input direction)
- Translate Coordinator output events → OpenAI Realtime API commands (output direction)
- Maintain the existing `RealtimeClient` protocol so unit tests with `StubRealtimeClient` continue to work

**Non-Goals:**

- Changing the frontend — browser still connects directly to OpenAI for audio
- Adding new HTTP endpoints — existing POST/DELETE /calls lifecycle is sufficient
- Implementing new Coordinator logic — all event handling already exists
- Server-side audio processing — audio stays in the browser ↔ OpenAI WebRTC path

## Decisions

### 1. Server-side WebSocket to OpenAI Realtime API

**Decision:** Open a persistent WebSocket connection from the backend to `wss://api.openai.com/v1/realtime?model={model}` for each active call, running alongside the browser's WebRTC connection.

**Why:** The browser's WebRTC data channel carries events for UI display, but the backend needs its own event stream to feed the Coordinator. A server-side WebSocket gives the backend full access to transcription events, speech detection, and the ability to send session configuration and response instructions.

**Alternatives considered:**
- *Browser relays events via WebSocket to backend:* Adds frontend complexity, extra network hop, and latency. Rejected because it contradicts the "no frontend changes" goal.
- *Shared data channel:* WebRTC data channels are browser-to-OpenAI only; the backend has no access to them after SDP proxy.

### 2. Implement RealtimeClient protocol with OpenAIRealtimeEventBridge

**Decision:** Create `OpenAIRealtimeEventBridge` in `backend/src/voice_runtime/realtime_event_bridge.py` that implements the existing `RealtimeClient` protocol. This class manages the WebSocket lifecycle, event translation, and bidirectional communication.

**Why:** The Coordinator already interacts with `RealtimeClient` via `send_voice_start()` and `send_voice_cancel()`. Implementing this protocol means the Coordinator works identically with the real bridge and the existing `StubRealtimeClient` in tests.

### 3. Event translation mapping

**Decision:** Map OpenAI Realtime events to Coordinator EventEnvelopes:

| OpenAI Event | Coordinator Event | Direction |
|---|---|---|
| `input_audio_buffer.speech_started` | `SpeechStarted` | OpenAI → Coordinator |
| `input_audio_buffer.speech_stopped` | `SpeechStopped` | OpenAI → Coordinator |
| `conversation.item.input_audio_transcription.completed` | `TranscriptFinal` | OpenAI → Coordinator |
| `response.done` | `VoiceGenerationCompleted` | OpenAI → Coordinator |
| `response.failed` | `VoiceGenerationError` | OpenAI → Coordinator |
| `RealtimeVoiceStart` (prompt) | `response.create` + `session.update` | Coordinator → OpenAI |
| `RealtimeVoiceCancel` | `response.cancel` | Coordinator → OpenAI |

### 4. Session configuration via session.update

**Decision:** When the Coordinator emits `RealtimeVoiceStart` with a prompt, the bridge sends a `session.update` to set instructions, followed by `response.create` to trigger the response. This gives the Coordinator full control over what the agent says.

**Why:** OpenAI's Realtime API uses `session.update` to configure system instructions and `response.create` to trigger a response. This is the standard pattern for server-controlled conversations.

### 5. Actor stack instantiation in session lifecycle

**Decision:** `POST /calls` creates `CallSessionEntry` with all runtime actors (Coordinator, TurnManager, AgentFSM, ToolExecutor, Router, EventBridge). `DELETE /calls/{call_id}` tears them all down. The EventBridge WebSocket opens during the SDP exchange (not at session creation) since we need the model to be configured first.

**Why:** Lazy WebSocket connection during SDP exchange avoids opening connections for sessions that never complete signaling. The SDP proxy already knows the model, so the WebSocket can connect to the same model.

**Alternative considered:**
- *Open WebSocket at POST /calls:* Wastes resources if SDP exchange never happens. Rejected.

### 6. Add websockets dependency

**Decision:** Add the `websockets` library for the server-side WebSocket connection to OpenAI.

**Why:** `httpx` does not support persistent WebSocket connections. The `websockets` library is the standard async WebSocket client for Python, lightweight, and well-maintained.

## Risks / Trade-offs

- **[Dual event streams]** Browser and backend both receive events from OpenAI (data channel + WebSocket). The browser uses events for UI only (transcription display, speaking indicators). The backend uses events for Coordinator logic. No conflict since they serve different purposes. → Mitigation: document clearly that browser events are display-only.

- **[WebSocket reliability]** If the server-side WebSocket drops, the Coordinator loses its event feed. → Mitigation: implement reconnection logic with exponential backoff; the browser's WebRTC connection remains stable independently.

- **[Latency overhead]** Adding Coordinator processing adds latency between user speech and agent response. → Mitigation: Coordinator processing is in-memory with asyncio, expected < 5ms for routing classification. The main latency is the LLM response itself, which OpenAI handles.

- **[Resource per call]** Each call now holds a WebSocket connection + full actor stack in memory. → Mitigation: the `max_concurrent_calls` setting already limits this. Actor stack is lightweight (no heavy allocations).
