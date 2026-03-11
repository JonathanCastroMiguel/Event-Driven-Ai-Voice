## Context

The voice client (`frontend/src/`) connects to OpenAI's Realtime API via WebRTC. Audio flows browser↔OpenAI directly; a parallel WebSocket to the backend handles event forwarding and debug data. The current implementation lacks mute control, has potential echo issues on laptop speakers, has a CSS bug in the specialist debug timeline, and suffers from model non-determinism in specialist routing.

## Goals / Non-Goals

**Goals:**
- Add mute toggle with zero-renegotiation WebRTC approach
- Harden echo cancellation for non-headphone setups
- Fix specialist timeline visual offset in the debug panel
- Make the router prompt more deterministic for function calling

**Non-Goals:**
- Server-side audio processing (SpeexDSP, etc.) — browser AEC should suffice
- Changing the WebRTC architecture or signaling flow
- Modifying the Coordinator or AgentFSM logic
- Adding VoIP/SIP integration

## Decisions

### D1: Mute via `track.enabled = false`

**Choice**: Toggle `sender.track.enabled` on the WebRTC audio sender track.

**Alternatives considered**:
- `track.stop()` + re-acquire: Requires new `getUserMedia` call and renegotiation. Too slow.
- `replaceTrack(null)`: Works but requires `replaceTrack(originalTrack)` to unmute, more complex state.
- `sender.track.enabled = false`: Sends silence frames, no renegotiation, instant toggle. OpenAI continues receiving (silent) audio so VAD stays quiet.

**Rationale**: Simplest approach, no side effects, well-supported across browsers.

### D2: Echo cancellation — browser AEC only

**Choice**: Rely on browser's built-in AEC (`echoCancellation: true` in getUserMedia constraints) + ensure audio playback uses a DOM `<audio>` element (not Web Audio API) so the browser can correlate input/output for cancellation.

**Alternatives considered**:
- SpeexDSP via WASM: Adds ~200KB bundle + processing overhead. Overkill for browser testing.
- Server-side echo cancellation: Adds latency, against architecture principles.
- Gain reduction during playback: Hacky, degrades UX.

**Rationale**: Browser AEC works well when the audio output goes through a standard DOM element. The current implementation already has `echoCancellation: true`. If echo persists, the issue is likely that remote audio is being played via Web Audio API instead of a DOM audio element — we need to verify and fix this path.

### D3: Specialist timeline — CSS Grid with dynamic offset

**Choice**: Replace fixed `pl-8 ml-4` CSS on the specialist row with a dynamic offset calculated from the `route_result` event's position in the main timeline.

**Implementation approach**: Use CSS Grid columns where each stage occupies a column. The specialist row starts at the column after `route_result`, visually forking from that point.

**Alternatives considered**:
- Ref measurement (`getBoundingClientRect`): Runtime measurement, fragile on resize.
- Percentage-based offset: Requires knowing total timeline width and stage count upfront.

**Rationale**: CSS Grid is declarative, handles resize naturally, and aligns with the existing Tailwind approach.

### D4: Router prompt reinforcement for deterministic function calling

**Choice**: Add explicit reinforcement rules in `decision_rules` that:
1. State the model MUST call `route_to_specialist` function (not just speak about routing)
2. Add a "NEVER do X" negative example (never say "let me connect you" without calling the function)
3. Add a repeated instruction at the end of the prompt (recency bias)

**Rationale**: LLMs are sensitive to instruction positioning and negative examples. The current prompt says "You MUST do both: speak the filler AND call the function" but this can be strengthened with explicit negative examples and end-of-prompt reinforcement. This is a prompt-only change with zero code impact.

## Risks / Trade-offs

- **[Browser AEC variability]** → Different browsers/devices have different AEC quality. Mitigation: verify DOM audio element path, document known limitations.
- **[Model non-determinism persists]** → Prompt changes may not fully eliminate the issue since it's inherent to the Realtime API model. Mitigation: the prompt improvement is best-effort; document alternative test phrases that work more reliably.
- **[CSS Grid complexity]** → Grid approach for timeline may require refactoring the stage rendering. Mitigation: keep the grid scoped to the timeline component only.
