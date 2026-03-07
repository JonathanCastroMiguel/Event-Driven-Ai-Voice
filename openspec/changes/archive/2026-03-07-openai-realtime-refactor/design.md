## Context

The voice runtime originally used a backend-mediated architecture: browser audio streamed via WebRTC to a backend aiortc peer connection, which decoded Opus to PCM, resampled, and forwarded audio to OpenAI's Realtime API via WebSocket. OpenAI responses flowed back through the same relay. This added ~20-50ms latency per hop, required complex audio format handling (stereo planar PCM → mono 24kHz), and produced garbled transcriptions due to naive downsampling (aliasing artifacts).

OpenAI launched a native WebRTC endpoint (`POST /v1/realtime/calls`) that accepts direct browser WebRTC connections. This eliminates the need for any server-side audio processing.

## Goals / Non-Goals

**Goals:**
- Eliminate all backend audio relay code and dependencies
- Achieve direct browser-to-OpenAI WebRTC audio path (zero backend latency on audio)
- Keep OpenAI API key server-side via SDP signaling proxy
- Maintain existing UI (transcription panel, speaking indicators, debug panel)
- Remove unused client-side VAD assets (~5MB of ONNX/WASM files)

**Non-Goals:**
- Integrating Coordinator/TurnManager/AgentFSM with the new direct connection (deferred)
- Custom routing or guardrails during voice sessions (requires runtime integration)
- Session configuration via OpenAI's `session.update` data channel events
- Ephemeral key support (would allow skipping the SDP proxy entirely)

## Decisions

### 1. Pure SDP Proxy over Ephemeral Keys

**Decision:** Backend proxies the SDP offer/answer exchange rather than generating ephemeral API keys.

**Rationale:** SDP proxy is simpler to implement and gives us a single point where we can later inject session configuration (system prompts, tools) before returning the SDP answer. Ephemeral keys would require the browser to call OpenAI directly for signaling too, losing backend control.

**Alternative considered:** Ephemeral key generation — simpler client code but no server-side control point for future runtime integration.

### 2. Inline Data Channel Listeners over useEffect

**Decision:** Wire WebRTC data channel event listeners inline inside `startSession()` instead of via `useEffect` with refs.

**Rationale:** React refs (`dcRef.current`) don't trigger re-renders, so a `useEffect` with `dcRef.current` as dependency never fires after the data channel is created. Inline wiring guarantees listeners are attached at creation time.

### 3. OpenAI Server-Side VAD over Client-Side Silero

**Decision:** Remove Silero VAD (ONNX model + WASM runtime) and rely on OpenAI's built-in VAD.

**Rationale:** OpenAI's `input_audio_buffer.speech_started/stopped` events provide the same functionality. Client-side VAD added ~3ms processing + ~5MB of assets with no benefit when audio goes directly to OpenAI.

### 4. Local Variable for Cleanup over State Closure

**Decision:** Use a local `newCallId` variable in `startSession()` for error cleanup instead of the React state `callId`.

**Rationale:** The `callId` state value captured in the `useCallback` closure is stale (always `null` at creation time). A local variable correctly references the newly created call ID for cleanup on failure.

### 5. httpx Content Mode for SDP Proxy

**Decision:** Use `content=body.sdp` with explicit `Content-Type: application/sdp` header instead of `data=` or `json=`.

**Rationale:** OpenAI's `/v1/realtime/calls` endpoint requires raw SDP text with `application/sdp` content type. Using `data={}` sends `application/x-www-form-urlencoded` which returns 400. Using `json=` would JSON-encode the SDP.

## Risks / Trade-offs

- **[Runtime disconnection]** The Coordinator, TurnManager, and AgentFSM no longer receive real-time events from voice sessions. The system currently operates as a raw "talk to GPT-4o" client without routing, guardrails, or conversation management. → Mitigation: Deferred to a separate change; current state is sufficient for end-to-end voice testing.

- **[API key in SDP proxy]** The backend must be available for SDP signaling. If the backend goes down, new calls cannot be established (existing calls continue since audio flows directly to OpenAI). → Mitigation: Acceptable for MVP; production would use ephemeral keys as fallback.

- **[No session configuration]** OpenAI receives no system prompt, tool definitions, or custom instructions — it uses its default behavior. → Mitigation: The SDP proxy endpoint is the natural injection point for `session.update` events in a future change.

- **[Accept 200 and 201]** OpenAI's SDP endpoint returns either 200 or 201 depending on the scenario. The proxy accepts both. → Mitigation: Explicitly check `resp.status_code not in (200, 201)` rather than `!= 200`.
