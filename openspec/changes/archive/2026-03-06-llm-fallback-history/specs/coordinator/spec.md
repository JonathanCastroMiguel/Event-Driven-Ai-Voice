## MODIFIED Requirements

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
