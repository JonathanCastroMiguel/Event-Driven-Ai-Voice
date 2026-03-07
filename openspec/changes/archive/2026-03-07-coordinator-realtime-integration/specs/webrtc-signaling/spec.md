## MODIFIED Requirements

### Requirement: Session creation endpoint
The system SHALL expose `POST /calls` that creates a new CallSession, assigns a `call_id` (UUID), and instantiates the full runtime actor stack: Coordinator, TurnManager, AgentFSM, ToolExecutor, Router, and RealtimeEventBridge. All actors SHALL be stored in the session registry for the call's lifetime.

#### Scenario: Successful call creation
- **WHEN** a client sends `POST /calls`
- **THEN** the system SHALL create all runtime actors (Coordinator, TurnManager, AgentFSM, ToolExecutor, Router), store them in the session entry, and return HTTP 201 with `{"call_id": "<uuid>", "status": "created"}`

#### Scenario: Call creation with active call limit exceeded
- **WHEN** `POST /calls` is called and the maximum concurrent call limit is reached
- **THEN** the system SHALL return HTTP 503 with `{"detail": "max_calls_exceeded"}`

### Requirement: SDP offer/answer exchange
The system SHALL expose `POST /calls/{call_id}/offer` that accepts an SDP offer from the browser, proxies it to OpenAI's Realtime WebRTC API, returns the SDP answer, and opens the server-side WebSocket connection for the RealtimeEventBridge.

#### Scenario: Successful SDP exchange with bridge connection
- **WHEN** a client sends `POST /calls/{call_id}/offer` with a valid SDP offer
- **THEN** the system SHALL proxy the SDP to OpenAI, return the SDP answer, and start the RealtimeEventBridge WebSocket connection to OpenAI
- **AND** the browser SHALL connect directly to OpenAI via WebRTC (no server-side peer connection)

#### Scenario: SDP offer for non-existent call
- **WHEN** `POST /calls/{call_id}/offer` is called with an unknown `call_id`
- **THEN** the system SHALL return HTTP 404

#### Scenario: Bridge connection failure during SDP exchange
- **WHEN** the SDP proxy succeeds but the RealtimeEventBridge WebSocket fails to connect
- **THEN** the system SHALL still return the SDP answer (call continues in degraded mode without Coordinator)
- **AND** the system SHALL log a warning

### Requirement: Call termination
The system SHALL expose `DELETE /calls/{call_id}` that tears down all runtime actors, closes the RealtimeEventBridge WebSocket, removes the call from the session registry, and returns HTTP 204.

#### Scenario: Graceful call termination with actor cleanup
- **WHEN** a client sends `DELETE /calls/{call_id}`
- **THEN** the system SHALL close the RealtimeEventBridge, tear down all runtime actors, remove the call from the session registry, and return HTTP 204

#### Scenario: Termination of non-existent call
- **WHEN** a client sends `DELETE /calls/{call_id}` with an unknown `call_id`
- **THEN** the system SHALL return HTTP 404
