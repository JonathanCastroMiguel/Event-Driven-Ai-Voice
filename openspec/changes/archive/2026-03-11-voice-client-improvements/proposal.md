## Why

The voice client is functional for basic testing but has gaps that hurt demo quality and routing reliability:
1. No mute control — user cannot stop the agent from hearing during demos
2. Speaker playback can cause echo feedback on non-headphone setups
3. Debug panel specialist timeline renders from far left instead of forking from the `route_result` event
4. The Realtime model sometimes speaks about routing without actually calling `route_to_specialist()` — prompt needs to be more deterministic

## What Changes

- **Mute button**: Add a toggle that sets `sender.track.enabled = false` on the WebRTC audio track. Single click mute, single click unmute. Visual indicator in the UI.
- **Echo cancellation hardening**: Investigate and fix speaker feedback. Browser AEC (`echoCancellation: true`) is already enabled but may not suffice on laptop speakers. Evaluate if additional measures are needed (gain reduction, SpeexDSP, or playback isolation).
- **Debug panel specialist timeline fix**: Specialist row currently uses fixed CSS offset (`pl-8 ml-4`) instead of dynamically positioning from the `route_result` event's timeline position. Fix to fork visually from the correct point.
- **Router prompt determinism**: Strengthen the `decision_rules` in `router_prompt.yaml` to make function calling more reliable. Add explicit instruction that the model MUST call the function (not just speak about routing). Add reinforcement pattern to reduce model non-determinism.

## Capabilities

### New Capabilities

_(none — all changes modify existing capabilities)_

### Modified Capabilities

- `voice-client-ui`: Add mute toggle, echo cancellation hardening
- `debug-panel`: Fix specialist timeline rendering offset
- `model-router`: Strengthen prompt for deterministic function calling

## Impact

- **Frontend**: `use-voice-session.ts` (mute + echo), `voice-session.tsx` (mute UI), `turn-timeline.tsx` (specialist offset fix)
- **Backend**: `router_registry/v1/router_prompt.yaml` (prompt changes)
- **No API changes**, no data model changes, no new dependencies expected
