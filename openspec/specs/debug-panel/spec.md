## ADDED Requirements

### Requirement: Debug mode toggle
The voice client SHALL provide a UI toggle to enable/disable debug mode. When enabled, it SHALL send `{"type": "debug_enable"}` on the control DataChannel. When disabled, it SHALL send `{"type": "debug_disable"}`.

#### Scenario: Debug mode enabled
- **WHEN** the user toggles debug mode on
- **THEN** the client SHALL send `debug_enable` on the control DataChannel and display the debug panel

#### Scenario: Debug mode disabled
- **WHEN** the user toggles debug mode off
- **THEN** the client SHALL send `debug_disable` on the control DataChannel and hide the debug panel

### Requirement: Zero latency impact when disabled
When debug mode is disabled, the debug DataChannel SHALL NOT have any active listeners and the debug panel component SHALL NOT be rendered.

#### Scenario: No overhead when disabled
- **WHEN** debug mode is off
- **THEN** no debug events SHALL be processed or rendered
- **AND** the audio pipeline latency SHALL not be affected

### Requirement: Turn history display
The debug panel SHALL display the current active turn and previous turns, loaded top-to-bottom (newest at bottom).

#### Scenario: Turn update received
- **WHEN** a `turn_update` message arrives on the debug DataChannel with `turn_id`, `text`, and `state`
- **THEN** the debug panel SHALL display or update the turn entry in the turn history list

#### Scenario: Multiple turns displayed
- **WHEN** multiple turns have been processed
- **THEN** all turns SHALL be visible in chronological order (oldest at top, newest at bottom)

### Requirement: FSM status display
The debug panel SHALL display the current state of the AgentFSM.

#### Scenario: FSM state change
- **WHEN** a `fsm_state` message arrives on the debug DataChannel
- **THEN** the debug panel SHALL display the current FSM state (e.g., "idle", "generating", "waiting_tool")

### Requirement: Routing details display
The debug panel SHALL display the most recent routing decision including Route A label, confidence, and Route B details when applicable.

#### Scenario: Routing decision displayed
- **WHEN** a `routing` message arrives with `route_a`, `route_a_confidence`, and optionally `route_b`
- **THEN** the debug panel SHALL display all routing details

### Requirement: Event log display
The debug panel SHALL display recent system events in reverse chronological order (newest at top).

#### Scenario: Event logged
- **WHEN** an `event` message arrives on the debug DataChannel
- **THEN** it SHALL be prepended to the event log list with its `event_type` and `ts`

#### Scenario: Event log size limited
- **WHEN** more than 50 events have been received
- **THEN** the oldest events SHALL be removed from the display to keep the list at 50 entries maximum

### Requirement: Latency metrics display
The debug panel SHALL display key latency metrics: user speech duration, turn management time, and agent processing time.

#### Scenario: Latency metric received
- **WHEN** a `latency` message arrives with `metric` and `value`
- **THEN** the debug panel SHALL display or update the corresponding latency value

### Requirement: Debug data delivery
Debug data SHALL be delivered from the backend to the frontend via the "debug" WebRTC DataChannel, separate from the audio path.

#### Scenario: Debug data on separate channel
- **WHEN** debug mode is enabled and system events occur
- **THEN** debug data SHALL flow through the "debug" DataChannel
- **AND** the audio DataChannel/track SHALL not carry any debug data

### Requirement: Turn timeline specialist row rendering
The debug panel SHALL render the specialist processing row (delegate stages) starting at a dynamic horizontal offset that aligns with the `route_result` event's position in the main timeline. The specialist row SHALL visually fork from the `route_result` stage, not from the far left of the timeline.

#### Scenario: Specialist stages fork from route_result
- **WHEN** a turn includes specialist stages (`is_delegate: true`) following a `route_result` event
- **THEN** the specialist row SHALL begin rendering at the same horizontal position where `route_result` ends in the main timeline row

#### Scenario: Direct route has no specialist row
- **WHEN** a turn has `route_type="direct"` with no specialist stages
- **THEN** no specialist row SHALL be rendered

#### Scenario: Timeline resizes correctly
- **WHEN** the browser window is resized while the debug panel displays a specialist timeline
- **THEN** the specialist row offset SHALL adjust to maintain alignment with `route_result`

### Requirement: Audio playback event emission
The frontend SHALL emit `audio_playback_start` and `audio_playback_end` debug events by detecting `output_audio_buffer.started` (first occurrence per response) and `output_audio_buffer.stopped` from the OpenAI WebRTC data channel. These events SHALL be sent to the backend via the event WebSocket as `client_debug_event` messages.

#### Scenario: Audio playback start emitted
- **WHEN** the first `output_audio_buffer.started` event arrives for a response
- **THEN** the frontend SHALL send `{type: "client_debug_event", stage: "audio_playback_start", turn_id, ts}` to the backend

#### Scenario: Audio playback end emitted
- **WHEN** `output_audio_buffer.stopped` arrives
- **THEN** the frontend SHALL send `{type: "client_debug_event", stage: "audio_playback_end", turn_id, ts}` to the backend

### Requirement: Bridge timing display
The debug panel SHALL display bridge timing metrics (`send_to_created_ms`, `created_to_done_ms`) when present in debug events.

#### Scenario: Bridge timing shown in stage box
- **WHEN** a debug_event includes `send_to_created_ms: 150`
- **THEN** the stage box SHALL display `bridge: 150ms` below the delta/total line

### Requirement: Readable stage labels
The debug panel SHALL display human-friendly labels for debug stages without changing backend event names.

#### Scenario: Direct route label
- **WHEN** `route_result` event has `route_type="direct"`
- **THEN** the label SHALL display "Direct Response"

#### Scenario: Delegate route label
- **WHEN** `route_result` event has `route_type="delegate"` and `label="billing"`
- **THEN** the label SHALL display "Delegate → billing"

#### Scenario: Model processing label
- **WHEN** `model_processing` event is displayed
- **THEN** the label SHALL display "Model Inference"
