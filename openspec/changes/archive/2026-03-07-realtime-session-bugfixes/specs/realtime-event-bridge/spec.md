## MODIFIED Requirements

### Requirement: Coordinator output to OpenAI translation (output direction)
The bridge SHALL translate Coordinator output events into OpenAI Realtime API messages and send them to the frontend via WebSocket. The `send_to_frontend()` method SHALL be public to allow external callers (e.g., `calls.py` for session.update) to send messages through the bridge.

#### Scenario: send_to_frontend is publicly accessible
- **WHEN** external code (e.g., the WebSocket endpoint in `calls.py`) needs to send a message to the frontend
- **THEN** it SHALL call `bridge.send_to_frontend(data)` directly (public method, not prefixed with underscore)

#### Scenario: Prompt with message array sent as response.create
- **WHEN** `send_voice_start()` is called with a prompt containing a message array (system + user messages)
- **THEN** the bridge SHALL send a single `response.create` with `instructions` set to the combined system messages and `input` containing the user message

#### Scenario: Simple string prompt sent as response.create
- **WHEN** `send_voice_start()` is called with a simple string prompt (e.g., filler)
- **THEN** the bridge SHALL send a `response.create` with the string as the instruction

#### Scenario: Voice cancel sent as response.cancel
- **WHEN** `send_voice_cancel()` is called
- **THEN** the bridge SHALL send `{"type": "response.cancel"}` to the frontend
