## Context

The voice runtime is fully operational with a `StubRealtimeClient` for testing. The `RealtimeClient` Protocol defines the integration boundary: `send_voice_start`, `send_voice_cancel`, `on_event`, and `close`. The Coordinator consumes `EventEnvelope` messages and emits `RealtimeVoiceStart` / `RealtimeVoiceCancel` output events. No real audio pipeline exists yet.

The frontend stack (Next.js 15, Tailwind CSS 4, shadcn/ui) is defined in standards but has no application code. This change creates the first real integration between browser audio and the voice runtime.

## Goals / Non-Goals

**Goals:**
- Connect real browser audio to the existing Coordinator pipeline via WebRTC
- Implement a `RealtimeClient` backed by a Realtime Voice API (streaming STT/TTS)
- Provide a minimal voice UI for end-to-end testing
- Provide a debug panel for observing runtime behavior in real-time
- Minimize latency at every layer

**Non-Goals:**
- VoIP/telephony integration (future)
- Production-grade authentication or multi-tenancy
- Call recording or playback
- Mobile support
- Custom STT/TTS models — use Realtime Voice API provider as-is

## Decisions

### D1: WebRTC library — `aiortc` (Python)

**Choice:** Use `aiortc` for server-side WebRTC.

**Alternatives considered:**
- **mediasoup (Node.js SFU):** Would require a separate Node.js service, adding latency and operational complexity.
- **Janus/Kurento (media server):** Full-featured but heavy for MVP; overkill when we only need 1:1 browser-to-server connections.
- **WebSocket with raw audio:** Simpler but TCP-based (head-of-line blocking), no native echo cancellation, higher latency.

**Rationale:** `aiortc` is pure Python, integrates natively with asyncio, and handles SDP/ICE/DTLS/SRTP. Single-process deployment with the existing FastAPI backend. Suitable for MVP with low concurrent call counts.

### D2: Signaling via REST endpoints

**Choice:** Use REST endpoints for WebRTC signaling (not a dedicated signaling WebSocket).

- `POST /calls` → creates CallSession, returns `call_id`
- `POST /calls/{call_id}/offer` → receives SDP offer, returns SDP answer
- `POST /calls/{call_id}/ice` → exchanges ICE candidates
- `DELETE /calls/{call_id}` → ends call, cleans up resources

**Rationale:** Simpler than a signaling WebSocket for 1:1 connections. The signaling phase is short-lived (< 1 second). Once WebRTC is established, all media and data flows over the peer connection.

### D3: Realtime Voice Bridge architecture

**Choice:** A `RealtimeVoiceBridge` class that implements the `RealtimeClient` Protocol and acts as the glue between WebRTC audio tracks and the Realtime Voice API.

```
Browser ←→ aiortc (WebRTC) ←→ RealtimeVoiceBridge ←→ Realtime Voice API
                                      ↕
                                 Coordinator
```

The bridge:
1. Receives Opus audio frames from the WebRTC audio track
2. Forwards them to the Realtime Voice API for streaming STT
3. Receives transcription events → creates `EventEnvelope` (`transcript_final`) → dispatches to Coordinator
4. Receives `RealtimeVoiceStart` from Coordinator → sends response text to Realtime Voice API for TTS
5. Receives TTS audio stream → pushes audio frames to the WebRTC audio track back to browser

**Rationale:** The bridge implements the existing `RealtimeClient` Protocol, so the Coordinator needs zero changes for basic operation. The Coordinator already handles `speech_started`, `transcript_final`, `voice_generation_completed` — the bridge just produces real ones instead of stubs.

### D4: VAD signals via WebRTC DataChannel

**Choice:** The browser sends `speech_started` / `speech_ended` JSON messages over a WebRTC DataChannel (not over REST).

**Rationale:** DataChannel uses the same UDP transport as audio — lowest possible latency for signaling. No HTTP overhead. The bridge receives these messages and creates the corresponding `EventEnvelope` for the Coordinator.

### D5: Debug data via separate DataChannel

**Choice:** A second WebRTC DataChannel (`debug`) for telemetry data.

