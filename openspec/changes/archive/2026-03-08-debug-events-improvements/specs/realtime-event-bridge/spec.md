## Overview

Add `response_source` tracking and pass bridge timing metrics through EventEnvelope payloads so the Coordinator can emit accurate, context-aware debug events.

## Requirements

### R1: Track response source (router vs specialist)

- Add `_current_response_source: str` field, default `"router"`.
- In `send_voice_start()`, reset `_current_response_source = "router"`.
- When dispatching a specialist prompt (the path that sends `response.create` for specialist), set `_current_response_source = "specialist"`.
- Include `response_source` in the `response_created` EventEnvelope payload.
- Include `response_source` in the `voice_generation_completed` EventEnvelope payload.

### R2: Pass `send_to_created_ms` in response_created payload

- The bridge already calculates `send_to_created_ms` (line ~241). Include it in the `response_created` EventEnvelope payload dict alongside `response_source`.
- If the value is 0 or not calculable, omit it from the payload.

### R3: Pass `created_to_done_ms` in voice_generation_completed payload

- The bridge already calculates `created_to_done_ms` (line ~276). Include it in the `voice_generation_completed` EventEnvelope payload dict alongside `response_source`.
- If the value is 0 or not calculable, omit it from the payload.

### R4: Reset timing state consistently

- Ensure `_response_create_sent_ms` and `_response_created_ms` are reset at each new `send_voice_start()` to prevent stale timing from leaking across turns.
- Ensure `_current_response_source` resets to `"router"` at each `send_voice_start()`.

### R5: Function call routing (added during implementation)

- Handle `response.function_call_arguments.done` events from the OpenAI Realtime API.
- Call `parse_function_call_action()` from `model_router.py` to validate the function call.
- If valid, emit `model_router_action` EventEnvelope with `department`, `summary`, and `filler_text` (from accumulated transcript buffer).
- Track `_function_call_received: bool` flag to distinguish routing responses from direct responses in the `response.done` handler.
- On `response.done`: if `_function_call_received`, emit `voice_generation_completed` with the filler transcript; otherwise emit normal `voice_generation_completed`.

## Files

- `backend/src/voice_runtime/realtime_event_bridge.py`
