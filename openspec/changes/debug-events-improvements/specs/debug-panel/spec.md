## Overview

Emit frontend audio playback debug events, send them to backend, display bridge timing metrics, and improve stage labels in the timeline.

## Requirements

### R1: Emit audio playback debug events from frontend

- In `use-voice-session.ts`, track a `firstAudioReceived` flag per response (reset on `response.created`).
- On first `response.audio.delta`, send `{type: "client_debug_event", stage: "audio_playback_start", turn_id, ts}` to the backend via the event WebSocket.
- On `response.audio.done`, send `{type: "client_debug_event", stage: "audio_playback_end", turn_id, ts}` to the backend via the event WebSocket.
- `ts` is `Date.now()` at the moment of detection.
- `turn_id` must match the current debug turn_id (received from the last `debug_event` message, or tracked locally).

### R2: Render audio playback events in timeline

- Add `audio_playback_start` and `audio_playback_end` to `STAGE_LABELS` in `turn-timeline.tsx` with labels "Audio Start" and "Audio End".
- These stages appear in the main timeline row (not specialist sub-flow).
- In `useDebugChannel`, these come as regular `debug_event` messages (backend re-emits them after receiving `client_debug_event`).

### R3: Display bridge timing in stage boxes

- When a `debug_event` message includes `send_to_created_ms` or `created_to_done_ms`, display as additional line in the `StageBox`.
- Format: `bridge: Xms` below the existing `+delta_ms / total_ms` line.
- If the field is absent, do not render the extra line.

### R4: Parse extra fields from debug_event messages

- In `useDebugChannel`, extract `send_to_created_ms` and `created_to_done_ms` from the raw message and include as optional fields on `DebugStage`.
- Add optional fields: `send_to_created_ms?: number`, `created_to_done_ms?: number`.

### R5: Improve stage labels for readability

- Update `STAGE_LABELS` display names (backend event names unchanged):
  - `route_result` with `route_type="direct"` → "Direct Response"
  - `route_result` with `route_type="delegate"` → "Delegate → {label}"
  - `model_processing` → "Model Inference"
  - `audio_playback_start` → "Audio Start"
  - `audio_playback_end` → "Audio End"
- Update `stageLabel()` function to handle these cases.

### R6: Verify specialist_processing in sub-flow row

- `specialist_processing` is already in `SPECIALIST_STAGES` set and `STAGE_LABELS` — verify it renders correctly between `specialist_sent` and `specialist_ready` when real events arrive.

## Files

- `frontend/src/hooks/use-voice-session.ts`
- `frontend/src/hooks/use-debug-channel.ts`
- `frontend/src/components/debug/turn-timeline.tsx`
