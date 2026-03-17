## Tasks

### YAML restructure
- [ ] Rewrite `router_registry/v1/router_prompt.yaml` with structured format: `identity` (str), `departments` (dict with description/triggers/fillers/tool), `guardrails` (list), `language_instruction` (str). Remove `decision_rules` and flat `departments` text sections. The `tool` field is an object `{ type, name/url, auth }` for specialist departments, `null` for `direct`.

### model_router.py refactor
- [ ] Add `ToolConfig` dataclass (type: str, name: str | None, url: str | None, auth: str | None) for specialist endpoint configuration.
- [ ] Add `DepartmentConfig` dataclass (description, triggers, fillers, tool: ToolConfig | None) and `RouterPromptConfig` dataclass (identity, departments dict, guardrails list, language_instruction) replacing `RouterPromptTemplate`.
- [ ] Replace static `Department` enum with `valid_departments: set[str]` derived from config keys.
- [ ] Replace static `ROUTE_TOOL_DEFINITION` dict with `build_route_tool_definition(departments)` function that generates the tool def dynamically from department keys.
- [ ] Add `SYSTEM_MECHANIC` constant string (mandatory tool-calling rules, never vocalize function names).
- [ ] Rewrite `RouterPromptBuilder.__init__` to accept `RouterPromptConfig` and assemble system prompt from structured sections (system_mechanic + identity + generated routing rules + guardrails bullets + language_instruction).
- [ ] Add `RouterPromptBuilder.get_department_tool(department: str) -> ToolConfig | None` method. Returns the `ToolConfig` object for specialist departments, `None` for `direct` or unknown.
- [ ] Add `RouterPromptBuilder.get_department_filler(department: str) -> str | None` method (random selection from dept's fillers list, `None` if empty/unknown).
- [ ] Update `build_response_create` to use the dynamically generated tool definition.
- [ ] Update `parse_function_call_action` to accept a `valid_departments: set[str]` parameter instead of using the static `Department` enum.
- [ ] Update `load_router_prompt` to parse the new structured YAML format and return `RouterPromptConfig`. Parse `tool` field as `ToolConfig` when present.

### Coordinator update
- [ ] Update coordinator to resolve specialist tool via `self._router_prompt_builder.get_department_tool(department)` returning `ToolConfig | None` instead of `f"specialist_{department}"`. For MVP, extract tool name from `ToolConfig.name` for `internal` type tools.
- [ ] Replace hardcoded filler `"Un momento, por favor."` with `self._router_prompt_builder.get_department_filler(department)`. Skip filler emission if `None` returned.

### Test updates
- [ ] Update `test_model_router.py` — new YAML fixtures with `ToolConfig` objects, test dynamic tool definition generation, test `get_department_tool` returns `ToolConfig`, test `get_department_filler`, test structured config loading, test prompt assembly.
- [ ] Update `test_two_step_routing.py` — update fixtures for new YAML structure if needed.
- [ ] Run full test suite and fix any breakage from the refactor.
