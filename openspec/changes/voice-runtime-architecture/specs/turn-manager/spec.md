## ADDED Requirements

### Requirement: Turn detection from speech events
TurnManager SHALL detect human turns by processing `speech_started`, `speech_stopped`, `transcript_partial`, and `transcript_final` events. A turn begins on `speech_started` and finalizes on `transcript_final`.

#### Scenario: Complete turn lifecycle
- **WHEN** Realtime emits `speech_started` followed by `transcript_final(text="tengo un problema")`
- **THEN** TurnManager SHALL emit `human_turn_started(turn_id)` and then `human_turn_finalized(turn_id, text="tengo un problema")`

#### Scenario: Speech started without transcript
- **WHEN** `speech_started` is received but no `transcript_final` follows within the timeout window
- **THEN** TurnManager SHALL emit `human_turn_cancelled(turn_id, reason="no_transcript")`

### Requirement: Turn state management
Each turn SHALL have a unique `turn_id` (UUID) and a sequential `seq` number within the call. Turn state SHALL be one of: `open`, `finalized`, `cancelled`.

#### Scenario: Sequential turn numbering
- **WHEN** three turns are finalized in a call
- **THEN** they SHALL have `seq` values 1, 2, 3 respectively

#### Scenario: Turn state transitions
- **WHEN** a turn is in `open` state
- **THEN** it SHALL only transition to `finalized` or `cancelled`, never back to `open`

### Requirement: TurnManager isolation
TurnManager SHALL NOT have knowledge of tools, agents, or routing. It SHALL only process speech/transcript events and emit turn lifecycle events.

#### Scenario: TurnManager receives unrelated event
- **WHEN** TurnManager receives an event type it does not handle (e.g., `tool_result`)
- **THEN** it SHALL ignore the event without error

### Requirement: Barge-in forwarding
When the Coordinator forwards a `speech_started` event during barge-in, TurnManager SHALL treat it as the start of a new turn, cancelling any open turn that has not yet finalized.

#### Scenario: Barge-in creates new turn
- **WHEN** `speech_started` arrives while a previous turn is `open` but not finalized
- **THEN** TurnManager SHALL emit `human_turn_cancelled` for the old turn and `human_turn_started` for the new turn
