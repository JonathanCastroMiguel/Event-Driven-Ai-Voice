## MODIFIED Requirements

### Requirement: Visual pipeline timeline per turn

The debug panel SHALL display each turn as a horizontal box-and-arrow timeline showing pipeline stages from left to right. Each box MUST show:
- Stage name (human-readable label)
- Delta ms (time since previous stage)
- Cumulative ms (time since first event of the turn)

Full stage sequence for direct routes:
`speech_start` → `speech_stop` → `audio_committed` → `prompt_sent` → `model_processing` → `route_result` → `generation_start` → `generation_finish`

For `route_result`, the box MUST also show the routing label (e.g., "greeting", "sales") and whether it was direct or delegated.

#### Scenario: Direct route displayed as single row
- **WHEN** all 8 debug events for a direct-route turn are received
- **THEN** the panel SHALL render 8 connected boxes in a single horizontal row with delta and cumulative ms in each

#### Scenario: Partial turn displayed progressively
- **WHEN** debug events arrive incrementally for an in-progress turn
- **THEN** boxes SHALL appear progressively left-to-right as events arrive

### Requirement: Branching timeline for delegate routes

When `route_result` has `route_type: "delegate"`, the timeline SHALL fork into two parallel rows:
- **Main row** (top): continues from `route_result` with a `fill_silence` stage box (emitted when Coordinator launches silence-filling), then merges back for `generation_start` → `generation_finish`
- **Sub-flow row** (bottom): branches downward from `route_result`, showing `specialist_sent` → `specialist_processing` → `specialist_ready`
- When `specialist_ready` arrives, the sub-flow visually reconnects upward to `generation_start` on the main row

For direct routes, the timeline SHALL remain a single row with no fork.

#### Scenario: Delegate route with specialist sub-flow
- **WHEN** `route_result` arrives with `route_type: "delegate"` followed by `fill_silence` and specialist stages
- **THEN** the timeline SHALL fork: main row shows `fill_silence` box, sub-flow row shows specialist stages below running in parallel, reconnecting at `generation_start`

#### Scenario: Direct route stays single row
- **WHEN** `route_result` arrives with `route_type: "direct"`
- **THEN** the timeline SHALL continue as a single row without forking

### Requirement: Barge-in visualization

When a `barge_in` debug event is received for a turn, the timeline SHALL display a visually distinct barge-in indicator (red box) at the point of interruption. No further boxes appear after the barge-in.

#### Scenario: Barge-in during generation
- **WHEN** a `barge_in` event is received after `generation_start`
- **THEN** the timeline SHALL show boxes up to `generation_start`, followed by a red barge-in box, and no `generation_finish` box

### Requirement: FIFO stack of last 5 turns

The debug panel SHALL display the last 5 turns as a vertical FIFO stack. The newest turn enters at the top, pushing older turns down. Turns beyond the 5th are removed.

#### Scenario: 6th turn arrives
- **WHEN** a 6th turn's `speech_start` event is received
- **THEN** the oldest (bottom) turn SHALL be removed and the new turn SHALL appear at the top

### Requirement: Stage box color coding

Each stage box SHALL be color-coded based on its `delta_ms`:
- Green: delta < 100ms
- Yellow: 100ms <= delta < 300ms
- Red: delta >= 300ms

#### Scenario: Slow stage highlighted
- **WHEN** a stage has `delta_ms` of 450ms
- **THEN** its box SHALL be rendered with a red color indicator

### Requirement: Backend-controlled debug toggle

The debug panel toggle SHALL send `{"type": "debug_enable"}` or `{"type": "debug_disable"}` to the backend via the event WebSocket. When debug is off, no debug events are received and the panel shows an empty state.

#### Scenario: User enables debug
- **WHEN** the user toggles debug mode ON
- **THEN** the frontend SHALL send `{"type": "debug_enable"}` via the event WebSocket and begin displaying incoming debug events

#### Scenario: User disables debug
- **WHEN** the user toggles debug mode OFF
- **THEN** the frontend SHALL send `{"type": "debug_disable"}` via the event WebSocket and clear the timeline display
