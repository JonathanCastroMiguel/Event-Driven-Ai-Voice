## ADDED Requirements

### Requirement: OpenAI round-trip timing

The bridge SHALL measure and log timing for the OpenAI Realtime API round-trip:
- `send_to_created_ms`: time from sending `response.create` to receiving `response.created`
- `created_to_done_ms`: time from `response.created` to `response.done`
- `total_response_ms`: time from sending `response.create` to `response.done`

#### Scenario: Response timing logged
- **WHEN** a response cycle completes (response.create sent → response.done received)
- **THEN** structured logs SHALL include `send_to_created_ms`, `created_to_done_ms`, and `total_response_ms`

### Requirement: Agent transcript in voice_generation_completed

The bridge SHALL include the accumulated response transcript in the `voice_generation_completed` event payload, enabling the conversation buffer to store agent responses.

#### Scenario: Transcript included in completion event
- **WHEN** `response.done` is received with a non-empty transcript buffer
- **THEN** the `voice_generation_completed` EventEnvelope payload SHALL include `transcript` with the full response text

## MODIFIED Requirements

### Requirement: Bridge handles dict prompt with history detection

When `send_voice_start` receives a dict prompt (from RouterPromptBuilder), the bridge SHALL log whether conversation history is present by checking for `Conversation history:` in the instructions field.

#### Scenario: Dict prompt with history
- **WHEN** `send_voice_start` receives a dict prompt containing `Conversation history:` in instructions
- **THEN** the bridge SHALL log `has_history=True` and `instructions_len`
