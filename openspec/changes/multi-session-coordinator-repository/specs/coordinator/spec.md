## ADDED Requirements

### Requirement: Coordinator lifecycle management via SessionRepository
The Coordinator SHALL be instantiated and managed by SessionRepository within a CallSessionEntry. The Coordinator SHALL receive its call_id and voice_client_reference during construction via the repository. The Coordinator SHALL remain active for the entire session duration and SHALL process only EventEnvelope objects matching its call_id.

#### Scenario: Coordinator bound to session call_id
- **WHEN** SessionRepository creates a session with `call_id=ID1`
- **THEN** the instantiated Coordinator SHALL have `self.call_id = ID1` and SHALL only process EventEnvelopes with `envelope.call_id == ID1`

#### Scenario: Coordinator receives voice_client callback
- **WHEN** a Coordinator is created via SessionRepository.create_session()
- **THEN** the Coordinator SHALL be registered to receive voice_client events for its call_id and SHALL forward events to its event bus

#### Scenario: Coordinator lifecycle ends with session
- **WHEN** SessionRepository removes a session (call_id=ID1)
- **THEN** the Coordinator for ID1 SHALL receive a termination signal and proceed with graceful cleanup (flush events, close resources)

### Requirement: Coordinator call_id validation on event processing
The Coordinator SHALL validate every EventEnvelope's call_id before processing. If the call_id does not match the Coordinator's own call_id, the Coordinator SHALL log a warning and drop the event (defense in depth against misconfiguration or routing bugs).

#### Scenario: Envelope matches coordinator call_id
- **WHEN** Coordinator (call_id=ID1) receives EventEnvelope with `call_id=ID1`
- **THEN** Coordinator SHALL proceed with normal event processing

#### Scenario: Envelope call_id mismatch
- **WHEN** Coordinator (call_id=ID1) receives EventEnvelope with `call_id=ID2`
- **THEN** Coordinator SHALL log a warning "Event call_id mismatch: expected ID1, got ID2" and drop the event
- **AND** a counter (for observability) SHALL be incremented

#### Scenario: First event in session
- **WHEN** Coordinator (call_id=ID1) receives the first EventEnvelope after instantiation
- **THEN** Coordinator SHALL verify the call_id matches and process normally
