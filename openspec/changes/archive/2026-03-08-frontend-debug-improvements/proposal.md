## Why

Real-audio testing without headphones causes a feedback loop: the AI's speaker output is picked up by the microphone, making the model respond to itself endlessly. The debug panel is non-functional for real debugging — it shows raw events instead of a clear visual pipeline, has no real timing data, and runs even in production adding unnecessary latency. The voice client also has browser compatibility issues (audio element not in DOM, incomplete mic permission UX).

## What Changes

- **Echo cancellation**: Enable browser-native echo cancellation (AEC) on the microphone MediaStream so the frontend can be used without headphones. The AI's speaker output must not trigger the VAD or be picked up as user speech.
- **Backend-controlled debug mode**: Debug event emission is controlled by a backend flag (env var or config). When debug is OFF, no debug events are emitted over the WebSocket — zero overhead in production. Frontend toggle sends `debug_enable`/`debug_disable` to the backend, which starts/stops emitting debug events.
- **Backend debug event emission**: When debug is ON, Coordinator and Bridge emit structured debug events via WebSocket — per-stage timing, FSM transitions, routing results, barge-in events, and turn completions.
- **Debug panel redesign — visual timeline**: Replace the current raw event display with a visual pipeline timeline per turn:
  - Horizontal box-and-arrow diagram: each box is a pipeline stage, connected left-to-right
  - Full stage sequence: `speech_start` → `speech_stop` → `audio_committed` → `prompt_sent` → `model_processing` → `route_result` (label + direct/delegate) → `generation_start` → `generation_finish`
  - `prompt_sent` and `model_processing` are new stages that break down the previously opaque gap between audio commit and route result (prompt building time vs network RTT vs model inference)
  - Each box shows: delta ms (time since previous step) and cumulative ms (from first event)
  - **Branching for delegate routes**: When `route_result` is "delegate", the timeline forks into two parallel rows:
    - **Main row** (top): continues with fill-silence events while the specialist works
    - **Sub-flow row** (bottom): `specialist_sent` → `specialist_processing` → `specialist_ready`, branching down from `route_result`
    - When the specialist is ready, the sub-flow reconnects upward to the main row, merging into `generation_start` → `generation_finish`
    - For direct routes, the timeline stays as a single row (no fork)
  - Barge-in: if detected, the timeline is cut short with a visual barge-in indicator
  - Last 5 turns displayed as a FIFO stack: newest turn enters from the top, pushing older turns down
- **Voice client fixes**: Append audio element to DOM for cross-browser playback, add proper mic permission denied UX (clear message + disabled Start Call), improve connection error handling.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `voice-client-ui`: Add echo cancellation to microphone capture, fix audio element DOM attachment, add mic permission denied UX, improve connection error handling.
- `debug-panel`: Complete redesign — visual pipeline timeline with per-stage timing boxes, FIFO stack of last 5 turns, barge-in visualization. Backend-controlled on/off via WebSocket messages.
- `coordinator`: Emit structured debug events (FSM transitions, per-stage timing, routing results) when debug mode is enabled. Support `debug_enable`/`debug_disable` control messages.
- `realtime-event-bridge`: Forward debug timing events (send→created, created→done, total response, barge-in) when debug mode is enabled.

## Impact

- **Backend code**: `coordinator.py` (debug event emission, debug flag), `realtime_event_bridge.py` (timing event forwarding), `calls.py` (WebSocket debug control messages), `config.py` (debug mode env var)
- **Frontend code**: `debug-panel.tsx` (full redesign — timeline visualization), `use-debug-channel.ts` (new structured event types), `use-voice-session.ts` (echo cancellation, audio element fix, mic permission UX), `voice-session.tsx` (debug toggle sends control message)
- **APIs**: No REST API changes. New WebSocket message types: `debug_enable`, `debug_disable`, `debug_event` (backward compatible).
- **Tests**: Frontend component tests for timeline rendering, backend unit tests for debug event emission and debug flag gating
