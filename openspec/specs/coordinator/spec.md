## MODIFIED Requirements

### Requirement: Turn lifecycle orchestration
On receiving `audio_committed` (translated from `input_audio_buffer.committed`), the Coordinator SHALL create a new `agent_generation_id`, set it as `active_agent_generation_id`, construct the router prompt via `RouterPromptBuilder`, and emit `realtime_voice_start` with the router prompt. The Coordinator SHALL NOT wait for `transcript_final` to begin routing. Transcription events SHALL be processed asynchronously for conversation buffer logging and persistence only.

#### Scenario: Turn triggered by audio committed
- **WHEN** the Bridge emits an `audio_committed` event after server VAD detects end of speech
- **THEN** the Coordinator SHALL create an `agent_generation_id`, build the router prompt with conversation history, and emit `realtime_voice_start` with the router prompt as instructions

#### Scenario: Transcript received after routing started
- **WHEN** `transcript_final` arrives after `audio_committed` has already triggered routing
- **THEN** the Coordinator SHALL append the transcript text to the conversation buffer and persist it, but SHALL NOT trigger any additional routing

#### Scenario: Rapid successive turns
- **WHEN** a new `audio_committed` arrives while a previous generation is still active
- **THEN** the Coordinator SHALL cancel the previous `agent_generation_id` and `voice_generation_id` before starting the new turn

#### Scenario: First turn of call (no history)
- **WHEN** `audio_committed` arrives and the conversation buffer is empty
- **THEN** the Coordinator SHALL build the router prompt with an empty input array (no conversation history)

### Requirement: Model router response handling
The Coordinator SHALL handle two response modes from the Realtime model: (a) direct voice response (model speaks the answer) and (b) JSON action (model returns specialist routing instruction). On receiving `model_router_action` from the Bridge, the Coordinator SHALL dispatch specialist tool execution. On receiving `voice_generation_completed` (direct voice), the Coordinator SHALL finalize the turn normally.

#### Scenario: Direct voice response completes
- **WHEN** the Bridge emits `voice_generation_completed` (model spoke directly)
- **THEN** the Coordinator SHALL clear `active_voice_generation_id`, finalize the agent generation as completed, and append the turn to the conversation buffer

#### Scenario: JSON action triggers specialist tool
- **WHEN** the Bridge emits `model_router_action` with `department="billing"` and `summary="billing issue"`
- **THEN** the Coordinator SHALL dispatch tool execution for the billing specialist, optionally emit a filler voice, and on tool result emit a final `realtime_voice_start` with the specialist response

#### Scenario: JSON action with filler strategy
- **WHEN** a `model_router_action` is received and filler strategy is enabled
- **THEN** the Coordinator SHALL emit a filler `realtime_voice_start` before dispatching tool execution

### Requirement: Barge-in handling
On receiving `speech_started` while `active_voice_generation_id` is set, the Coordinator SHALL: (1) emit `realtime_voice_cancel(active_voice_generation_id)`, (2) emit `cancel_agent_generation(active_agent_generation_id)`, (3) add both IDs to their respective cancelled sets, (4) forward the event to TurnManager.

#### Scenario: Barge-in during direct voice response
- **WHEN** user starts speaking while the model is speaking a direct response (speech_started with active_voice_generation_id)
- **THEN** Coordinator SHALL cancel voice output and agent generation, ensuring no double response

#### Scenario: Barge-in during specialist tool execution
- **WHEN** user starts speaking while a specialist tool is running
- **THEN** Coordinator SHALL cancel the tool via `cancel_tool`, cancel the agent generation, and any late `tool_result` SHALL be ignored

#### Scenario: Late tool result after cancellation
- **WHEN** a `tool_result` arrives for a cancelled `agent_generation_id`
- **THEN** Coordinator SHALL check the `cancelled_agent_generations` set and discard the result silently

### Requirement: Prompt construction via router prompt
The Coordinator SHALL construct prompts for `realtime_voice_start` by using `RouterPromptBuilder` to combine: (1) router prompt template (static instructions), (2) conversation history from `ConversationBuffer.format_messages()` (dynamic input). The Coordinator SHALL NOT use `PoliciesRegistry` for per-turn prompt construction — policies are embedded in the router prompt template.

#### Scenario: Router prompt with conversation history
- **WHEN** the Coordinator handles `audio_committed` and the buffer contains 2 prior turns
- **THEN** the `response.create` payload SHALL have `instructions` set to the router prompt template and `input` containing the 2 prior turns as message pairs

#### Scenario: Specialist response prompt after tool result
- **WHEN** a tool result is received for a specialist action
- **THEN** the Coordinator SHALL construct a specialist response prompt with the tool result and emit `realtime_voice_start`

### Requirement: Async transcript logging
The Coordinator SHALL process `transcript_final` events for logging purposes only. On receiving `transcript_final`, the Coordinator SHALL: (1) update the current turn's `text_final` in persistence, (2) append to conversation buffer if a turn is active, (3) emit debug event with transcript text. It SHALL NOT trigger routing or FSM transitions.

#### Scenario: Transcript logged for active turn
- **WHEN** `transcript_final` arrives with text "quiero cambiar mi plan" and a turn is active
- **THEN** the Coordinator SHALL persist the text, append to buffer, and emit a debug event, but SHALL NOT trigger any routing

#### Scenario: Transcript arrives with no active turn
- **WHEN** `transcript_final` arrives but no turn is currently active
- **THEN** the Coordinator SHALL log the transcript at debug level and discard it
