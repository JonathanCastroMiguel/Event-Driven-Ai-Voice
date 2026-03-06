## ADDED Requirements

### Requirement: Session creation endpoint
The system SHALL expose `POST /calls` that creates a new CallSession, assigns a `call_id` (UUID), and returns it to the client. The endpoint SHALL initialize the Coordinator, TurnManager, AgentFSM, and RealtimeVoiceBridge for the new call.

#### Scenario: Successful call creation
- **WHEN** a client sends `POST /calls`
- **THEN** the system SHALL return HTTP 201 with `{"call_id": "<uuid>", "status": "created"}`
- **AND** a Coordinator with all actors SHALL be initialized for the call

#### Scenario: Call creation with active call limit exceeded
- **WHEN** `POST /calls` is called and the maximum concurrent call limit is reached
- **THEN** the system SHALL return HTTP 503 with `{"error": "max_calls_exceeded"}`

### Requirement: SDP offer/answer exchange
The system SHALL expose `POST /calls/{call_id}/offer` that accepts an SDP offer from the browser, creates a WebRTC peer connection via aiortc, configures audio tracks and DataChannels, and returns the SDP answer.

#### Scenario: Successful SDP exchange
- **WHEN** a client sends `POST /calls/{call_id}/offer` with a valid SDP offer
- **THEN** the system SHALL return HTTP 200 with the SDP answer
- **AND** the WebRTC peer connection SHALL be configured with an audio transceiver (sendrecv) and two DataChannels ("control", "debug")

#### Scenario: SDP offer for non-existent call
- **WHEN** `POST /calls/{call_id}/offer` is called with an unknown `call_id`
- **THEN** the system SHALL return HTTP 404

### Requirement: ICE candidate exchange
The system SHALL expose `POST /calls/{call_id}/ice` for trickle ICE candidate exchange between browser and server.

#### Scenario: ICE candidate added
- **WHEN** a client sends a valid ICE candidate to `POST /calls/{call_id}/ice`
- **THEN** the system SHALL add the candidate to the peer connection and return HTTP 204

### Requirement: Call termination
The system SHALL expose `DELETE /calls/{call_id}` that closes the WebRTC peer connection, cleans up the Coordinator and all actors, and removes the call from the session registry.

#### Scenario: Graceful call termination
- **WHEN** a client sends `DELETE /calls/{call_id}`
- **THEN** the system SHALL close the WebRTC peer connection, clean up the Coordinator, and return HTTP 204

#### Scenario: Call terminated on peer connection close
- **WHEN** the WebRTC peer connection is closed by the browser (e.g., tab closed)
- **THEN** the system SHALL detect the disconnection and clean up the Coordinator and all actors automatically

### Requirement: STUN/TURN configuration
The system SHALL support configurable STUN/TURN servers via environment variables (`STUN_SERVERS`, `TURN_SERVERS`, `TURN_USERNAME`, `TURN_CREDENTIAL`). The ICE configuration SHALL be included in the SDP answer.

#### Scenario: Default STUN configuration
- **WHEN** no STUN/TURN environment variables are set
- **THEN** the system SHALL use Google's public STUN server (`stun:stun.l.google.com:19302`) as default

#### Scenario: Custom TURN configuration
- **WHEN** `TURN_SERVERS`, `TURN_USERNAME`, and `TURN_CREDENTIAL` environment variables are set
- **THEN** the system SHALL include the TURN server in the ICE configuration for NAT traversal