**Rationale:** Keeps debug data off the audio path entirely. The Coordinator already emits structured logs (structlog) and metrics (Prometheus). The bridge taps into these and forwards relevant events to the debug DataChannel when the frontend enables debug mode. Zero overhead when disabled (no listener registered).

### D6: Frontend component architecture

**Choice:** Three main components in the Next.js app:

1. **`VoiceSession`** — manages WebRTC connection lifecycle, audio tracks, DataChannels
2. **`VoiceUI`** — mic/speaker animations, transcription display (client component)
3. **`DebugPanel`** — toggleable overlay consuming debug DataChannel events (client component)

**Rationale:** Clean separation. `VoiceSession` handles all WebRTC complexity. UI components are pure consumers of state. Debug panel is lazy-loaded and conditionally rendered.

### D7: Realtime Voice API provider abstraction

**Choice:** Define a `RealtimeVoiceProvider` Protocol in the bridge layer:

```python
class RealtimeVoiceProvider(Protocol):
    async def send_audio(self, frame: bytes) -> None: ...
    async def receive_transcription(self) -> AsyncIterator[TranscriptionEvent]: ...
    async def send_text_for_tts(self, text: str) -> AsyncIterator[bytes]: ...
    async def close(self) -> None: ...
```

**Rationale:** The specific Realtime Voice API provider (OpenAI Realtime, Deepgram, etc.) is not yet selected. The Protocol allows swapping providers without changing the bridge. MVP implementation can start with any provider.

## API Contracts

### POST /calls
```json
// Request: empty body
// Response 201:
{
  "call_id": "uuid",
  "status": "created"
}
```

### POST /calls/{call_id}/offer
```json
// Request:
{ "sdp": "<SDP offer string>", "type": "offer" }
// Response 200:
{ "sdp": "<SDP answer string>", "type": "answer" }
```

### POST /calls/{call_id}/ice
```json
// Request:
{ "candidate": "<ICE candidate string>", "sdpMid": "0", "sdpMLineIndex": 0 }
// Response 204
```

### DELETE /calls/{call_id}
```json
// Response 204 (no body)
```

### DataChannel: "control" (JSON messages)
```json
// Browser → Backend:
{ "type": "speech_started", "ts": 1234567890 }
{ "type": "speech_ended", "ts": 1234567890 }
{ "type": "debug_enable" }
{ "type": "debug_disable" }
```

### DataChannel: "debug" (JSON messages, backend → browser)
```json
{ "type": "turn_update", "turn_id": "uuid", "text": "...", "state": "finalized" }
{ "type": "fsm_state", "state": "generating", "agent_generation_id": "uuid" }
{ "type": "routing", "route_a": "domain", "route_a_confidence": 0.92, "route_b": "billing" }
{ "type": "event", "event_type": "human_turn_finalized", "ts": 1234567890 }
{ "type": "latency", "metric": "turn_processing_ms", "value": 4.2 }
```

## Risks / Trade-offs

- **[aiortc maturity]** `aiortc` is less battle-tested than browser WebRTC implementations. → Mitigation: MVP only needs 1:1 connections; if issues arise, can fall back to a WebSocket+PCM approach with minimal bridge changes.
- **[Opus codec mismatch]** The Realtime Voice API may expect PCM16 or a different format than Opus. → Mitigation: `aiortc` can decode Opus to PCM internally; the bridge handles transcoding if needed.
- **[STUN/TURN in Docker]** NAT traversal can be tricky in containerized environments. → Mitigation: For local dev/testing, use host networking or a local TURN server (coturn). Document the configuration.
- **[Realtime Voice API provider lock-in]** MVP picks one provider. → Mitigation: `RealtimeVoiceProvider` Protocol allows swapping without bridge changes.
- **[Debug panel overhead]** Even with a separate DataChannel, high-frequency events could consume CPU. → Mitigation: Throttle debug events (max 10/s per type), batch updates on the frontend side.

## Open Questions

1. **Which Realtime Voice API provider?** OpenAI Realtime API, Deepgram, or Google Cloud Speech Streaming? Needs to support both streaming STT and streaming TTS. Decision can be deferred behind the `RealtimeVoiceProvider` Protocol.
2. **TURN server for production?** coturn self-hosted vs managed (Twilio TURN)? Not needed for local Docker testing (same network), but required for remote access.
