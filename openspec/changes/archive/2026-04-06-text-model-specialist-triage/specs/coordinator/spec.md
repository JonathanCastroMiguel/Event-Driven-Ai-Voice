## MODIFIED Requirements

### Requirement: Model router response handling
The Coordinator SHALL handle two response modes from the Realtime model: (a) direct voice response (handled by the Bridge's two-step flow — the Coordinator receives `voice_generation_completed` as normal) and (b) function call routing (model calls `route_to_specialist()` with a specialist department). On receiving `model_router_action` from the Bridge, the Coordinator SHALL resolve the specialist tool name by calling `RouterPromptBuilder.get_department_tool(department)` instead of constructing it via `f"specialist_{department}"`. The Coordinator SHALL also resolve the filler message by calling `RouterPromptBuilder.get_department_filler(department)` instead of the hardcoded `"Un momento, por favor."`. If `get_department_filler` returns `None`, no filler SHALL be emitted. The Coordinator SHALL receive a reference to the `RouterPromptBuilder` (already available as a constructor dependency) and use its methods for both tool name and filler resolution.

When the specialist tool returns successfully, the Coordinator SHALL treat the tool result payload as a **literal text string** to be vocalized. The Coordinator SHALL wrap this text in a `response.create` dict with a directive instruction that forces the Realtime model to speak the text exactly as provided, without paraphrasing or adding content.

#### Scenario: Direct voice response completes
- **WHEN** the Bridge emits `voice_generation_completed` (from the two-step direct flow)
- **THEN** the Coordinator SHALL clear `active_voice_generation_id`, finalize the agent generation as completed, and append the turn to the conversation buffer

#### Scenario: Function call triggers specialist tool via config lookup
- **WHEN** the Bridge emits `model_router_action` with `department="retention"`
- **THEN** the Coordinator SHALL call `self._router_prompt_builder.get_department_tool("retention")` to get the tool name
- **AND** dispatch tool execution with the resolved tool name (e.g., `"specialist_retention"`)

#### Scenario: Direct department skips tool execution
- **WHEN** the Bridge emits `model_router_action` with `department="direct"`
- **THEN** `get_department_tool("direct")` SHALL return `None`
- **AND** the Coordinator SHALL follow the direct response flow without tool execution

#### Scenario: Filler selected from department config
- **WHEN** the Bridge emits `model_router_action` with `department="billing"` and billing has fillers configured
- **THEN** the Coordinator SHALL call `get_department_filler("billing")` and use the returned string as the `prompt` in `RealtimeVoiceStart`

#### Scenario: No filler when department has empty fillers
- **WHEN** the Bridge emits `model_router_action` with a department that has `fillers=[]`
- **THEN** `get_department_filler` SHALL return `None`
- **AND** the Coordinator SHALL skip filler emission (no `RealtimeVoiceStart`)

#### Scenario: Specialist tool result vocalized literally
- **WHEN** the specialist tool returns `ok=True` with a `str` payload (text model response)
- **THEN** the Coordinator SHALL wrap the text in a `response.create` dict with a directive instruction (e.g., "Say exactly the following to the customer: <text>") and emit it as `RealtimeVoiceStart` with `response_source="specialist"`
- **AND** the Coordinator SHALL NOT forward the raw text as a plain string prompt

#### Scenario: Specialist tool failure
- **WHEN** the specialist tool returns `ok=False`
- **THEN** the Coordinator SHALL construct a fallback `response.create` with a generic apology message and emit it as `RealtimeVoiceStart`

#### Scenario: Unknown department from model
- **WHEN** the Bridge emits `model_router_action` with a department not in the config
- **THEN** `get_department_tool` SHALL return `None`
- **AND** the Coordinator SHALL log a warning and follow the direct response fallback

### Requirement: Specialist prompt as dict with embedded history
The Coordinator SHALL build specialist prompts as a `response.create` dict with the text model's literal response wrapped in a directive instruction. The directive SHALL instruct the Realtime model to vocalize the provided text exactly, in the customer's language, without adding, removing, or paraphrasing any content.

#### Scenario: Specialist responds in customer's language
- **WHEN** the customer spoke Spanish and the text model generated a Spanish triage response
- **THEN** the specialist `response.create` payload SHALL contain a directive instruction wrapping the text model's response, ensuring the Realtime model speaks it verbatim
