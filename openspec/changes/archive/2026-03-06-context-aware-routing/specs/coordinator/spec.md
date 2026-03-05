## MODIFIED Requirements

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

### Requirement: Configuration for context-aware routing
The Coordinator SHALL read `routing_context_window` (default: 1) and `routing_short_text_chars` (default: 20) from the application Settings and pass them to the `RoutingContextBuilder`.

#### Scenario: Custom routing context settings from environment
- **WHEN** `ROUTING_CONTEXT_WINDOW=2` and `ROUTING_SHORT_TEXT_CHARS=30` are set in the environment
- **THEN** the `RoutingContextBuilder` SHALL use `context_window=2` and `short_text_chars=30`

#### Scenario: Default routing context settings
- **WHEN** no routing context environment variables are set
- **THEN** the `RoutingContextBuilder` SHALL use `context_window=1` and `short_text_chars=20`
