## MODIFIED Requirements

### Requirement: Model router response handling
The Coordinator SHALL handle two response modes from the Realtime model: (a) direct voice response (handled by the Bridge's two-step flow — the Coordinator receives `voice_generation_completed` as normal) and (b) function call routing (model calls `route_to_specialist()` with a specialist department). On receiving `model_router_action` from the Bridge, the Coordinator SHALL resolve the tool config by calling `RouterPromptBuilder.get_department_tool(department)`. The Coordinator SHALL also resolve the filler message by calling `RouterPromptBuilder.get_department_filler(department)`. If `get_department_filler` returns `None`, no filler SHALL be emitted.

When the tool config is resolved, the Coordinator SHALL dispatch based on `tool_config.type`:
- `"http"`: call `dispatch_http_agent(url, auth, department, summary, history, language)` from `http-agent-dispatch`
- `"internal"`: call the internal text-model triage flow (`_call_text_model` with department system prompt)
- `None` (direct): follow the direct response flow without specialist dispatch

The Coordinator SHALL NOT use `ToolExecutor` for specialist dispatch. Specialist routing bypasses the tool registry entirely.

When the dispatch returns successfully (non-None str), the Coordinator SHALL wrap the text in a `response.create` dict with a directive instruction that forces the Realtime model to speak the text exactly. When the dispatch returns `None` (failure), the Coordinator SHALL emit a fallback apology `response.create`.

Fillers SHALL play in parallel during both `http` and `internal` dispatch.

#### Scenario: Direct voice response completes
- **WHEN** the Bridge emits `voice_generation_completed` (from the two-step direct flow)
- **THEN** the Coordinator SHALL clear `active_voice_generation_id`, finalize the agent generation as completed, and append the turn to the conversation buffer

#### Scenario: HTTP agent dispatched for department
- **WHEN** the Bridge emits `model_router_action` with `department="billing"` and billing has `tool.type="http"` with a valid URL
- **THEN** the Coordinator SHALL call `dispatch_http_agent` with the URL, auth, department, summary, history, and detected language
- **AND** SHALL NOT call `ToolExecutor.execute`

#### Scenario: Internal agent dispatched for department
- **WHEN** the Bridge emits `model_router_action` with `department="billing"` and billing has `tool.type="internal"`
- **THEN** the Coordinator SHALL call the internal text-model triage flow with the department system prompt
- **AND** SHALL NOT call `ToolExecutor.execute`

#### Scenario: Direct department skips specialist dispatch
- **WHEN** the Bridge emits `model_router_action` with `department="direct"`
- **THEN** `get_department_tool("direct")` SHALL return `None`
- **AND** the Coordinator SHALL follow the direct response flow without any specialist dispatch

#### Scenario: Filler selected from department config
- **WHEN** the Bridge emits `model_router_action` with `department="billing"` and billing has fillers configured
- **THEN** the Coordinator SHALL call `get_department_filler("billing")` and emit the filler in parallel with the specialist dispatch

#### Scenario: No filler when department has empty fillers
- **WHEN** the Bridge emits `model_router_action` with a department that has `fillers=[]`
- **THEN** `get_department_filler` SHALL return `None`
- **AND** the Coordinator SHALL skip filler emission

#### Scenario: Specialist dispatch result vocalized literally
- **WHEN** the specialist dispatch (HTTP or internal) returns a `str` response
- **THEN** the Coordinator SHALL wrap the text in a `response.create` dict with a directive instruction and emit it as `RealtimeVoiceStart` with `response_source="specialist"`

#### Scenario: Specialist dispatch failure
- **WHEN** the specialist dispatch returns `None`
- **THEN** the Coordinator SHALL construct a fallback `response.create` with a generic apology message and emit it as `RealtimeVoiceStart`

#### Scenario: Unknown department from model
- **WHEN** the Bridge emits `model_router_action` with a department not in the config
- **THEN** `get_department_tool` SHALL return `None`
- **AND** the Coordinator SHALL log a warning and follow the direct response fallback

#### Scenario: Language passed to HTTP agent
- **WHEN** the Coordinator dispatches to an HTTP agent
- **THEN** it SHALL extract the customer's language from the conversation history (last user message language or default) and include it in the dispatch call

### Requirement: Specialist prompt as dict with embedded history
The Coordinator SHALL build specialist prompts as a `response.create` dict with the text model's literal response wrapped in a directive instruction. The directive SHALL instruct the Realtime model to vocalize the provided text exactly, in the customer's language, without adding, removing, or paraphrasing any content.

#### Scenario: Specialist responds in customer's language
- **WHEN** the customer spoke Spanish and the specialist dispatch generated a Spanish triage response
- **THEN** the specialist `response.create` payload SHALL contain a directive instruction wrapping the response text, ensuring the Realtime model speaks it verbatim
