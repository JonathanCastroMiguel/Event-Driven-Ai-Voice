## MODIFIED Requirements

### Requirement: Model router response handling
_Modifies: "Model router response handling" — specialist tool name resolution changes_

On receiving `model_router_action` from the Bridge, the Coordinator SHALL resolve the specialist tool name by calling `RouterPromptBuilder.get_department_tool(department)` instead of constructing it via `f"specialist_{department}"`. The Coordinator SHALL receive a reference to the `RouterPromptBuilder` (already available as a constructor dependency) and use its `get_department_tool` method for tool name resolution.

#### Scenario: Function call triggers specialist tool via config lookup
- **WHEN** the Bridge emits `model_router_action` with `department="retention"`
- **THEN** the Coordinator SHALL call `self._router_prompt_builder.get_department_tool("retention")` to get the tool name
- **AND** dispatch tool execution with the resolved tool name (e.g., `"specialist_retention"`)

#### Scenario: Direct department skips tool execution
- **WHEN** the Bridge emits `model_router_action` with `department="direct"`
- **THEN** `get_department_tool("direct")` SHALL return `None`
- **AND** the Coordinator SHALL follow the direct response flow without tool execution

#### Scenario: Unknown department from model
- **WHEN** the Bridge emits `model_router_action` with a department not in the config
- **THEN** `get_department_tool` SHALL return `None`
- **AND** the Coordinator SHALL log a warning and follow the direct response fallback
