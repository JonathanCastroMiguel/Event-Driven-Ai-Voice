## ADDED Requirements

### Requirement: Audio committed event translation
The Bridge SHALL translate `input_audio_buffer.committed` events from OpenAI into Coordinator EventEnvelopes with `type="audio_committed"` and `source=EventSource.REALTIME`.

#### Scenario: Audio committed event received
- **WHEN** the data channel forwards an `input_audio_buffer.committed` event from OpenAI
- **THEN** the Bridge SHALL emit an EventEnvelope with `type="audio_committed"`, a new `event_id`, and the current timestamp

### Requirement: JSON action detection from model response
The Bridge SHALL accumulate text from `response.audio_transcript.delta` events during an active voice generation. On `response.done`, if the accumulated transcript is a valid JSON action (parsed by `parse_model_action`), the Bridge SHALL emit a `model_router_action` EventEnvelope instead of `voice_generation_completed`.

#### Scenario: Model responds with JSON action
- **WHEN** the accumulated transcript from `response.audio_transcript.delta` events is `{"action": "specialist", "department": "billing", "summary": "billing issue"}` and `response.done` fires
- **THEN** the Bridge SHALL emit an EventEnvelope with `type="model_router_action"` and `payload={"department": "billing", "summary": "billing issue"}`, and SHALL NOT emit `voice_generation_completed`

#### Scenario: Model responds with direct voice
- **WHEN** the accumulated transcript is "Buenos días, ¿en qué puedo ayudarle?" and `response.done` fires
- **THEN** the Bridge SHALL emit `voice_generation_completed` normally (no JSON action detected)

#### Scenario: Malformed JSON falls back to voice completed
- **WHEN** the accumulated transcript starts with `{` but fails JSON parsing and `response.done` fires
- **THEN** the Bridge SHALL emit `voice_generation_completed`, log a warning, and reset the transcript accumulator

### Requirement: Transcript accumulation for action detection
The Bridge SHALL maintain a `_response_transcript_buffer` (string) that accumulates text from `response.audio_transcript.delta` events. The buffer SHALL be reset on each new `response.created` event.

#### Scenario: Transcript accumulated across deltas
- **WHEN** three `response.audio_transcript.delta` events arrive with text "{ ", "\"action\":", " \"specialist\"}"
- **THEN** the Bridge SHALL accumulate the full text `{"action": "specialist"}` in the buffer

#### Scenario: Buffer reset on new response
- **WHEN** a new `response.created` event arrives
- **THEN** the Bridge SHALL clear the `_response_transcript_buffer` to empty string

## MODIFIED Requirements

### Requirement: OpenAI event to EventEnvelope translation (input direction)
The bridge SHALL translate incoming OpenAI Realtime events into Coordinator EventEnvelopes. The following event types SHALL be translated: `input_audio_buffer.speech_started` → `speech_started`, `input_audio_buffer.speech_stopped` → `speech_stopped`, `input_audio_buffer.committed` → `audio_committed`, `conversation.item.input_audio_transcription.completed` → `transcript_final`, `response.done` → `voice_generation_completed` OR `model_router_action` (depending on JSON action detection), `response.failed` → `voice_generation_error`.

#### Scenario: Committed event translation
- **WHEN** the data channel forwards `input_audio_buffer.committed`
- **THEN** the Bridge SHALL emit an EventEnvelope with `type="audio_committed"` and `source=EventSource.REALTIME`

#### Scenario: Response done with JSON action
- **WHEN** `response.done` fires and the accumulated transcript is a valid JSON action
- **THEN** the Bridge SHALL emit `model_router_action` instead of `voice_generation_completed`

#### Scenario: Response done without JSON action
- **WHEN** `response.done` fires and the accumulated transcript is not JSON
- **THEN** the Bridge SHALL emit `voice_generation_completed` as before

### Requirement: Server VAD configuration in session update
The one-time `session.update` sent on WebSocket connection SHALL include `silence_duration_ms` in the `turn_detection` configuration. The value SHALL be configurable via the `VAD_SILENCE_DURATION_MS` environment variable (default: 500).

#### Scenario: Session update with custom silence duration
- **WHEN** `VAD_SILENCE_DURATION_MS=300` is set in the environment
- **THEN** the `session.update` SHALL include `turn_detection.silence_duration_ms: 300`

#### Scenario: Session update with default silence duration
- **WHEN** no `VAD_SILENCE_DURATION_MS` environment variable is set
- **THEN** the `session.update` SHALL include `turn_detection.silence_duration_ms: 500`
