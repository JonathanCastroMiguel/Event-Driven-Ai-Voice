## ADDED Requirements

### Requirement: CoordinatorRuntimeState per call
The Coordinator SHALL maintain an in-memory runtime state per active call containing: `active_turn_id` (UUID | None), `active_agent_generation_id` (UUID | None), `active_voice_generation_id` (UUID | None), `cancelled_agent_generations` (set[UUID]), `cancelled_voice_generations` (set[UUID]), `idempotency_seen_event_ids` (TTLSet via Redis, 300s TTL), `idempotency_tool_results` (TTLMap via Redis, 300s TTL).

#### Scenario: State initialization on call start
- **WHEN** a new call session begins
- **THEN** Coordinator SHALL create a CoordinatorRuntimeState with all active fields set to None and empty cancelled sets

#### Scenario: State cleanup on call end
- **WHEN** a call session ends
- **THEN** Coordinator SHALL cancel any active generations, clean up all async tasks, and remove the runtime state from memory

### Requirement: Turn lifecycle orchestration
On receiving `human_turn_finalized`, the Coordinator SHALL create a new `agent_generation_id`, set it as `active_agent_generation_id`, and dispatch `handle_turn` to the Agent FSM. Before calling `Router.classify()`, the Coordinator SHALL build enriched classification inputs via `RoutingContextBuilder` when the conversation buffer is non-empty. The enriched text and LLM context SHALL be passed to `Router.classify()` as optional parameters.

#### Scenario: Simple turn (greeting)
- **WHEN** TurnManager emits `human_turn_finalized` and Agent FSM responds with `request_guided_response(policy_key="greeting")`
- **THEN** Coordinator SHALL construct the prompt (base_system + policy_block + history + user_text), emit `realtime_voice_start`, and wait for `voice_generation_completed`

#### Scenario: Turn with specialist agent
- **WHEN** Agent FSM responds with `request_agent_action(specialist="sales")`
- **THEN** Coordinator SHALL optionally emit a filler voice, execute `run_tool`, wait for `tool_result`, then emit `realtime_voice_start` with the final response

#### Scenario: Rapid successive turns
- **WHEN** a new `human_turn_finalized` arrives while a previous generation is still active
- **THEN** Coordinator SHALL cancel the previous `agent_generation_id` and `voice_generation_id` before starting the new turn

#### Scenario: Short follow-up text with multi-turn LLM context
- **WHEN** `human_turn_finalized` arrives with `text="de este mes"` (< 20 chars) AND the conversation buffer contains 2 prior turns with `user_text` values `["mi factura", "no me llega"]`
- **THEN** the Coordinator SHALL call `Router.classify(text="de este mes", language=lang, enriched_text="no me llega. de este mes", llm_context=<multi-turn context with 2 prior turns>)`

#### Scenario: Long text not enriched but LLM context still provided
- **WHEN** `human_turn_finalized` arrives with `text="quiero cambiar mi plan de datos a uno más barato"` (>= 20 chars) AND the conversation buffer is non-empty
- **THEN** the Coordinator SHALL call `Router.classify(text=..., language=lang, enriched_text=None, llm_context=<multi-turn context>)`

#### Scenario: First turn of call (no history)
- **WHEN** `human_turn_finalized` arrives and the conversation buffer is empty
- **THEN** the Coordinator SHALL call `Router.classify(text=..., language=lang)` without any enrichment parameters

### Requirement: Barge-in handling
On receiving `speech_started` while `active_voice_generation_id` is set, the Coordinator SHALL: (1) emit `realtime_voice_cancel(active_voice_generation_id)`, (2) emit `cancel_agent_generation(active_agent_generation_id)`, (3) add both IDs to their respective cancelled sets, (4) forward the event to TurnManager.

#### Scenario: Barge-in during voice output
- **WHEN** user starts speaking while bot is speaking (speech_started with active_voice_generation_id)
- **THEN** Coordinator SHALL cancel voice output and agent generation, ensuring no double response

#### Scenario: Barge-in during tool execution
- **WHEN** user starts speaking while a tool is running
- **THEN** Coordinator SHALL cancel the tool via `cancel_tool`, cancel the agent generation, and any late `tool_result` SHALL be ignored

#### Scenario: Late tool result after cancellation
- **WHEN** a `tool_result` arrives for a cancelled `agent_generation_id`
- **THEN** Coordinator SHALL check the `cancelled_agent_generations` set and discard the result silently

