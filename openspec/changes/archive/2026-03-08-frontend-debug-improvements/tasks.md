## 1. [BE] Debug mode control

- [x] 1.1 Add `_debug_enabled: bool = False` flag to Coordinator
- [x] 1.2 Add `set_debug_enabled(enabled: bool)` method on Coordinator
- [x] 1.3 Intercept `debug_enable`/`debug_disable` messages in `calls.py` WebSocket handler — set flag on Coordinator, do NOT forward to bridge

## 2. [BE] Debug event emission

- [x] 2.1 Add `_debug_turn_id`, `_debug_turn_start_ms`, `_debug_last_stage_ms` fields to Coordinator
- [x] 2.2 Add `_send_debug(stage, **extra)` helper — builds `debug_event` with turn_id/delta_ms/total_ms/ts, sends via `send_to_frontend()`, no-op when `_debug_enabled` is False
- [x] 2.3 Emit `speech_start` in `_on_speech_started` (assigns new `_debug_turn_id`)
- [x] 2.4 Emit `speech_stop` in `_on_speech_stopped`
- [x] 2.5 Emit `audio_committed` in `_on_audio_committed`
- [x] 2.6 Emit `prompt_sent` after RouterPromptBuilder builds prompt and before sending to bridge
- [x] 2.7 Emit `model_processing` when bridge reports `response.created` (forward timing from bridge)
- [x] 2.8 Emit `route_result` on `response.done` with `label` and `route_type` (direct/delegate)
- [x] 2.9 Emit `fill_silence` on main flow when Coordinator launches silence-filling for delegate routes
- [x] 2.10 Emit `specialist_sent`, `specialist_processing`, `specialist_ready` for delegate routes (parallel sub-flow)
- [x] 2.11 Emit `generation_start` when voice generation begins (first audio or specialist response)
- [x] 2.12 Emit `generation_finish` in `_on_voice_completed`
- [x] 2.13 Emit `barge_in` when barge-in is detected

## 3. [FE] Voice client fixes

- [x] 3.1 Append audio element to `document.body` (hidden) on session start, remove on cleanup
- [x] 3.2 Catch `NotAllowedError` from `getUserMedia()` — show "Microphone access required" message, disable Start Call button
- [x] 3.3 Add `sendDebugControl(enabled: boolean)` to `useVoiceSession` — sends `debug_enable`/`debug_disable` via event WebSocket

## 4. [FE] Debug channel refactor

- [x] 4.1 Define `DebugTurnTimeline` type: `turn_id`, `stages[]` (stage/delta_ms/total_ms/label/route_type), `is_delegate: boolean`, `specialist_stages[]`, `barge_in: boolean`
- [x] 4.2 Refactor `useDebugChannel` to process `debug_event` messages — group by `turn_id`, append stages to current turn
- [x] 4.3 Detect delegate routes: when `route_result` has `route_type: "delegate"`, subsequent `specialist_*` stages go to `specialist_stages[]`
- [x] 4.4 Maintain FIFO of last 5 turns, evict oldest when 6th arrives
- [x] 4.5 Handle `barge_in` stage — mark turn as interrupted

## 5. [FE] Debug panel timeline redesign

- [x] 5.1 Create `TurnTimeline` component — horizontal row of stage boxes connected by arrows
- [x] 5.2 Each box shows: stage name, delta ms, cumulative ms
- [x] 5.3 `route_result` box shows routing label + direct/delegate badge
- [x] 5.4 Color-code boxes by delta_ms: green (<100ms), yellow (100-300ms), red (>=300ms)
- [x] 5.5 Branching for delegate routes: main row shows waiting state after `route_result`, sub-flow row branches down with `specialist_sent` → `specialist_processing` → `specialist_ready`, reconnects up to `generation_start`
- [x] 5.6 Barge-in box rendered as red indicator cutting the timeline
- [x] 5.7 Replace `DebugPanel` with new layout: FIFO stack of 5 `TurnTimeline` rows (newest on top)
- [x] 5.8 Wire debug toggle to send WebSocket control message instead of frontend-only state

## 6. [TEST] Backend tests

- [x] 6.1 Test `_debug_enabled` flag defaults to False and no events emitted
- [x] 6.2 Test `debug_enable`/`debug_disable` control messages toggle the flag
- [x] 6.3 Test `_send_debug` emits correct `debug_event` structure with timing
- [x] 6.4 Test direct route turn emits all 8 stages with consistent `turn_id`
- [x] 6.5 Test delegate route turn emits specialist sub-flow stages
- [x] 6.6 Test barge-in emits `barge_in` stage

## 7. [TEST] Frontend tests

- [x] 7.1 Test `useDebugChannel` groups events by `turn_id` into timelines
- [x] 7.2 Test delegate route events split into main + specialist_stages
- [x] 7.3 Test FIFO eviction at 5 turns
- [x] 7.4 Test `TurnTimeline` renders single-row for direct, branching for delegate
- [x] 7.5 Test barge-in renders truncated timeline
- [x] 7.6 Test color coding thresholds (green/yellow/red)
