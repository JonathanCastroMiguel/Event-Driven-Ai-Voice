### Requirement: Audio committed event translation
The Bridge SHALL translate `input_audio_buffer.committed` events from OpenAI into Coordinator EventEnvelopes with `type="audio_committed"` and `source=EventSource.REALTIME`.

#### Scenario: Audio committed event received
- **WHEN** the data channel forwards an `input_audio_buffer.committed` event from OpenAI
- **THEN** the Bridge SHALL emit an EventEnvelope with `type="audio_committed"`, a new `event_id`, and the current timestamp

### Requirement: Function call routing via route_to_specialist
The Bridge SHALL handle `response.function_call_arguments.done` events from the OpenAI Realtime API. When the model calls `route_to_specialist()`, the Bridge SHALL validate the function call via `parse_function_call_action()` and emit a `model_router_action` EventEnvelope. The Bridge SHALL also accumulate the filler transcript from `response.audio_transcript.delta` events that accompany the function call.

#### Scenario: Model calls route_to_specialist function
- **WHEN** a `response.function_call_arguments.done` event arrives with `name="route_to_specialist"` and valid JSON arguments `{"department": "billing", "summary": "billing issue"}`
- **THEN** the Bridge SHALL emit an EventEnvelope with `type="model_router_action"` and `payload={"department": "billing", "summary": "billing issue", "filler_text": "..."}`, set `_function_call_received = True`, and clear `_active_voice_generation_id`

#### Scenario: Model responds with direct voice (no function call)
- **WHEN** `response.done` fires and `_function_call_received` is False
- **THEN** the Bridge SHALL emit `voice_generation_completed` normally

#### Scenario: Function call response completes
- **WHEN** `response.done` fires and `_function_call_received` is True
- **THEN** the Bridge SHALL emit `voice_generation_completed` with the filler transcript

#### Scenario: Invalid function call name
- **WHEN** a `response.function_call_arguments.done` event arrives with an unexpected function name
- **THEN** the Bridge SHALL log a warning and not emit any routing event

### Requirement: Transcript accumulation for action detection
The Bridge SHALL maintain a `_response_transcript_buffer` (string) that accumulates text from `response.audio_transcript.delta` events. The buffer SHALL be reset on each new `response.created` event.

#### Scenario: Transcript accumulated across deltas
- **WHEN** three `response.audio_transcript.delta` events arrive with text "{ ", "\"action\":", " \"specialist\"}"
- **THEN** the Bridge SHALL accumulate the full text `{"action": "specialist"}` in the buffer

#### Scenario: Buffer reset on new response
- **WHEN** a new `response.created` event arrives
- **THEN** the Bridge SHALL clear the `_response_transcript_buffer` to empty string

### Requirement: OpenAI event to EventEnvelope translation (input direction)
The bridge SHALL translate incoming OpenAI Realtime events into Coordinator EventEnvelopes. The following event types SHALL be translated: `input_audio_buffer.speech_started` → `speech_started`, `input_audio_buffer.speech_stopped` → `speech_stopped`, `input_audio_buffer.committed` → `audio_committed`, `conversation.item.input_audio_transcription.completed` → `transcript_final`, `response.function_call_arguments.done` → `model_router_action` (if `route_to_specialist` function call), `response.done` → `voice_generation_completed`, `response.failed` → `voice_generation_error`.

#### Scenario: Committed event translation
- **WHEN** the data channel forwards `input_audio_buffer.committed`
- **THEN** the Bridge SHALL emit an EventEnvelope with `type="audio_committed"` and `source=EventSource.REALTIME`

#### Scenario: Function call triggers routing
- **WHEN** `response.function_call_arguments.done` arrives with a valid `route_to_specialist` call
- **THEN** the Bridge SHALL emit `model_router_action` with department, summary, and filler_text

#### Scenario: Response done after function call
- **WHEN** `response.done` fires and `_function_call_received` is True
- **THEN** the Bridge SHALL emit `voice_generation_completed` with the filler transcript

#### Scenario: Response done without function call
- **WHEN** `response.done` fires and `_function_call_received` is False
- **THEN** the Bridge SHALL emit `voice_generation_completed` normally

### Requirement: Server VAD configuration in session update
The one-time `session.update` sent on WebSocket connection SHALL include `silence_duration_ms` in the `turn_detection` configuration. The value SHALL be configurable via the `VAD_SILENCE_DURATION_MS` environment variable (default: 500).

#### Scenario: Session update with custom silence duration
- **WHEN** `VAD_SILENCE_DURATION_MS=300` is set in the environment
- **THEN** the `session.update` SHALL include `turn_detection.silence_duration_ms: 300`

#### Scenario: Session update with default silence duration
- **WHEN** no `VAD_SILENCE_DURATION_MS` environment variable is set
- **THEN** the `session.update` SHALL include `turn_detection.silence_duration_ms: 500`

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

### Requirement: Bridge handles dict prompt with history detection

When `send_voice_start` receives a dict prompt (from RouterPromptBuilder), the bridge SHALL log whether conversation history is present by checking for `Conversation history:` in the instructions field.

#### Scenario: Dict prompt with history
- **WHEN** `send_voice_start` receives a dict prompt containing `Conversation history:` in instructions
- **THEN** the bridge SHALL log `has_history=True` and `instructions_len`

### Requirement: Response source tracking

The bridge SHALL track whether the current response is from the router or a specialist, and include `response_source` in EventEnvelope payloads.

#### Scenario: Router response source
- **WHEN** `send_voice_start` is called for a router prompt
- **THEN** `_current_response_source` SHALL be set to `"router"` and included in `response_created` and `voice_generation_completed` payloads

#### Scenario: Specialist response source
- **WHEN** `send_voice_start` is called for a specialist prompt with `response_source="specialist"`
- **THEN** `_current_response_source` SHALL be set to `"specialist"` and included in payloads

### Requirement: Timing metrics in EventEnvelope payloads

The bridge SHALL include `send_to_created_ms` in `response_created` payloads and `created_to_done_ms` in `voice_generation_completed` payloads. Values of 0 SHALL be omitted.

#### Scenario: Timing included in response_created
- **WHEN** `response.created` arrives 150ms after `response.create` was sent
- **THEN** the `response_created` EventEnvelope payload SHALL include `send_to_created_ms: 150`

#### Scenario: Timing included in voice_generation_completed
- **WHEN** `response.done` arrives 2000ms after `response.created`
- **THEN** the `voice_generation_completed` EventEnvelope payload SHALL include `created_to_done_ms: 2000`