### Requirement: Filler strategy
When the Coordinator estimates tool latency will exceed 350ms, it SHALL emit a filler `realtime_voice_start` with `kind="filler"` and a short prompt (e.g., "Un momento, por favor."). The filler uses a separate `voice_generation_id` but the same `agent_generation_id`. The filler is fully cancellable.

#### Scenario: Filler emitted before tool result
- **WHEN** Coordinator dispatches `run_tool` and estimated latency > 350ms
- **THEN** Coordinator SHALL emit a filler `realtime_voice_start` with `kind="filler"` and a new `voice_generation_id`

#### Scenario: Final response after filler
- **WHEN** `tool_result` arrives while filler is still playing
- **THEN** Coordinator SHALL cancel the filler voice, then emit the final `realtime_voice_start` with `kind="response"` and a new `voice_generation_id`

#### Scenario: Filler max duration
- **WHEN** filler playback exceeds 1200ms
- **THEN** the filler SHALL be auto-cancelled regardless of tool status

### Requirement: Prompt construction via policy keys
The Coordinator SHALL construct prompts for `realtime_voice_start` by combining: (1) base system instruction (constant), (2) policy-key-specific instruction block from `policies.yaml`, (3) conversation history from `ConversationBuffer.format_messages()`, (4) current user text. The `policy_key` MUST be a value from the closed `PolicyKey` enum. When the conversation buffer is empty (first turn), the prompt SHALL be identical to the previous single-turn format.

#### Scenario: Prompt for greeting policy (first turn, no history)
- **WHEN** Coordinator receives `request_guided_response(policy_key="greeting", user_text="hola")` and the conversation buffer is empty
- **THEN** the prompt sent to Realtime SHALL be `[{"role":"system","content":BASE_SYSTEM}, {"role":"system","content":GREETING_POLICY}, {"role":"user","content":"hola"}]`

#### Scenario: Prompt with conversation history (subsequent turn)
- **WHEN** Coordinator receives `request_guided_response(policy_key="greeting", user_text="¿cuánto debo?")` and the buffer contains one prior turn (user: "mi factura", specialist: "billing")
- **THEN** the prompt SHALL be `[{"role":"system","content":BASE_SYSTEM}, {"role":"system","content":GREETING_POLICY}, {"role":"user","content":"mi factura"}, {"role":"assistant","content":"[domain] Specialist: billing"}, {"role":"user","content":"¿cuánto debo?"}]`

#### Scenario: Invalid policy key rejected
- **WHEN** Agent FSM sends a `policy_key` not in the PolicyKey enum
- **THEN** Coordinator SHALL log an error and use a safe fallback policy (e.g., `clarify_department`)

### Requirement: Coordinator manages ConversationBuffer lifecycle
The Coordinator SHALL create a `ConversationBuffer` at initialization (alongside `CoordinatorRuntimeState`) and append turn entries after successful prompt construction and voice start emission. The Coordinator SHALL accept `max_history_turns`, `max_history_chars`, `routing_context_window`, `routing_short_text_chars`, and `llm_context_window` as constructor parameters with defaults from application Settings.

#### Scenario: Coordinator wired with output callback
- **WHEN** a Coordinator is instantiated for a new call
- **THEN** it SHALL support `set_output_callback()` to register a callback that dispatches `RealtimeVoiceStart`, `RealtimeVoiceCancel`, and `CancelAgentGeneration` events to external consumers (e.g., the Bridge)

#### Scenario: Output events dispatched via callback
- **WHEN** the Coordinator emits a `RealtimeVoiceStart` event and an output callback is registered
- **THEN** the callback SHALL be invoked with the event, and callback errors SHALL be caught and logged without crashing the Coordinator

#### Scenario: Buffer created on Coordinator init
- **WHEN** a Coordinator is instantiated for a new call
- **THEN** it SHALL create a `ConversationBuffer` with limits from constructor parameters

#### Scenario: Turn appended to buffer after voice start
- **WHEN** the Coordinator emits a `RealtimeVoiceStart` for a guided response or specialist action
- **THEN** it SHALL append a `TurnEntry` to the conversation buffer with the current turn's user text, route_a_label, policy_key, and specialist

#### Scenario: Cancelled turn not appended
- **WHEN** a turn is cancelled due to barge-in or rapid successive turns before voice start
- **THEN** the Coordinator SHALL NOT append any entry to the conversation buffer

