## Tasks

### YAML restructure
- [ ] Rewrite `router_registry/v1/router_prompt.yaml` with structured format: `identity` (str), `departments` (dict with description/triggers/tool), `guardrails` (list), `language_instruction` (str). Remove `decision_rules` and flat `departments` text sections.

### model_router.py refactor
- [ ] Add `DepartmentConfig` dataclass (description, triggers, tool) and `RouterPromptConfig` dataclass (identity, departments dict, guardrails list, language_instruction) replacing `RouterPromptTemplate`.
- [ ] Replace static `Department` enum with `valid_departments: set[str]` derived from config keys.
- [ ] Replace static `ROUTE_TOOL_DEFINITION` dict with `build_route_tool_definition(departments)` function that generates the tool def dynamically from department keys.
- [ ] Add `SYSTEM_MECHANIC` constant string (mandatory tool-calling rules, never vocalize function names).
- [ ] Rewrite `RouterPromptBuilder.__init__` to accept `RouterPromptConfig` and assemble system prompt from structured sections (system_mechanic + identity + generated routing rules + guardrails bullets + language_instruction).
- [ ] Add `RouterPromptBuilder.get_department_tool(department: str) -> str | None` method.
- [ ] Update `build_response_create` to use the dynamically generated tool definition.
- [ ] Update `parse_function_call_action` to accept a `valid_departments: set[str]` parameter instead of using the static `Department` enum.
- [ ] Update `load_router_prompt` to parse the new structured YAML format and return `RouterPromptConfig`.

### Coordinator update
- [ ] Update coordinator to resolve specialist tool name via `self._router_prompt_builder.get_department_tool(department)` instead of `f"specialist_{department}"`.

### Test updates
- [ ] Update `test_model_router.py` — new YAML fixtures, test dynamic tool definition generation, test `get_department_tool`, test structured config loading, test prompt assembly.
- [ ] Update `test_two_step_routing.py` — update fixtures for new YAML structure if needed.
- [ ] Run full test suite and fix any breakage from the refactor.
