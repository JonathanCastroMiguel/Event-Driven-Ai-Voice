## ADDED Requirements

### Requirement: Per-session debug mode flag

The Coordinator SHALL maintain a `_debug_enabled: bool` flag per session, defaulting to `False`. When `True`, the Coordinator emits debug events via the bridge's `send_to_frontend()`. When `False`, no debug events are emitted — zero overhead.

#### Scenario: Debug disabled by default
- **WHEN** a new call session is created
- **THEN** `_debug_enabled` SHALL be `False` and no debug events are emitted

#### Scenario: Debug enabled mid-session
- **WHEN** the Coordinator receives a `debug_enable` control message
- **THEN** `_debug_enabled` SHALL be set to `True` and subsequent pipeline events SHALL emit corresponding debug events

#### Scenario: Debug disabled mid-session
- **WHEN** the Coordinator receives a `debug_disable` control message
- **THEN** `_debug_enabled` SHALL be set to `False` and no further debug events are emitted

### Requirement: Structured debug event emission

When debug is enabled, the Coordinator SHALL emit a `debug_event` message for each pipeline stage via `send_to_frontend()`. Each event MUST include:
- `type`: always `"debug_event"`
- `turn_id`: UUID assigned at `speech_start`, consistent across all events for that turn
- `stage`: one of `speech_start`, `speech_stop`, `audio_committed`, `prompt_sent`, `model_processing`, `route_result`, `fill_silence`, `generation_start`, `generation_finish`, `barge_in`, `specialist_sent`, `specialist_processing`, `specialist_ready`
- `delta_ms`: milliseconds since the previous stage in this turn (0 for the first event)
- `total_ms`: milliseconds since `speech_start` for this turn
- `ts`: epoch milliseconds

For `route_result` stage, the event MUST also include:
- `label`: the routing label (e.g., `greeting`, `sales`, `billing`, `support`, `retention`)
- `route_type`: `"direct"` if the model speaks directly, `"delegate"` if routing to a specialist

The stages `prompt_sent`, `model_processing`, and `route_result` decompose the previously opaque gap between audio commit and route result:
- `audio_committed` → `prompt_sent`: prompt building time (RouterPromptBuilder)
- `prompt_sent` → `model_processing`: network RTT to OpenAI
- `model_processing` → `route_result`: model inference time

#### Scenario: Direct route turn emits all main stages
- **WHEN** a direct-response turn completes (speech_start → speech_stop → audio_committed → prompt_sent → model_processing → route_result(direct) → generation_start → generation_finish)
- **THEN** 8 debug events SHALL be emitted with consistent `turn_id`, incrementing `delta_ms` and `total_ms`

#### Scenario: Delegate route turn emits main + specialist + fill_silence stages
- **WHEN** a delegate turn completes (route_result(delegate) → fill_silence + specialist_sent → specialist_processing → specialist_ready → generation_start → generation_finish)
- **THEN** a `fill_silence` stage SHALL be emitted on the main flow when the Coordinator launches silence-filling while waiting for the specialist
- **AND** the specialist sub-flow stages SHALL be emitted with the same `turn_id` and cumulative timing from `speech_start`

#### Scenario: Barge-in emits truncated timeline
- **WHEN** a barge-in occurs during generation
- **THEN** a `barge_in` debug event SHALL be emitted and no `generation_finish` event is sent for that turn

#### Scenario: Debug disabled emits nothing
- **WHEN** `_debug_enabled` is `False`
- **THEN** no debug events SHALL be emitted regardless of pipeline activity
