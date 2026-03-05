## ADDED Requirements

### Requirement: ConversationBuffer tracks completed turns
The system SHALL provide a `ConversationBuffer` class that accumulates completed turn entries within a single call. Each entry SHALL be a frozen dataclass `TurnEntry` containing: `seq` (int), `user_text` (str), `route_a_label` (str), `policy_key` (str | None), `specialist` (str | None).

#### Scenario: Append a completed turn
- **WHEN** a turn completes successfully (voice generation started)
- **THEN** the buffer SHALL store a `TurnEntry` with the turn's seq, user text, route classification, and policy/specialist info

#### Scenario: Buffer is empty on call start
- **WHEN** a new `ConversationBuffer` is created
- **THEN** it SHALL contain zero entries

### Requirement: Sliding window pruning by max turns
The buffer SHALL enforce a configurable `max_turns` limit (default: 10). When appending a new entry would exceed `max_turns`, the oldest entry SHALL be removed first.

#### Scenario: Buffer at max capacity
- **WHEN** the buffer has `max_turns` entries and a new entry is appended
- **THEN** the oldest entry SHALL be dropped and the new entry SHALL be added at the end

#### Scenario: Buffer under capacity
- **WHEN** the buffer has fewer than `max_turns` entries
- **THEN** the new entry SHALL be appended without dropping any entries

### Requirement: Character budget pruning
The buffer SHALL enforce a configurable `max_chars` limit (default: 2000) on the total character count of all `user_text` fields. When appending a new entry would exceed `max_chars`, oldest entries SHALL be removed until the budget is satisfied.

#### Scenario: Entry exceeds remaining character budget
- **WHEN** adding a new entry would push total `user_text` characters above `max_chars`
- **THEN** oldest entries SHALL be removed one by one until the new entry fits within budget

#### Scenario: Single entry exceeds entire budget
- **WHEN** a new entry's `user_text` alone exceeds `max_chars`
- **THEN** the buffer SHALL clear all existing entries and store only the new entry (truncation is NOT applied — the entry is stored as-is)

### Requirement: Format history as chat messages
The buffer SHALL provide a `format_messages()` method that returns a `list[dict[str, str]]` of alternating user/assistant chat messages suitable for prompt injection.

#### Scenario: Format two-turn history
- **WHEN** the buffer contains two entries (seq=1: "hola", greeting) and (seq=2: "mi factura", billing)
- **THEN** `format_messages()` SHALL return:
  - `{"role": "user", "content": "hola"}`
  - `{"role": "assistant", "content": "[greeting] Guided response"}`
  - `{"role": "user", "content": "mi factura"}`
  - `{"role": "assistant", "content": "[billing] Specialist: billing"}`

#### Scenario: Format empty history
- **WHEN** the buffer is empty
- **THEN** `format_messages()` SHALL return an empty list

#### Scenario: Assistant message format for guided response
- **WHEN** a turn entry has `policy_key` set and `specialist` is None
- **THEN** the assistant message content SHALL be `[{policy_key}] Guided response`

#### Scenario: Assistant message format for specialist action
- **WHEN** a turn entry has `specialist` set
- **THEN** the assistant message content SHALL be `[{route_a_label}] Specialist: {specialist}`

### Requirement: Exclude cancelled turns
Only turns that completed successfully (voice generation was emitted) SHALL be added to the buffer. Cancelled or barge-in-interrupted turns SHALL NOT be appended.

#### Scenario: Barge-in interrupted turn not added
- **WHEN** a turn is cancelled due to barge-in before voice generation
- **THEN** the buffer SHALL NOT contain an entry for that turn

#### Scenario: Successfully completed turn added
- **WHEN** a turn completes with a `RealtimeVoiceStart` emission
- **THEN** the buffer SHALL contain an entry for that turn
