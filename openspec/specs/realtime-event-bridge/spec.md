### Requirement: Audio committed event translation
The Bridge SHALL translate `input_audio_buffer.committed` events from OpenAI into Coordinator EventEnvelopes with `type="audio_committed"` and `source=EventSource.REALTIME`.

#### Scenario: Audio committed event received
- **WHEN** the data channel forwards an `input_audio_buffer.committed` event from OpenAI
- **THEN** the Bridge SHALL emit an EventEnvelope with `type="audio_committed"`, a new `event_id`, and the current timestamp

### Requirement: Function call routing via route_to_specialist
The Bridge SHALL handle `response.function_call_arguments.done` events from the OpenAI Realtime API. When the model calls `route_to_specialist()`, the Bridge SHALL differentiate between `department="direct"` and specialist departments:

- **Direct**: Set `_pending_direct_audio = True` and store OpenAI's `call_id` and `item_id` for later acknowledgment. Do NOT emit `model_router_action`.
- **Specialist**: Set `_function_call_received = True`, emit `model_router_action` EventEnvelope with department and summary.

Because the router prompt is sent with `tool_choice="required"`, the model produces only the function call in this response — no audio is generated. Spoken output is produced by separate follow-up responses (handled by the bridge for direct, by the coordinator for specialist).

#### Scenario: Model calls route_to_specialist with direct department
- **WHEN** a `response.function_call_arguments.done` event arrives with `department="direct"`
- **THEN** the Bridge SHALL set `_pending_direct_audio = True`, store `_pending_fn_call_id` and `_pending_fn_item_id`, and NOT emit any routing event

#### Scenario: Model calls route_to_specialist with specialist department
- **WHEN** a `response.function_call_arguments.done` event arrives with `department="billing"`
- **THEN** the Bridge SHALL set `_function_call_received = True`, emit `model_router_action` with `payload={"department": "billing", "summary": "..."}`, and clear `_active_voice_generation_id`

#### Scenario: Invalid function call name
- **WHEN** a `response.function_call_arguments.done` event arrives with an unexpected function name
- **THEN** the Bridge SHALL log a warning and not emit any routing event

### Requirement: Response transcript accumulation
The Bridge SHALL maintain a `_response_transcript_buffer` (string) that accumulates text from `response.audio_transcript.delta` events. The buffer SHALL be reset on each new `response.created` event. The accumulated transcript is included in the `voice_generation_completed` envelope payload so that the conversation buffer can store the agent's spoken response.

The buffer is empty for the initial classification response (because `tool_choice="required"` suppresses audio) and populated for the audio-bearing follow-up responses (direct two-step audio and specialist "say exactly" responses).

#### Scenario: Transcript accumulated across deltas during a spoken response
- **WHEN** multiple `response.audio_transcript.delta` events arrive during a spoken response with text "Buenos ", "días, ", "¿en qué puedo ayudarle?"
- **THEN** the Bridge SHALL accumulate the full text `Buenos días, ¿en qué puedo ayudarle?` in the buffer

#### Scenario: Buffer reset on new response
- **WHEN** a new `response.created` event arrives
- **THEN** the Bridge SHALL clear the `_response_transcript_buffer` to empty string

### Requirement: OpenAI event to EventEnvelope translation (input direction)
The bridge SHALL translate incoming OpenAI Realtime events into Coordinator EventEnvelopes. The following event types SHALL be translated: `input_audio_buffer.speech_started` → `speech_started`, `input_audio_buffer.speech_stopped` → `speech_stopped`, `input_audio_buffer.committed` → `audio_committed`, `conversation.item.input_audio_transcription.completed` → `transcript_final`, `response.function_call_arguments.done` → `model_router_action` (only if specialist department, not direct), `response.done` → `voice_generation_completed` (only for direct follow-up and specialist responses, not for the initial classification response), `response.failed` → `voice_generation_error`.

#### Scenario: Committed event translation
- **WHEN** the data channel forwards `input_audio_buffer.committed`
- **THEN** the Bridge SHALL emit an EventEnvelope with `type="audio_committed"` and `source=EventSource.REALTIME`

#### Scenario: Function call with direct triggers no routing event
- **WHEN** `response.function_call_arguments.done` arrives with `department="direct"`
- **THEN** the Bridge SHALL NOT emit `model_router_action`

#### Scenario: Function call with specialist triggers routing event
- **WHEN** `response.function_call_arguments.done` arrives with `department="billing"`
- **THEN** the Bridge SHALL emit `model_router_action` with department and summary

#### Scenario: Response done after specialist classification
- **WHEN** `response.done` fires and `_function_call_received` is True
- **THEN** the Bridge SHALL NOT emit `voice_generation_completed` — the specialist's own response.done will handle it

#### Scenario: Response done after direct follow-up
- **WHEN** `response.done` fires for the second `response.create` (direct audio follow-up) and `_function_call_received` is False
- **THEN** the Bridge SHALL emit `voice_generation_completed` with the transcript normally

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

### Requirement: Two-step direct response flow
When the model classifies a message as `department="direct"`, the Bridge SHALL execute a two-step flow: (1) on `response.done` after classification, acknowledge the function call via `conversation.item.create` with `type="function_call_output"`, then (2) send a second `response.create` WITHOUT tools so the model generates the spoken reply.

#### Scenario: Function call acknowledged before follow-up
- **WHEN** `response.done` fires with `_pending_direct_audio = True`
- **THEN** the Bridge SHALL send a `conversation.item.create` message with `type="function_call_output"`, `call_id` matching the pending function call, and `output='{"status":"ok"}'`
- **AND** the Bridge SHALL then send a `response.create` with `modalities: ["text", "audio"]`, the original `instructions`, and NO `tools` or `tool_choice`

#### Scenario: Second response generates audio
- **WHEN** the second `response.create` (without tools) is sent
- **THEN** the model SHALL generate a spoken response based on the instructions and conversation context
- **AND** the Bridge SHALL process this response's `response.done` as a normal direct voice response

#### Scenario: Transcript buffer reset between steps
- **WHEN** the two-step direct flow transitions from classification to audio follow-up
- **THEN** the Bridge SHALL reset `_response_transcript_buffer` to empty string before the second response

### Requirement: Bridge state tracking for pending function calls
The Bridge SHALL maintain `_pending_fn_call_id` and `_pending_fn_item_id` fields captured from `response.function_call_arguments.done` events. These are used to acknowledge the function call before sending a follow-up `response.create`.

#### Scenario: Function call IDs captured
- **WHEN** a `response.function_call_arguments.done` event arrives
- **THEN** the Bridge SHALL store `data.call_id` as `_pending_fn_call_id` and `data.item_id` as `_pending_fn_item_id`

#### Scenario: Function call IDs cleared after acknowledgment
- **WHEN** the function call is acknowledged via `function_call_output`
- **THEN** the Bridge SHALL clear `_pending_fn_call_id` and `_pending_fn_item_id` to empty strings

### Requirement: Last instructions caching
The Bridge SHALL cache the `instructions` field from the most recent `response.create` payload sent to the frontend. This cached value is used for the second `response.create` in the two-step direct flow.

#### Scenario: Instructions cached on send
- **WHEN** `send_voice_start` processes a `response.create` payload with `instructions`
- **THEN** the Bridge SHALL store the instructions in `_last_instructions`

#### Scenario: Cached instructions used for follow-up
- **WHEN** the two-step direct flow sends the second `response.create`
- **THEN** the `instructions` field SHALL be set to `_last_instructions`
