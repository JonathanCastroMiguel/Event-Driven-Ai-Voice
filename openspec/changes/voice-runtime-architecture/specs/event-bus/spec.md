## ADDED Requirements

### Requirement: EventEnvelope as canonical event wrapper
All events in the runtime SHALL be wrapped in an `EventEnvelope` struct containing: `event_id` (UUID), `call_id` (UUID), `ts` (int, ms epoch or monotonic), `type` (str), `payload` (dict), `source` (Literal["realtime", "turn_manager", "agent", "coordinator", "tool_exec", "timer"]), `correlation_id` (UUID | None), and `causation_id` (UUID | None).

#### Scenario: Event creation with full traceability
- **WHEN** any actor creates an event
- **THEN** the event MUST have a unique `event_id`, the `call_id` of the active session, a monotonic `ts`, and the `source` set to the originating actor

#### Scenario: Causal chain tracking
- **WHEN** an event is created in response to another event
- **THEN** `causation_id` MUST be set to the `event_id` of the originating event, and `correlation_id` MUST be set to the `agent_generation_id` when applicable

### Requirement: asyncio.Queue as in-process event bus
The event bus SHALL be implemented as an `asyncio.Queue[EventEnvelope]`. Each actor SHALL consume events from shared or dedicated queues.

#### Scenario: Event dispatch to coordinator
- **WHEN** TurnManager emits a `human_turn_finalized` event
- **THEN** the event SHALL be placed on the coordinator's input queue and processed in FIFO order

#### Scenario: Backpressure via bounded queue
- **WHEN** the event bus queue reaches its maximum capacity
- **THEN** the producing actor SHALL await until space is available (asyncio.Queue backpressure), preventing unbounded memory growth

### Requirement: Typed event definitions
Each event type SHALL be defined as a dedicated `msgspec.Struct` (frozen=True) with typed fields. The `type` field in EventEnvelope SHALL match the struct class name in snake_case.

#### Scenario: Type safety on event creation
- **WHEN** a `human_turn_finalized` event is created
- **THEN** the payload MUST include `call_id` (UUID), `turn_id` (UUID), `text` (str), and `ts` (int) — all statically typed

#### Scenario: Unknown event type received
- **WHEN** the coordinator receives an event with an unrecognized `type`
- **THEN** it SHALL log a warning with event details and discard the event without crashing

### Requirement: Input events from Realtime to Coordinator
The system SHALL support the following inbound events from the Realtime/Transport layer: `speech_started(call_id, ts, provider_event_id?)`, `speech_stopped(call_id, ts, provider_event_id?)`, `transcript_partial(call_id, text, ts, provider_event_id?)`, `transcript_final(call_id, text, ts, provider_event_id?)`, `voice_generation_completed(call_id, voice_generation_id, ts)`, `voice_generation_error(call_id, voice_generation_id, error, ts)`.

#### Scenario: Transcript final received
- **WHEN** Realtime emits `transcript_final` with `call_id` and `text`
- **THEN** the event SHALL be forwarded to TurnManager for turn finalization

#### Scenario: Voice generation completed
- **WHEN** Realtime emits `voice_generation_completed` with a `voice_generation_id`
- **THEN** the Coordinator SHALL update the VoiceGeneration state to `completed` and clean up active state

### Requirement: TurnManager events
The system SHALL support: `human_turn_started(call_id, turn_id, ts)`, `human_turn_finalized(call_id, turn_id, text, ts)`, `human_turn_cancelled(call_id, turn_id, reason, ts)`.

#### Scenario: Turn finalized triggers agent processing
- **WHEN** TurnManager emits `human_turn_finalized`
- **THEN** Coordinator SHALL create a new `agent_generation_id` and dispatch `handle_turn` to the Agent FSM

### Requirement: Coordinator-to-Agent events
The system SHALL support: `handle_turn(call_id, turn_id, text, agent_generation_id, ts)`, `cancel_agent_generation(call_id, agent_generation_id, reason, ts)`, `voice_done(call_id, agent_generation_id, voice_generation_id, status, ts)`.

#### Scenario: Cancel agent generation on barge-in
- **WHEN** Coordinator sends `cancel_agent_generation`
- **THEN** the Agent FSM SHALL transition to `cancelled` state and stop processing for that generation

### Requirement: Agent FSM response events
The system SHALL support: `agent_state_changed(call_id, agent_generation_id, state, ts)`, `request_guided_response(call_id, agent_generation_id, policy_key, user_text, ts)`, `request_agent_action(call_id, agent_generation_id, specialist, user_text, ts)`, `request_tool_call(call_id, agent_generation_id, tool_name, args, tool_request_id?, ts)`.

#### Scenario: Guided response request
- **WHEN** Agent FSM emits `request_guided_response` with `policy_key="greeting"`
- **THEN** Coordinator SHALL construct a prompt using the policy registry and emit `realtime_voice_start`

#### Scenario: Agent action request for specialist
- **WHEN** Agent FSM emits `request_agent_action` with `specialist="billing"`
- **THEN** Coordinator SHALL optionally emit a filler, execute the relevant tool(s), and emit the final `realtime_voice_start`

### Requirement: Coordinator-to-Realtime output events
The system SHALL support: `realtime_voice_start(call_id, agent_generation_id, voice_generation_id, prompt, ts)` and `realtime_voice_cancel(call_id, voice_generation_id, reason, ts)`. Both filler and final response use `realtime_voice_start`.

#### Scenario: Voice start with structured prompt
- **WHEN** Coordinator emits `realtime_voice_start`
- **THEN** the `prompt` field SHALL contain a list of message dicts with `role` and `content` keys (base system + policy block + user text)

#### Scenario: Voice cancel on barge-in
- **WHEN** Coordinator emits `realtime_voice_cancel`
- **THEN** the Realtime layer SHALL immediately stop audio output for that `voice_generation_id`

### Requirement: Tool execution events
The system SHALL support: `run_tool(call_id, agent_generation_id, tool_request_id, tool_name, args, timeout_ms, ts)`, `cancel_tool(call_id, agent_generation_id, tool_request_id, reason, ts)`, `tool_result(call_id, agent_generation_id, tool_request_id, ok, payload, ts)`.

#### Scenario: Tool result received
- **WHEN** ToolExecutor emits `tool_result` with `ok=true`
- **THEN** Coordinator SHALL construct the final response prompt and emit `realtime_voice_start`