### Requirement: Configuration for conversation history limits
The Coordinator SHALL read `max_history_turns` (default: 10) and `max_history_chars` (default: 2000) from the application Settings and pass them to the ConversationBuffer.

#### Scenario: Custom history limits from environment
- **WHEN** `MAX_HISTORY_TURNS=5` and `MAX_HISTORY_CHARS=1000` are set in the environment
- **THEN** the ConversationBuffer SHALL use max_turns=5 and max_chars=1000

#### Scenario: Default history limits
- **WHEN** no history limit environment variables are set
- **THEN** the ConversationBuffer SHALL use max_turns=10 and max_chars=2000

### Requirement: Configuration for context-aware routing
The Coordinator SHALL read `routing_context_window` (default: 1), `routing_short_text_chars` (default: 20), and `llm_context_window` (default: 3) from the application Settings and pass them to the `RoutingContextBuilder`.

#### Scenario: Custom LLM context window from environment
- **WHEN** `LLM_CONTEXT_WINDOW=2` is set in the environment
- **THEN** the `RoutingContextBuilder` SHALL use `llm_context_window=2`

#### Scenario: Default LLM context window
- **WHEN** no `LLM_CONTEXT_WINDOW` environment variable is set
- **THEN** the `RoutingContextBuilder` SHALL use `llm_context_window=3`

#### Scenario: Custom routing context settings from environment
- **WHEN** `ROUTING_CONTEXT_WINDOW=2` and `ROUTING_SHORT_TEXT_CHARS=30` are set in the environment
- **THEN** the `RoutingContextBuilder` SHALL use `context_window=2` and `short_text_chars=30`

#### Scenario: Default routing context settings
- **WHEN** no routing context environment variables are set
- **THEN** the `RoutingContextBuilder` SHALL use `context_window=1` and `short_text_chars=20`

### Requirement: Idempotent event processing
The Coordinator SHALL deduplicate events using `event_id` checked against a Redis TTL set (300s). Duplicate events SHALL be discarded silently.

#### Scenario: Duplicate event received
- **WHEN** an event with the same `event_id` is received twice within 300 seconds
- **THEN** the second event SHALL be discarded and logged at debug level

#### Scenario: Redis unavailable for dedup
- **WHEN** Redis is unreachable during event dedup check
- **THEN** Coordinator SHALL fall back to an in-memory TTL set and log a warning

### Requirement: Idempotent tool results
Tool results SHALL be cached by `tool_request_id` in a Redis TTL map (300s). If the same tool is requested again with the same arguments, the cached result SHALL be returned without re-execution.

#### Scenario: Cached tool result
- **WHEN** a `run_tool` is requested with a `tool_request_id` that already has a cached result
- **THEN** Coordinator SHALL return the cached `tool_result` immediately without executing the tool

### Requirement: Debug event emission
When debug mode is enabled for a call, the Coordinator SHALL emit debug events for key state changes: turn updates, FSM state transitions, routing decisions, and latency measurements. Debug events SHALL be emitted to a debug callback registered by the RealtimeVoiceBridge.

#### Scenario: Turn update emitted for debug
- **WHEN** debug mode is enabled and a `human_turn_finalized` event is processed
- **THEN** the Coordinator SHALL emit a debug event with `type="turn_update"`, `turn_id`, `text`, and `state`

#### Scenario: FSM state change emitted for debug
- **WHEN** debug mode is enabled and the AgentFSM transitions state
- **THEN** the Coordinator SHALL emit a debug event with `type="fsm_state"` and the new `state`

#### Scenario: Routing decision emitted for debug
- **WHEN** debug mode is enabled and `Router.classify()` returns a result
- **THEN** the Coordinator SHALL emit a debug event with `type="routing"`, `route_a`, `route_a_confidence`, and `route_b` (if applicable)

#### Scenario: Latency measurement emitted for debug
- **WHEN** debug mode is enabled and a turn completes (from `human_turn_finalized` to `realtime_voice_start`)
- **THEN** the Coordinator SHALL emit a debug event with `type="latency"`, `metric="turn_processing_ms"`, and the elapsed time

#### Scenario: No debug overhead when disabled
- **WHEN** debug mode is NOT enabled for a call
- **THEN** the Coordinator SHALL NOT emit any debug events and SHALL NOT compute debug-only metrics
