## Why

The debug pipeline timeline is functional for direct routes but has not been validated with real specialist (delegate) flows. The specialist sub-flow stages (`specialist_sent`, `specialist_processing`, `specialist_ready`) were implemented based on the Coordinator code but never tested with a live call that triggers a delegate route (e.g., asking about billing or sales). Additionally, the current debug event coverage may have gaps — some Coordinator transitions may not emit debug events, timing accuracy across the bridge boundary needs verification, and the frontend timeline rendering for delegate routes with real data hasn't been observed.

## What Changes

- **Frontend audio playback events**: The frontend detects `response.audio.delta` (first chunk = playback start) and `response.audio.done` (playback end) and emits `audio_playback_start` / `audio_playback_end` debug events. These are sent back to the backend via WebSocket as `client_debug_event` messages, where the Coordinator logs them and re-emits them through the debug pipeline for a complete server-side trace.
- **Fix retroactive direct route events**: Replace the retroactive `route_result(direct)` + `generation_start` + `generation_finish` emission in `_on_voice_completed` with properly timed events: `route_result(direct)` at `response.done` (no routing action), `generation_start` from frontend first audio chunk, `generation_finish` from frontend audio done.
- **Validate specialist debug flow end-to-end**: Trigger real delegate routes and verify the full specialist stage sequence: `route_result(delegate)` → `fill_silence` → `specialist_sent` → `specialist_processing` → `specialist_ready` → `generation_start` → `generation_finish`. Fix any gaps.
- **Bridge timing passthrough**: Pass `send_to_created_ms` and `created_to_done_ms` from bridge to Coordinator debug events. Distinguish router vs specialist `response.created` with `response_source` field.
- **Readable debug labels**: Frontend displays human-friendly labels for debug stages (e.g., "Direct Response" instead of "direct (direct)") without changing backend event names.
- **Edge cases**: Verify debug behavior for barge-in during specialist processing, consecutive delegate routes, failed specialist tool execution.
- **Routing refactor: markers → function calling**: During real-call validation, the marker-based routing (`<<ROUTE:...>>`) was found to leak routing metadata into TTS audio. After exploring six approaches (JSON, markers + cancel, muting), replaced with OpenAI Realtime API function calling (`route_to_specialist` tool). All marker detection and cancel logic removed from bridge and frontend. Frontend simplified to pure event forwarder. Specialist prompt rebuilt as dict with embedded history and language instruction.

## Capabilities

### New Capabilities

- `client-debug-events`: Frontend emits `audio_playback_start` and `audio_playback_end` events, sends them to the backend via WebSocket (`client_debug_event` message type), where the Coordinator integrates them into the debug trace for complete server-side logging.

### Modified Capabilities

- `coordinator`: Receive `client_debug_event` messages from frontend, integrate into debug pipeline. Fix direct route timing. Distinguish router vs specialist processing.
- `debug-panel`: Display bridge timing metrics, improve stage labels, render frontend audio playback events in timeline.
- `realtime-event-bridge`: Track `response_source`, pass timing metrics in EventEnvelope payloads. Handle function call routing via `response.function_call_arguments.done`.
- `model-router`: Replace marker-based routing with `route_to_specialist` function calling tool. Register tool at session level.
- `coordinator`: Build specialist prompt as dict with embedded conversation history and language instruction.

## Impact

- **Backend code**: `coordinator.py` (debug event emission fixes, client event ingestion), `realtime_event_bridge.py` (timing + source payloads), `call_session.py` or WebSocket handler (route `client_debug_event` to Coordinator)
- **Frontend code**: `use-voice-session.ts` (emit client debug events on audio playback), `turn-timeline.tsx` (labels, bridge timing display), `use-debug-channel.ts` (parse new fields and client events)
- **Tests**: Updated/new tests for bridge payloads, coordinator client event handling, frontend event emission
- **No new APIs** — uses existing WebSocket connection for client→backend debug events
