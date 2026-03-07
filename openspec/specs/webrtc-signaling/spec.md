## ADDED Requirements

### Requirement: Session creation endpoint
The system SHALL expose `POST /calls` that creates a new CallSession and assigns a `call_id` (UUID). The endpoint SHALL NOT initialize Coordinator, TurnManager, AgentFSM, or any runtime actors (deferred to future integration).

#### Scenario: Successful call creation
- **WHEN** a client sends `POST /calls`
- **THEN** the system SHALL return HTTP 201 with `{"call_id": "<uuid>", "status": "created"}`

#### Scenario: Call creation with active call limit exceeded
- **WHEN** `POST /calls` is called and the maximum concurrent call limit is reached
- **THEN** the system SHALL return HTTP 503 with `{"detail": "max_calls_exceeded"}`

### Requirement: SDP offer/answer exchange
The system SHALL expose `POST /calls/{call_id}/offer` that accepts an SDP offer from the browser and proxies it to OpenAI's Realtime WebRTC API, returning the SDP answer. The backend SHALL NOT create a local WebRTC peer connection.

#### Scenario: Successful SDP exchange
- **WHEN** a client sends `POST /calls/{call_id}/offer` with a valid SDP offer
- **THEN** the system SHALL proxy the SDP to OpenAI and return the SDP answer
- **AND** the browser SHALL connect directly to OpenAI via WebRTC (no server-side peer connection)

#### Scenario: SDP offer for non-existent call
- **WHEN** `POST /calls/{call_id}/offer` is called with an unknown `call_id`
- **THEN** the system SHALL return HTTP 404

### Requirement: Call termination
The system SHALL expose `DELETE /calls/{call_id}` that removes the call from the session registry and returns HTTP 204.

#### Scenario: Graceful call termination
- **WHEN** a client sends `DELETE /calls/{call_id}`
- **THEN** the system SHALL remove the call from the session registry and return HTTP 204

#### Scenario: Termination of non-existent call
- **WHEN** a client sends `DELETE /calls/{call_id}` with an unknown `call_id`
- **THEN** the system SHALL return HTTP 404
