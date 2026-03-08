## MODIFIED Requirements

### Requirement: TurnEntry-based conversation storage

The ConversationBuffer SHALL use a TurnEntry model to store conversation turns, where each entry tracks `user_text` and `agent_text` as separately-populated fields. This replaces the previous simple dict-based storage.

#### Scenario: User transcript arrives before agent transcript
- **WHEN** a user transcript is committed via `commit_turn`
- **THEN** a new TurnEntry SHALL be created with `user_text` set and `agent_text` empty

#### Scenario: Agent transcript populates existing turn
- **WHEN** an agent transcript arrives via `set_agent_text` for the current turn
- **THEN** the existing TurnEntry's `agent_text` SHALL be updated without creating a new entry

### Requirement: Format messages includes agent responses

The `format_messages` method SHALL return both user and assistant messages from complete turns, providing accurate bidirectional history for the router prompt.

#### Scenario: Multi-turn history formatting
- **WHEN** `format_messages` is called with 3 completed turns (user + agent text)
- **THEN** the result SHALL contain 6 messages alternating user/assistant roles with correct content
