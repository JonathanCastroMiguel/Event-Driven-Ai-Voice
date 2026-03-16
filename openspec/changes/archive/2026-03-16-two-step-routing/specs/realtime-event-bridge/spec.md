## MODIFIED Requirements

### Requirement: Function call routing via route_to_specialist
The Bridge SHALL handle `response.function_call_arguments.done` events from the OpenAI Realtime API. When the model calls `route_to_specialist()`, the Bridge SHALL differentiate between `department="direct"` and specialist departments:

- **Direct**: Set `_pending_direct_audio = True` and store OpenAI's `call_id` and `item_id` for later acknowledgment. Do NOT emit `model_router_action`.
- **Specialist**: Set `_function_call_received = True`, emit `model_router_action` EventEnvelope with department, summary, and filler_text.

#### Scenario: Model calls route_to_specialist with direct department
- **WHEN** a `response.function_call_arguments.done` event arrives with `department="direct"`
- **THEN** the Bridge SHALL set `_pending_direct_audio = True`, store `_pending_fn_call_id` and `_pending_fn_item_id`, and NOT emit any routing event

#### Scenario: Model calls route_to_specialist with specialist department
- **WHEN** a `response.function_call_arguments.done` event arrives with `department="billing"`
- **THEN** the Bridge SHALL set `_function_call_received = True`, emit `model_router_action` with `payload={"department": "billing", "summary": "...", "filler_text": "..."}`, and clear `_active_voice_generation_id`

#### Scenario: Invalid function call name
- **WHEN** a `response.function_call_arguments.done` event arrives with an unexpected function name
- **THEN** the Bridge SHALL log a warning and not emit any routing event

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
- **THEN** the Bridge SHALL emit `model_router_action` with department, summary, and filler_text

#### Scenario: Response done after specialist classification
- **WHEN** `response.done` fires and `_function_call_received` is True
- **THEN** the Bridge SHALL NOT emit `voice_generation_completed` — the specialist's own response.done will handle it

#### Scenario: Response done after direct follow-up
- **WHEN** `response.done` fires for the second `response.create` (direct audio follow-up) and `_function_call_received` is False
- **THEN** the Bridge SHALL emit `voice_generation_completed` with the transcript normally

## ADDED Requirements

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
