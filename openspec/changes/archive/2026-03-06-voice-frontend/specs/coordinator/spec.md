## ADDED Requirements

### Requirement: Debug event emission
When debug mode is enabled for a call, the Coordinator SHALL emit debug events for key state changes: turn updates, FSM state transitions, routing decisions, and latency measurements. Debug events SHALL be emitted to a debug callback registered by the RealtimeVoiceBridge.

#### Scenario: Turn update emitted for debug
- **WHEN** debug mode is enabled and a `human_turn_finalized` event is processed
- **THEN** the Coordinator SHALL emit a debug event with `type="turn_update"`, `turn_id`, `text`, and `state`

#### Scenario: FSM state change emitted for debug
- **WHEN** debug mode is enabled and the AgentFSM transitions state
- **THEN** the Coordinator SHALL emit a debug event with `type="fsm_state"` and the new `state`

#### Scenario: Routing decision emitted for debug
- **WHEN** debug mode is enabled and `Router.classify()` returns a result
- **THEN** the Coordinator SHALL emit a debug event with `type="routing"`, `route_a`, `route_a_confidence`, and `route_b` (if applicable)

#### Scenario: Latency measurement emitted for debug
- **WHEN** debug mode is enabled and a turn completes (from `human_turn_finalized` to `realtime_voice_start`)
- **THEN** the Coordinator SHALL emit a debug event with `type="latency"`, `metric="turn_processing_ms"`, and the elapsed time

#### Scenario: No debug overhead when disabled
- **WHEN** debug mode is NOT enabled for a call
- **THEN** the Coordinator SHALL NOT emit any debug events and SHALL NOT compute debug-only metrics
