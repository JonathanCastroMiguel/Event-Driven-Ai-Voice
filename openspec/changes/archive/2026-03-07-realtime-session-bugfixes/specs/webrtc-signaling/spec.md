## MODIFIED Requirements

### Requirement: SDP offer/answer exchange
The system SHALL expose `POST /calls/{call_id}/offer` that performs a two-step exchange with OpenAI: (1) `POST /v1/realtime/sessions` with session config (model, modalities, input_audio_transcription, turn_detection with create_response=false) to obtain an ephemeral key, (2) `POST /v1/realtime` with the ephemeral key and SDP offer to obtain the SDP answer. The server API key SHALL only be used for the sessions call — the ephemeral key is used for the SDP exchange.

#### Scenario: Successful two-step SDP exchange
- **WHEN** a client sends `POST /calls/{call_id}/offer` with a valid SDP offer
- **THEN** the system SHALL first call `POST /v1/realtime/sessions` with session config to get an ephemeral key, then call `POST /v1/realtime` with the ephemeral key and SDP offer, and return the SDP answer
- **AND** the browser SHALL connect directly to OpenAI via WebRTC using the ephemeral key

#### Scenario: Session creation failure
- **WHEN** `POST /v1/realtime/sessions` returns a non-200 status
- **THEN** the system SHALL return HTTP 502 with detail "OpenAI session creation error: {status}"

#### Scenario: SDP exchange failure after session created
- **WHEN** the session is created successfully but `POST /v1/realtime` returns a non-200 status
- **THEN** the system SHALL return HTTP 502 with detail "OpenAI Realtime API error: {status}"

#### Scenario: SDP offer for non-existent call
- **WHEN** `POST /calls/{call_id}/offer` is called with an unknown `call_id`
- **THEN** the system SHALL return HTTP 404

## ADDED Requirements

### Requirement: WebSocket event forwarding endpoint
The system SHALL expose `WS /calls/{call_id}/events` for bidirectional event forwarding between the browser and the Coordinator. Input direction: browser forwards OpenAI data channel events → Bridge → Coordinator. Output direction: Coordinator commands → Bridge → browser → OpenAI data channel.

#### Scenario: WebSocket connection established
- **WHEN** a browser connects to `WS /calls/{call_id}/events` for a valid call
- **THEN** the system SHALL accept the WebSocket, register it with the Bridge via `set_frontend_ws()`, and begin forwarding events

#### Scenario: WebSocket connection for unknown call
- **WHEN** a browser connects to `WS /calls/{call_id}/events` with an unknown `call_id`
- **THEN** the system SHALL close the WebSocket with code 4004 and reason "Call not found"

#### Scenario: Browser forwards OpenAI event
- **WHEN** the browser sends a JSON message on the WebSocket containing an OpenAI data channel event
- **THEN** the system SHALL pass it to `bridge.handle_frontend_event()` for translation and dispatch to the Coordinator

#### Scenario: WebSocket disconnection cleanup
- **WHEN** the WebSocket disconnects
- **THEN** the system SHALL call `bridge.set_frontend_ws(None)` and log the disconnection

### Requirement: One-time session.update on WebSocket connection
On WebSocket connection, the system SHALL send a one-time `session.update` message through the WebSocket to configure: `input_audio_transcription: {model: "whisper-1"}` and `turn_detection: {type: "server_vad", create_response: false}`. This ensures transcription events fire and the model does not auto-respond to speech.

#### Scenario: Session update sent on connection
- **WHEN** a WebSocket connection is established for a call
- **THEN** the system SHALL send a `session.update` message via `bridge.send_to_frontend()` before processing any incoming events

#### Scenario: Session update buffered by frontend
- **WHEN** the session.update is sent before the data channel is open
- **THEN** the frontend's `sendOrBuffer` mechanism SHALL queue the message and flush it when the data channel opens

### Requirement: Runtime actor wiring on call creation
`POST /calls` SHALL instantiate the full runtime actor stack and wire events bidirectionally: Bridge input events → Coordinator `handle_event()`, Coordinator output events (RealtimeVoiceStart, RealtimeVoiceCancel) → Bridge `send_voice_start()` / `send_voice_cancel()`.

#### Scenario: Actor wiring at creation
- **WHEN** `POST /calls` creates a new call session
- **THEN** the Bridge SHALL be wired to the Coordinator via `bridge.on_event(coordinator.handle_event)` and the Coordinator SHALL have an output callback that dispatches to the Bridge

#### Scenario: Coordinator output dispatched to Bridge
- **WHEN** the Coordinator emits a `RealtimeVoiceStart` event
- **THEN** the output callback SHALL call `bridge.send_voice_start(event)` to forward the command to the browser

### Requirement: Policies fallback for development
If the shared `PoliciesRegistry` is not initialized at startup, the system SHALL fall back to stub policies containing basic instructions for each `PolicyKey` value. A warning SHALL be logged when stubs are used.

#### Scenario: Stub policies used when not initialized
- **WHEN** `POST /calls` is called and `_shared_policies` is `None`
- **THEN** the system SHALL create a stub `PoliciesRegistry` with default instructions and log `policies_not_initialized_using_stubs`

#### Scenario: Shared policies used when available
- **WHEN** `set_shared_router_and_policies()` has been called at startup
- **THEN** the system SHALL use the shared `PoliciesRegistry` instance
