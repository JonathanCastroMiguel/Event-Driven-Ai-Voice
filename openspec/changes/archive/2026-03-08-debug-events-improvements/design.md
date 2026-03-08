## Context

The debug pipeline timeline works for direct routes but has critical timing gaps. Testing with real calls revealed: (1) the backend measures up to `response.done` (model finished generating) but audio playback continues ~3s longer on the frontend — the backend has no visibility into actual audio playback, (2) `generation_start`, `generation_finish`, and `route_result(direct)` are emitted retroactively at the same instant in `_on_voice_completed`, making them useless for timing, (3) timing data calculated in the bridge never reaches the Coordinator, (4) there's no way to distinguish router vs specialist `response.created` events, and (5) no `specialist_processing` event exists between `specialist_sent` and `specialist_ready`.

## Goals / Non-Goals

**Goals:**
- Close the timing gap: frontend emits audio playback events and sends them to the backend for a complete server-side trace
- Fix retroactive event emission so debug timeline accurately reflects when things happen
- Pass bridge timing data (`send_to_created_ms`, `created_to_done_ms`) through to debug events
- Distinguish router vs specialist response events in the debug stream
- Validate with real delegate route calls
- Ensure timing is monotonic and accurate across the full pipeline (Coordinator↔Bridge↔Frontend)

**Non-Goals:**
- Persisting debug events to a database (future work)
- Redesigning the debug panel layout
- Changing the FSM or routing architecture
- Changing backend event names (only display labels in frontend)

## Decisions

### 1. Pass bridge timing metrics through EventEnvelope payload

**Decision**: Include `send_to_created_ms` and `created_to_done_ms` in the `response_created` and `voice_generation_completed` EventEnvelope payloads respectively. The Coordinator reads these from `envelope.payload` and passes them as extra fields in `_send_debug()`.

**Rationale**: The bridge already calculates these values (lines 241, 276-277 in `realtime_event_bridge.py`) but only logs them. The Coordinator currently ignores the payload of `response_created`. By forwarding these metrics, the frontend can show actual network RTT and model inference time in the debug boxes.

**Alternative considered**: Having the Coordinator calculate its own timestamps at event receipt — less accurate because it includes event queue delay, not true bridge-to-OpenAI timing.

### 2. Tag response events with sequence context (router vs specialist)

**Decision**: Add a `response_source` field to `response_created` and `voice_generation_completed` EventEnvelope payloads. Values: `"router"` (initial model-as-router response) or `"specialist"` (specialist agent response). The bridge tracks this via a `_current_response_source` field set when it sends `response.create`.

**Rationale**: The Coordinator receives `response_created` for both router and specialist responses through the same handler (line 265). Without context, the `model_processing` debug event is ambiguous. With `response_source`, the Coordinator can emit `model_processing` with extra `source` field, and the frontend can optionally show which model is processing.

**Implementation**: In `send_voice_start()`, the bridge sets `_current_response_source = "router"`. When dispatching a specialist prompt, it sets `_current_response_source = "specialist"`. On `response.created`, it includes `response_source` in the envelope payload.

### 3. Frontend emits audio playback events, sent to backend for complete trace

**Decision**: The frontend detects `response.audio.delta` (first chunk) and `response.audio.done` from the OpenAI WebRTC stream. On first audio chunk, it emits `audio_playback_start`; on audio done, it emits `audio_playback_end`. These events are sent to the backend via the existing WebSocket as `client_debug_event` messages containing `{type: "client_debug_event", stage: "audio_playback_start"|"audio_playback_end", turn_id, ts}`. The backend WebSocket handler routes these to the Coordinator, which integrates them into the debug pipeline via `_send_debug()`.

**Rationale**: The backend has zero visibility into when the user actually starts/stops hearing audio. `response.done` only signals that OpenAI finished generating — audio playback continues for seconds after. Real testing showed a 2.5s backend timeline vs 5.6s user-perceived time. The ~3s gap is entirely audio playback. By having the frontend report these events back, the server-side trace becomes complete and accurate for future analysis/persistence.

**Implementation**: Frontend tracks a `_firstAudioReceived` flag per response, reset on `response.created`. On first `response.audio.delta`, sends `client_debug_event` with `stage: "audio_playback_start"`. On `response.audio.done`, sends `stage: "audio_playback_end"`. Backend WebSocket handler identifies `client_debug_event` type and forwards to Coordinator. Coordinator calls `_send_debug()` with the stage name to integrate into the debug trace with proper `delta_ms`/`total_ms`.

### 4. Fix direct route: emit `route_result` at `response.done`, remove retroactive generation events

