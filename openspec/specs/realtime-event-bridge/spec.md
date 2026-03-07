## ADDED Requirements

### Requirement: WebSocket connection lifecycle
The RealtimeEventBridge SHALL open a persistent WebSocket connection to `wss://api.openai.com/v1/realtime?model={model}` using the server-side OpenAI API key. The connection SHALL be opened during SDP exchange and closed when the call ends.

#### Scenario: WebSocket opened during SDP exchange
- **WHEN** the SDP offer is successfully proxied to OpenAI
- **THEN** the bridge SHALL open a WebSocket connection to the OpenAI Realtime API using the same model

#### Scenario: WebSocket closed on call end
- **WHEN** `DELETE /calls/{call_id}` is called
- **THEN** the bridge SHALL close the WebSocket connection and stop the event listener task

#### Scenario: WebSocket connection failure
- **WHEN** the WebSocket connection to OpenAI fails or is rejected
- **THEN** the bridge SHALL log the error and the call SHALL continue without Coordinator integration (degraded mode)

#### Scenario: WebSocket disconnection during call
- **WHEN** the WebSocket connection drops unexpectedly
- **THEN** the bridge SHALL attempt reconnection with exponential backoff (100ms, 200ms, 400ms, max 5s) up to 3 attempts

### Requirement: RealtimeClient protocol implementation
The RealtimeEventBridge SHALL implement the `RealtimeClient` protocol defined in `realtime_client.py`, providing `send_voice_start()`, `send_voice_cancel()`, `on_event()`, and `close()` methods.

#### Scenario: send_voice_start translates to OpenAI commands
- **WHEN** the Coordinator emits a `RealtimeVoiceStart` event with a prompt
- **THEN** the bridge SHALL send a `session.update` message to OpenAI with the system instructions from the prompt, followed by a `response.create` message to trigger the agent response

#### Scenario: send_voice_cancel translates to response.cancel
- **WHEN** the Coordinator emits a `RealtimeVoiceCancel` event
- **THEN** the bridge SHALL send a `response.cancel` message to OpenAI

#### Scenario: on_event callback registration
- **WHEN** the Coordinator registers an event callback via `on_event()`
- **THEN** the bridge SHALL invoke this callback for every translated EventEnvelope from OpenAI

### Requirement: OpenAI event to EventEnvelope translation (input direction)
The bridge SHALL translate incoming OpenAI Realtime WebSocket events into Coordinator EventEnvelopes.

#### Scenario: Speech started event translation
- **WHEN** the WebSocket receives an `input_audio_buffer.speech_started` event
- **THEN** the bridge SHALL emit an EventEnvelope with `type="speech_started"` and `source=EventSource.REALTIME`

#### Scenario: Speech stopped event translation
- **WHEN** the WebSocket receives an `input_audio_buffer.speech_stopped` event
- **THEN** the bridge SHALL emit an EventEnvelope with `type="speech_stopped"` and `source=EventSource.REALTIME`

#### Scenario: Transcription completed event translation
- **WHEN** the WebSocket receives a `conversation.item.input_audio_transcription.completed` event with a non-empty transcript
- **THEN** the bridge SHALL emit an EventEnvelope with `type="transcript_final"`, `payload={"text": "<transcript>"}`, and `source=EventSource.REALTIME`

#### Scenario: Empty transcription ignored
- **WHEN** the WebSocket receives a `conversation.item.input_audio_transcription.completed` event with an empty or whitespace-only transcript
- **THEN** the bridge SHALL NOT emit any EventEnvelope

#### Scenario: Response done event translation
- **WHEN** the WebSocket receives a `response.done` event
- **THEN** the bridge SHALL emit an EventEnvelope with `type="voice_generation_completed"` containing the active `voice_generation_id`

#### Scenario: Response failed event translation
- **WHEN** the WebSocket receives a `response.failed` event
- **THEN** the bridge SHALL emit an EventEnvelope with `type="voice_generation_error"` containing the error details

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

### Requirement: Event listener task
The bridge SHALL run a background asyncio task that continuously reads from the WebSocket and dispatches translated events to the registered callback.

#### Scenario: Listener started on connection
- **WHEN** the WebSocket connection is established
- **THEN** the bridge SHALL start a background task reading WebSocket messages in a loop

#### Scenario: Listener stopped on close
- **WHEN** `close()` is called
- **THEN** the bridge SHALL cancel the listener task and close the WebSocket

#### Scenario: Malformed message handling
- **WHEN** the WebSocket receives a message that cannot be parsed as JSON
- **THEN** the bridge SHALL log a warning and continue listening
