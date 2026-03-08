## 1. Bridge: Response Source Tracking

- [x] 1.1 [BE] Add `_current_response_source: str` field to `RealtimeEventBridge.__init__`, default `"router"`
- [x] 1.2 [BE] Reset `_current_response_source` to `"router"` in `send_voice_start()`
- [x] 1.3 [BE] Set `_current_response_source = "specialist"` when dispatching specialist prompt
- [x] 1.4 [BE] Include `response_source` in `response_created` EventEnvelope payload
- [x] 1.5 [BE] Include `response_source` in `voice_generation_completed` EventEnvelope payload

## 2. Bridge: Timing Metrics in Payloads

- [x] 2.1 [BE] Include `send_to_created_ms` in `response_created` EventEnvelope payload (omit if 0)
- [x] 2.2 [BE] Include `created_to_done_ms` in `voice_generation_completed` EventEnvelope payload (omit if 0)
- [x] 2.3 [BE] Reset `_response_create_sent_ms` and `_response_created_ms` in `send_voice_start()`

## 3. Coordinator: Use Bridge Timing and Source

- [x] 3.1 [BE] Read `send_to_created_ms` from `response_created` payload and pass to `_send_debug("model_processing", send_to_created_ms=...)`
- [x] 3.2 [BE] Read `created_to_done_ms` from `voice_generation_completed` payload and pass to `_send_debug("generation_finish", created_to_done_ms=...)`
- [x] 3.3 [BE] When `response_source == "specialist"`, emit `_send_debug("specialist_processing")` instead of `"model_processing"`

## 4. Coordinator: Direct Route Timing Fix

- [x] 4.1 [BE] Add `_debug_route_result_emitted: bool` and `_debug_audio_playback_end_received: bool` flags, reset at `speech_start`
- [x] 4.2 [BE] In `voice_generation_completed` handler for router responses with no `model_router_action`, emit `_send_debug("route_result", label="direct", route_type="direct")`; set flag. Do NOT emit `generation_start` (now comes from frontend).
- [x] 4.3 [BE] Gate existing retroactive `route_result` in `_on_voice_completed` with `if not _debug_route_result_emitted`
- [x] 4.4 [BE] Gate `generation_finish` in `_on_voice_completed` with `if not _debug_audio_playback_end_received`

## 5. Coordinator: Receive Client Debug Events

- [x] 5.1 [BE] Add `handle_client_debug_event(stage: str, turn_id: str, ts: int)` method to Coordinator that calls `_send_debug(stage)`
- [x] 5.2 [BE] Set `_debug_audio_playback_end_received = True` when stage is `audio_playback_end`
- [x] 5.3 [BE] Route `client_debug_event` WebSocket messages to Coordinator (in `call_session.py` or WebSocket handler)

## 6. Frontend: Emit Audio Playback Events

- [x] 6.1 [FE] Track `firstAudioReceived` flag per response in `use-voice-session.ts`, reset on `response.created`
- [x] 6.2 [FE] On first `response.audio.delta`, send `{type: "client_debug_event", stage: "audio_playback_start", turn_id, ts}` to backend WebSocket
- [x] 6.3 [FE] On `response.audio.done`, send `{type: "client_debug_event", stage: "audio_playback_end", turn_id, ts}` to backend WebSocket
- [x] 6.4 [FE] Track current `turn_id` from last received `debug_event` message

## 7. Frontend: Display Improvements

- [x] 7.1 [FE] Add `send_to_created_ms?: number` and `created_to_done_ms?: number` to `DebugStage` interface
- [x] 7.2 [FE] Parse `send_to_created_ms` and `created_to_done_ms` from debug_event messages in `useDebugChannel`
- [x] 7.3 [FE] Display bridge timing as extra line in `StageBox` when present (`bridge: Xms`)
- [x] 7.4 [FE] Add `audio_playback_start` ("Audio Start") and `audio_playback_end` ("Audio End") to `STAGE_LABELS`
- [x] 7.5 [FE] Update `stageLabel()` for readable labels: direct → "Direct Response", delegate → "Delegate → {label}", model_processing → "Model Inference"

## 8. Tests

- [x] 8.1 [TEST] Unit test: bridge includes `response_source` and timing in `response_created` payload
- [x] 8.2 [TEST] Unit test: bridge includes `response_source` and timing in `voice_generation_completed` payload
- [x] 8.3 [TEST] Unit test: coordinator emits `specialist_processing` when `response_source == "specialist"`
- [x] 8.4 [TEST] Unit test: coordinator emits `route_result(direct)` at `voice_generation_completed` for router direct responses (no `generation_start`)
- [x] 8.5 [TEST] Unit test: coordinator `handle_client_debug_event` emits through debug pipeline
- [x] 8.6 [TEST] Unit test: coordinator fallback skips `generation_finish` when `_debug_audio_playback_end_received` is True
- [x] 8.7 [TEST] Frontend DebugStage interface already includes bridge timing fields (verified in code)

## 9. Routing Refactor: Markers → Function Calling (emerged during debug validation)

- [x] 9.1 [BE] Replace `parse_model_action()` / `ROUTE_MARKER_RE` / `extract_filler_text()` with `ROUTE_TOOL_DEFINITION` and `parse_function_call_action()` in `model_router.py`
- [x] 9.2 [BE] Add `route_to_specialist` tool to `RouterPromptBuilder.build_response_create()` with `tool_choice: "auto"`
- [x] 9.3 [BE] Handle `response.function_call_arguments.done` in `realtime_event_bridge.py` — emit `model_router_action` event
- [x] 9.4 [BE] Remove all marker detection, `_route_marker_cancelled`, cancel logic from bridge
- [x] 9.5 [BE] Add `_function_call_received` flag to bridge for `response.done` branching
- [x] 9.6 [BE] Register `route_to_specialist` tool in `session.update` (`calls.py`) — required for model to invoke functions
- [x] 9.7 [BE] Build specialist prompt as dict with embedded conversation history and language instruction in `coordinator.py`
- [x] 9.8 [BE] Update `router_prompt.yaml` — replace marker instructions with function calling instructions
- [x] 9.9 [FE] Remove all marker detection, `response.cancel`, transcript buffer, and mute logic from `use-voice-session.ts`
- [x] 9.10 [TEST] Unit tests for `parse_function_call_action()` and bridge function call handling
