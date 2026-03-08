## Overview

Fix debug event emission gaps in the Coordinator: integrate frontend audio playback events, fix direct route timing, distinguish router vs specialist processing, and pass bridge timing data.

## Requirements

### R1: Receive and integrate client debug events

- Handle `client_debug_event` messages forwarded from the WebSocket handler. Expected stages: `audio_playback_start`, `audio_playback_end`.
- On receipt, call `_send_debug(stage)` so the event gets proper `delta_ms`/`total_ms` relative to `_debug_turn_start_ms` and is emitted through the debug pipeline.
- Track `_debug_audio_playback_end_received: bool` flag, set `True` when `audio_playback_end` arrives. Reset at `speech_start`.

### R2: Use bridge timing data in debug events

- Read `send_to_created_ms` from `response_created` envelope payload and pass as extra field in `_send_debug("model_processing", send_to_created_ms=...)`.
- Read `created_to_done_ms` from `voice_generation_completed` envelope payload and pass as extra field in `_send_debug("generation_finish", created_to_done_ms=...)`.
- If payload fields are missing (backward compat), omit them from the debug event.

### R3: Distinguish router vs specialist model_processing

- When `response_created` envelope has `response_source == "specialist"`, emit `_send_debug("specialist_processing")` instead of `_send_debug("model_processing")`.
- When `response_source == "router"` or is absent, emit `_send_debug("model_processing")` as before.

### R4: Emit route_result for direct routes at response.done

- In the `voice_generation_completed` handler for router responses (identified by `response_source == "router"`), when no `model_router_action` was detected, emit `_send_debug("route_result", label="direct", route_type="direct")`.
- Do NOT emit `generation_start` from the backend — this now comes from the frontend as `audio_playback_start`.
- Add `_debug_route_result_emitted: bool` flag, reset at `speech_start`, set `True` when `route_result` is emitted.
- The existing retroactive emission in `_on_voice_completed` (ROUTING state) becomes a fallback: only emit `route_result` if `_debug_route_result_emitted` is `False`.

### R5: Fallback generation_finish in voice_completed

- In `_on_voice_completed`, emit `_send_debug("generation_finish")` only if `_debug_audio_playback_end_received` is `False` (frontend event didn't arrive — barge-in, error, etc.).
- If `audio_playback_end` was received, skip the fallback.

### R6: Keep specialist flow debug events accurate

- Verify the specialist stage sequence: `route_result(delegate)` → `fill_silence` → `specialist_sent` → `specialist_processing` (from R3) → `specialist_ready` → `audio_playback_start` → `audio_playback_end`.
- `generation_start` in the specialist path (emitted before specialist voice) remains as-is since it's emitted at the right time in `_on_model_router_action`.

### R7: Specialist prompt as dict with embedded history and language instruction (added during implementation)

- Build specialist prompt as a `response.create` dict (not list) with conversation history embedded in the `instructions` field.
- Include explicit language instruction: "Respond in the same language the customer used in the conversation history."
- History is formatted as `User: ...` / `Assistant: ...` lines appended to instructions (same pattern as `RouterPromptBuilder`).
- This ensures specialists respond in the customer's language, not in English (the routing summary is always in English).

## Files

- `backend/src/voice_runtime/coordinator.py`
- `backend/src/api/routes/calls.py` (session.update with tools registration)
