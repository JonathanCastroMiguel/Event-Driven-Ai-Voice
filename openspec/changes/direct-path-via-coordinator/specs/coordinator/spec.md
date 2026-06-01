## MODIFIED Requirements

### Requirement: Model router response handling
The Coordinator SHALL be the single dispatcher for all routing decisions emitted by the Bridge. On receiving `model_router_action` from the Bridge, the Coordinator SHALL inspect the `department` field and dispatch one of two flows:

- **Direct** (`department="direct"`): The Coordinator SHALL transition AgentFSM from `routing` to `speaking` via `voice_started`, send a `conversation.item.create` with `type="function_call_output"` (using `fn_call_id` and `output='{"status":"ok"}'`) to acknowledge the function call, then send a follow-up `response.create` containing the cached system prompt + history (no `tools`, `output_modalities=["audio"]`) so the model generates the spoken reply. No specialist tool is invoked.

- **Specialist** (`department` ∈ `{billing, sales, support, retention}`): The Coordinator SHALL transition AgentFSM `routing → waiting_tools`, resolve the specialist tool name via `RouterPromptBuilder.get_department_tool(department)`, optionally emit a filler via `RouterPromptBuilder.get_department_filler(department)`, call the specialist text model via the tool, transition `waiting_tools → speaking`, and send a `response.create` wrapping the literal text from the tool in a "Say exactly" directive instruction.

The Coordinator SHALL cache the assembled `instructions` of each dispatched `response.create` in `CoordinatorRuntimeState`, keyed by `agent_generation_id`, so the direct follow-up can reuse it without rebuilding from history. The cache entry SHALL be cleared on generation completion, cancellation, or error.

#### Scenario: Direct department dispatch sends ack and follow-up
- **WHEN** the Bridge emits `model_router_action` with `department="direct"` and includes `fn_call_id`/`fn_item_id` in the payload
- **THEN** the Coordinator SHALL transition AgentFSM `routing → speaking`
- **AND** SHALL send a `conversation.item.create` with `type="function_call_output"`, the provided `call_id`, and `output='{"status":"ok"}'`
- **AND** SHALL send a `response.create` with `output_modalities=["audio"]`, the cached `instructions` for the current `agent_generation_id`, and NO `tools` field

#### Scenario: Specialist department dispatch via config lookup
- **WHEN** the Bridge emits `model_router_action` with `department="retention"`
- **THEN** the Coordinator SHALL transition AgentFSM `routing → waiting_tools`
- **AND** call `self._router_prompt_builder.get_department_tool("retention")` to get the tool name
- **AND** dispatch tool execution with the resolved tool name (e.g., `"specialist_retention"`)

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

#### Scenario: Specialist tool failure
- **WHEN** the specialist tool returns `ok=False`
- **THEN** the Coordinator SHALL construct a fallback `response.create` with a generic apology message and emit it as `RealtimeVoiceStart`

#### Scenario: Unknown department from model
- **WHEN** the Bridge emits `model_router_action` with a department not in the config
- **THEN** `get_department_tool` SHALL return `None`
- **AND** the Coordinator SHALL log a warning and dispatch the direct flow as a safe fallback

#### Scenario: Cached instructions cleared on generation completion
- **WHEN** AgentFSM transitions to `done`, `cancelled`, or `error` for a given `agent_generation_id`
- **THEN** the Coordinator SHALL remove the cached `instructions` entry for that `agent_generation_id`

## ADDED Requirements

### Requirement: AgentFSM transitions for direct path follow natural lifecycle
The Coordinator SHALL drive AgentFSM through its natural lifecycle for the direct path: `IDLE → ROUTING` on dispatch, `ROUTING → SPEAKING` when sending the follow-up `response.create`, and `SPEAKING → DONE` on `voice_generation_completed`. The Coordinator SHALL NOT perform `voice_started + voice_completed` in a single operation in `_on_voice_completed`.

This brings the Coordinator into compliance with the existing `agent-fsm` capability spec, which already defines `routing + voice_started → speaking` as the canonical transition.

#### Scenario: Direct path uses explicit voice_started transition
- **WHEN** the Coordinator dispatches the direct follow-up `response.create`
- **THEN** the Coordinator SHALL invoke `agent_fsm.voice_started()` immediately before or after sending the follow-up so the FSM observes `routing → speaking`
- **AND** SHALL invoke `agent_fsm.voice_completed()` exactly once when `voice_generation_completed` arrives

#### Scenario: _on_voice_completed does not double-transition
- **WHEN** `voice_generation_completed` arrives for a direct turn
- **THEN** the AgentFSM SHALL already be in `speaking` (not `routing`)
- **AND** the Coordinator SHALL invoke `agent_fsm.voice_completed()` once to transition `speaking → done`

## REMOVED Requirements

### Requirement: Direct route result at response.done
**Reason**: This requirement assumed direct turns produced `voice_generation_completed` with no prior `model_router_action`. With direct-path dispatch moving to the Coordinator, every direct turn now produces a `model_router_action` first, so the "no prior action" heuristic is obsolete.
**Migration**: The `route_result(direct)` debug event SHALL be emitted by the Coordinator when it receives `model_router_action` with `department="direct"` (at dispatch time), not when `voice_generation_completed` arrives. This provides earlier visibility into the routing decision and aligns with how the specialist path emits `route_result(delegate)`.
