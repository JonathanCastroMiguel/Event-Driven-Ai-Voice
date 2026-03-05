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

#### Scenario: Short follow-up text enriched before classification
- **WHEN** `human_turn_finalized` arrives with `text="de este mes"` (< 20 chars) AND the conversation buffer contains a prior turn with `user_text="tengo un problema con mi factura"`
- **THEN** the Coordinator SHALL call `Router.classify(text="de este mes", language=lang, enriched_text="tengo un problema con mi factura. de este mes", llm_context="language=es; previous_turn: tengo un problema con mi factura")`

#### Scenario: Long text not enriched
- **WHEN** `human_turn_finalized` arrives with `text="quiero cambiar mi plan de datos a uno más barato"` (>= 20 chars)
- **THEN** the Coordinator SHALL call `Router.classify(text=..., language=lang)` without enriched_text or llm_context enrichment from the context builder (llm_context may still be provided if buffer is non-empty)

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
The Coordinator SHALL create a `ConversationBuffer` at initialization (alongside `CoordinatorRuntimeState`) and append turn entries after successful prompt construction and voice start emission.

#### Scenario: Buffer created on Coordinator init
- **WHEN** a Coordinator is instantiated for a new call
- **THEN** it SHALL create a `ConversationBuffer` with limits from `Settings.max_history_turns` and `Settings.max_history_chars`

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
The Coordinator SHALL read `routing_context_window` (default: 1) and `routing_short_text_chars` (default: 20) from the application Settings and pass them to the `RoutingContextBuilder`.

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
