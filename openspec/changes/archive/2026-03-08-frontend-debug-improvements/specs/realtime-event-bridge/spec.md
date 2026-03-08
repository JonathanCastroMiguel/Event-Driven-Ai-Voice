## ADDED Requirements

### Requirement: Debug event forwarding

The bridge SHALL forward debug events from the Coordinator to the frontend via `send_to_frontend()`. Debug events are regular JSON messages on the existing event WebSocket — no separate channel required.

#### Scenario: Debug event sent to frontend
- **WHEN** the Coordinator calls `send_to_frontend()` with a `debug_event` message and the frontend WebSocket is connected
- **THEN** the bridge SHALL send the JSON-encoded message to the frontend

### Requirement: Debug control message handling

The bridge's WebSocket handler in `calls.py` SHALL intercept `debug_enable` and `debug_disable` messages from the frontend and set the Coordinator's `_debug_enabled` flag accordingly, without forwarding these control messages to OpenAI.

#### Scenario: Frontend enables debug
- **WHEN** the event WebSocket receives `{"type": "debug_enable"}` from the frontend
- **THEN** the handler SHALL set `coordinator._debug_enabled = True` and NOT forward the message to the bridge's `handle_frontend_event()`

#### Scenario: Frontend disables debug
- **WHEN** the event WebSocket receives `{"type": "debug_disable"}` from the frontend
- **THEN** the handler SHALL set `coordinator._debug_enabled = False` and NOT forward the message to the bridge's `handle_frontend_event()`
