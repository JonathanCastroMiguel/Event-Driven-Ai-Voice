## Context

The voice runtime has a `RealtimeVoiceProvider` Protocol with four methods: `send_audio`, `receive_transcription`, `send_text_for_tts`, and `close`. The `RealtimeVoiceBridge` already consumes any provider through this Protocol. Currently only `StubVoiceProvider` exists, returning canned responses.

The OpenAI Realtime API provides bidirectional streaming STT and TTS over a single WebSocket (`wss://api.openai.com/v1/realtime`). The model `gpt-4o-mini-realtime-preview` is selected for lowest latency since the heavy inference is handled by separate agents — this provider only handles speech transcription and voice synthesis.

## Goals / Non-Goals

**Goals:**
- Implement `OpenAIRealtimeProvider` with minimum possible latency at every layer
- Stream audio to/from OpenAI with zero buffering beyond single frames
- Auto-select provider based on `OPENAI_API_KEY` presence
- Keep `StubVoiceProvider` as fallback for testing without API key

**Non-Goals:**
- Multiple simultaneous STT/TTS providers
- Provider hot-swapping during an active call
- OpenAI Realtime API function calling / tool use (Coordinator handles this separately)
- Audio format negotiation (fixed at PCM16 24kHz, OpenAI's native format)

## Decisions

### D1: Single persistent WebSocket per call

**Choice:** One WebSocket connection per call, opened on provider init, closed on provider close.

**Alternatives considered:**
- **Shared WebSocket pool across calls:** Lower connection overhead but adds multiplexing complexity and cross-call failure blast radius. Not worth it for MVP concurrency levels.
- **Per-request HTTP (non-streaming):** Would require accumulating audio chunks, destroying latency.

**Rationale:** OpenAI Realtime API is designed for persistent connections. One WebSocket per call maps 1:1 with the `RealtimeVoiceProvider` lifecycle. Connection setup cost (~100ms) is paid once at call start, then all frames flow with zero overhead.

### D2: Audio format — PCM16 at 24kHz

**Choice:** Send and receive audio as base64-encoded PCM16 at 24kHz (OpenAI's native format).

**Alternatives considered:**
- **Opus pass-through:** OpenAI Realtime API does not accept Opus directly.
- **PCM16 at 16kHz + server-side resample:** Extra processing step, adds latency.

**Rationale:** The WebRTC bridge already decodes Opus to PCM via aiortc. We resample from aiortc's output sample rate to 24kHz using a lightweight linear resampler. OpenAI returns PCM16 24kHz which we pass back to the bridge for the WebRTC audio track.

### D3: Fire-and-forget audio sends, async event reader

**Choice:** `send_audio` writes to the WebSocket immediately (no await on response). A background task reads all incoming WebSocket messages and dispatches them to internal queues.

**Rationale:** Decoupling send and receive eliminates head-of-line blocking. Audio frames are sent as fast as they arrive from WebRTC (~20ms intervals). The reader task processes transcription events and TTS audio independently. This is the lowest-latency pattern for full-duplex streaming.

### D4: Provider selection via factory function

**Choice:** A `create_voice_provider()` factory in `realtime_provider.py` that returns `OpenAIRealtimeProvider` if `OPENAI_API_KEY` is set, otherwise `StubVoiceProvider`.

**Alternatives considered:**
- **Config enum (`VOICE_PROVIDER=openai|stub`):** More explicit but unnecessary complexity when the key presence is sufficient.
- **Dependency injection container:** Over-engineered for two providers.

**Rationale:** Simple, zero-config for developers. If you have the key, you get real audio. If not, stubs work. The factory is called in `calls.py` when creating the bridge during SDP offer handling.

### D5: WebSocket library — `websockets`

**Choice:** Use the `websockets` library for the async WebSocket client.

**Alternatives considered:**
- **`aiohttp` WebSocket client:** Already not in deps; `websockets` is lighter and purpose-built.
- **`httpx` WebSocket:** httpx doesn't support WebSockets natively.

**Rationale:** `websockets` is the standard async WebSocket library for Python. Pure asyncio, minimal overhead, well-maintained.

### D6: Transcription delivery via asyncio.Queue

**Choice:** The WebSocket reader task pushes `TranscriptionEvent` objects to an `asyncio.Queue`. `receive_transcription()` yields from this queue.

**Rationale:** Clean producer-consumer separation. The queue decouples the WebSocket message parsing rate from the bridge's consumption rate. Queue is unbounded (backpressure is handled by the WebSocket itself). The `receive_transcription()` async iterator runs as long as the provider is alive.

### D7: TTS audio delivery via asyncio.Queue

**Choice:** When `send_text_for_tts` is called, it sends a `response.create` message to OpenAI and yields audio frames from a dedicated TTS queue. The WebSocket reader routes `response.audio.delta` messages to this queue.

**Rationale:** Same pattern as STT. The caller gets an async iterator that yields audio frames as they arrive. A sentinel value (`None`) signals stream completion. This allows the bridge to push frames to the WebRTC track immediately, frame by frame.

## API Contract (OpenAI Realtime WebSocket)

### Connection
```
wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview
Headers: Authorization: Bearer <OPENAI_API_KEY>
         OpenAI-Beta: realtime=v1
```

### Send audio frame
```json
{"type": "input_audio_buffer.append", "audio": "<base64 PCM16 24kHz>"}
```

### Commit audio (trigger transcription)
```json
{"type": "input_audio_buffer.commit"}
```

### Request TTS response
```json
{"type": "response.create", "response": {"modalities": ["audio", "text"], "instructions": "<prompt>"}}
```

### Receive transcription
```json
{"type": "conversation.item.input_audio_transcription.completed", "transcript": "..."}
```

### Receive TTS audio
```json
{"type": "response.audio.delta", "delta": "<base64 PCM16 24kHz>"}
{"type": "response.audio.done"}
```

## Risks / Trade-offs

- **[WebSocket connection reliability]** Network issues can drop the WebSocket mid-call. → Mitigation: Log disconnection, emit `voice_generation_error` event, let Coordinator handle graceful degradation. No automatic reconnect for MVP (would complicate state).
- **[24kHz resample overhead]** aiortc outputs at 48kHz; resampling to 24kHz adds CPU. → Mitigation: Simple decimation (take every 2nd sample) is exact for 48→24kHz, zero-allocation with numpy slicing. ~0.1ms per frame.
- **[Base64 encoding overhead]** PCM frames are base64-encoded for the WebSocket JSON protocol. → Mitigation: Unavoidable with OpenAI's API format. Encoding a 20ms frame (~960 bytes) takes <0.01ms.
- **[OpenAI API latency variance]** Transcription and TTS latency depend on OpenAI's servers. → Mitigation: We minimize our own overhead to near-zero; report OpenAI latency in debug telemetry.
- **[API key in memory]** The API key is held in the Settings singleton. → Mitigation: Standard for server-side secrets. Not logged, not exposed via API.

## Open Questions

1. **Server-side VAD vs client-side only?** OpenAI Realtime API has built-in turn detection. Currently we use client-side Silero VAD. We could let OpenAI handle VAD via `input_audio_buffer.commit` on server-detected silence. Decision: keep client-side VAD for now (lower latency, already implemented), revisit if needed.
