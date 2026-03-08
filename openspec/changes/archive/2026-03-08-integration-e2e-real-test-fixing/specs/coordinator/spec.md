## ADDED Requirements

### Requirement: Pipeline timing instrumentation

The Coordinator SHALL log ms-level timing at every event handler boundary, enabling production latency debugging.

Required timing points:
- `speech_started`: record `turn_speech_started_ms`
- `audio_committed`: log `speech_to_committed_ms` (delta from speech_started)
- `model_router_dispatched`: log `dispatch_elapsed_ms` (time to build and send prompt), `speech_to_dispatch_ms` (total from speech start)
- `transcript_final`: log `transcript_elapsed_ms` (delta from audio_committed)
- `model_router_action`: log `routing_elapsed_ms` (delta from dispatch)
- `voice_generation_completed`: log `voice_elapsed_ms` (delta from dispatch), `total_turn_ms` (full turn duration)

#### Scenario: Timing logged for complete turn
- **WHEN** a full voice turn completes (speech_started → voice_generation_completed)
- **THEN** structured logs SHALL include `total_turn_ms` and per-stage deltas

### Requirement: FSM state transition logging

The Coordinator SHALL log every FSM state transition with the format `fsm_<event_name>` including from/to states.

#### Scenario: Routing transition logged
- **WHEN** the FSM transitions from idle to routing after audio_committed
- **THEN** a structured log SHALL be emitted with `fsm_transition` from `idle` to `routing`

## MODIFIED Requirements

### Requirement: Fallback prompt uses instructions-based history

When the router prompt is not available and the Coordinator falls back to a default prompt, conversation history SHALL be embedded in the `instructions` field (not `response.input`), consistent with the RouterPromptBuilder behavior.

#### Scenario: Fallback with history
- **WHEN** the Coordinator uses the fallback prompt path with existing conversation history
- **THEN** the `response.create` payload SHALL contain history in `instructions` and MUST NOT contain a `response.input` field