**Decision**: Emit `route_result(direct)` when `response.done` arrives for a router response with no routing action. Remove the retroactive `generation_start` emission from the backend — `generation_start` is now `audio_playback_start` from the frontend. `generation_finish` is now `audio_playback_end` from the frontend. The `_on_voice_completed` handler no longer emits `generation_start`; it only emits `generation_finish` as a fallback if no `audio_playback_end` was received.

**Rationale**: The old approach emitted `route_result` + `generation_start` + `generation_finish` all at the same instant in `_on_voice_completed`, making them useless for timing. Now `route_result` fires at the right time (model decided to respond directly), and audio timing comes from the frontend where it actually happens.

### 4. Emit `specialist_processing` from bridge response.created

**Decision**: When the bridge receives `response.created` for a specialist response (identified by `_current_response_source == "specialist"`), the Coordinator emits `_send_debug("specialist_processing")` instead of generic `model_processing`. This fills the gap between `specialist_sent` and `specialist_ready`.

**Rationale**: Currently the specialist sub-flow only has `specialist_sent` (before tool execution) and `specialist_ready` (after `response.done`). The actual model processing time of the specialist is invisible. With `specialist_processing`, the timeline shows: `specialist_sent → specialist_processing → specialist_ready`.

### 5. Emit `specialist_processing` from bridge response.created

**Decision**: When the bridge receives `response.created` for a specialist response (identified by `_current_response_source == "specialist"`), the Coordinator emits `_send_debug("specialist_processing")` instead of generic `model_processing`. This fills the gap between `specialist_sent` and `specialist_ready`.

**Rationale**: Currently the specialist sub-flow only has `specialist_sent` and `specialist_ready`. The actual model processing time of the specialist is invisible.

### 6. Keep voice_completed handler as fallback

**Decision**: Retain `route_result` + `generation_finish` fallback logic in `_on_voice_completed()`, gated with `_debug_route_result_emitted` flag. If the frontend `audio_playback_end` never arrives (e.g., barge-in, error), the backend still emits `generation_finish`.

**Rationale**: Belt-and-suspenders. The primary path uses frontend audio events. The fallback covers edge cases.

**Implementation**: `_debug_route_result_emitted: bool` flag, reset at `speech_start`, set when `route_result` is emitted.

## Risks / Trade-offs

- **[Risk] Bridge state for response_source could get out of sync** → Mitigation: Reset `_current_response_source` to `"router"` at each new `send_voice_start()`.
- **[Risk] Frontend audio events may not arrive (barge-in, disconnect)** → Mitigation: Backend fallback in `_on_voice_completed` emits `generation_finish` if no `audio_playback_end` was received.
- **[Risk] Duplicate events if both frontend and backend emit generation_finish** → Mitigation: `_debug_audio_playback_end_received` flag, checked before fallback emission.
- **[Risk] Clock skew between frontend and backend timestamps** → Mitigation: `delta_ms`/`total_ms` are always calculated server-side relative to `_debug_turn_start_ms`. The frontend sends its `ts` for reference but timing is recalculated on arrival.

### 7. Routing architecture: markers replaced with function calling

**Decision**: Replace `<<ROUTE:dept:summary>>` marker-based routing with OpenAI Realtime API function calling (`route_to_specialist` tool). The model speaks a natural filler AND calls the function simultaneously. Function calls are never vocalized.

**Rationale**: During debug validation with real calls, the marker-based approach revealed a fundamental flaw: text generation runs ahead of audio synthesis. By the time the marker is detected (in text), the TTS has already synthesized it into the audio buffer. Six approaches were explored and discarded before arriving at function calling — see `ai-specs/specs/architecture.md` section 5.3.1 for the full decision record.

**Impact on debug pipeline**: The `model_router_action` event now arrives via `response.function_call_arguments.done` instead of transcript parsing. The `voice_generation_completed` event for routing responses includes the filler transcript. The specialist `response.create` is built as a dict with embedded history and language instruction (same pattern as the router prompt), ensuring specialists respond in the customer's language.

### 8. Frontend cleanup: pure event forwarder

**Decision**: Remove all routing logic from the frontend (`use-voice-session.ts`). The frontend no longer detects markers, sends `response.cancel`, or mutes audio. It is a pure event forwarder between the OpenAI WebRTC data channel and the backend WebSocket.

**Rationale**: With function calling, routing is entirely handled by the backend. The frontend has no role in routing decisions. Removing this logic eliminates complexity, potential timing bugs, and latency from unnecessary processing.

## Open Questions

- Should `fill_silence` have a corresponding `fill_silence_cancelled` when specialist is ready and filler is stopped? (Low priority.)
- Future: persist complete debug traces to a stats database for latency analysis across calls.
