## MODIFIED Requirements

### Requirement: Router prompt template definition
_Replaces: "Router prompt template definition"_

The model-router SHALL consume a router configuration that conforms to the **Target API payload structure** defined in design.md. The configuration is a JSON object with this contract:

```json
{
  "identity": "str",
  "departments": {
    "<name>": {
      "description": "str",
      "triggers": ["str"],
      "fillers": ["str"],
      "tool": { "type": "internal|mcp|rag|langgraph|rest", "name": "str?", "url": "str?", "auth": "str?" } | null
    }
  },
  "guardrails": ["str"],
  "language_instruction": "str"
}
```

During MVP, this JSON is stored locally in `router_registry/v1/router_prompt.json` — the exact same structure that will arrive from the API in the future. The runtime SHALL consume this shape identically regardless of whether it was loaded from a local file or received from an API call. The `tool` field is an object with `type` (internal, mcp, rag, langgraph, rest), optional `name` (for internal), optional `url` (for remote), and optional `auth` (secret reference); or `null` for the `direct` department. The tool-calling mechanics (`system_mechanic`) SHALL be generated as a constant by the builder, not stored in the config.

#### Scenario: JSON config loaded at startup
- **WHEN** the application starts and calls `load_router_prompt()`
- **THEN** it SHALL read the JSON file and parse it into a `RouterPromptConfig` containing `identity` (str), `departments` (dict of `DepartmentConfig`), `guardrails` (list of str), and `language_instruction` (str)

#### Scenario: Department config parsed with tool binding
- **WHEN** the JSON contains a department `billing` with `tool: { type: "internal", name: "specialist_billing" }`
- **THEN** the loaded `DepartmentConfig` for `billing` SHALL have `tool` as a `ToolConfig(type="internal", name="specialist_billing")`, `description` (str), `triggers` (list of str), and `fillers` (list of str)

#### Scenario: Direct department has no tool binding
- **WHEN** the JSON contains a department `direct` with `tool: null`
- **THEN** the loaded `DepartmentConfig` for `direct` SHALL have `tool=None` and `fillers=[]`

#### Scenario: Config loaded from dict (API response)
- **WHEN** the system receives the router configuration as a Python dict (e.g., from a JSON API response) matching the target payload structure
- **THEN** `load_router_prompt_from_dict(data)` SHALL parse it into the same `RouterPromptConfig` as the file path, with identical behavior

#### Scenario: Missing required fields
- **WHEN** the JSON is missing `identity`, `departments`, `guardrails`, or `language_instruction`
- **THEN** `load_router_prompt_from_dict()` SHALL raise a `ValueError` with a descriptive message

#### Scenario: Missing router prompt file
- **WHEN** `router_prompt.json` does not exist at the expected path
- **THEN** `load_router_prompt()` SHALL raise a `FileNotFoundError` with a descriptive message

### Requirement: Dynamic ROUTE_TOOL_DEFINITION generation
_Replaces: part of "Department.DIRECT enum value" — tool definition is no longer static_

The `ROUTE_TOOL_DEFINITION` SHALL be generated dynamically from the loaded department configuration. The `department` parameter enum SHALL be built from the keys of the `departments` dict in the config. The tool description SHALL remain fixed (classify every user message).

#### Scenario: Tool definition matches config departments
- **WHEN** the config defines departments `direct`, `sales`, `billing`, `support`, `retention`
- **THEN** `ROUTE_TOOL_DEFINITION["parameters"]["properties"]["department"]["enum"]` SHALL be `["direct", "sales", "billing", "support", "retention"]`

#### Scenario: Adding a department to config updates tool definition
- **WHEN** a new department `escalation` is added to the JSON config
- **THEN** the generated tool definition SHALL include `"escalation"` in the enum without code changes

### Requirement: Dynamic department validation
_Replaces: "Department.DIRECT enum value" — static enum replaced by runtime validation_

The system SHALL validate department names from function call arguments against the set of department keys loaded from config. The static `Department(str, Enum)` SHALL be replaced by a `valid_departments: set[str]` attribute on the config. `parse_function_call_action` SHALL accept the valid set and reject unknown department names.

#### Scenario: Valid department parsed
- **WHEN** `parse_function_call_action` receives `{"department": "billing", "summary": "invoice issue"}` and `billing` is in the valid set
- **THEN** it SHALL return a `ModelRouterAction` with `department="billing"`

#### Scenario: Unknown department rejected
- **WHEN** `parse_function_call_action` receives `{"department": "unknown"}` and `unknown` is NOT in the valid set
- **THEN** it SHALL return `None` and log a warning

### Requirement: RouterPromptBuilder assembles prompt from structured config
_Replaces: "RouterPromptBuilder builds response.create payloads"_

The `RouterPromptBuilder` SHALL assemble the system prompt at runtime from the structured `RouterPromptConfig`. The assembled prompt SHALL concatenate: (1) system mechanics (constant text about mandatory tool calling), (2) identity from config, (3) routing rules generated from departments (each department with its description and triggers), (4) guardrails joined as a bulleted list, (5) language instruction from config. The builder SHALL also expose `get_department_tool(department: str) -> ToolConfig | None` to resolve the specialist tool config for a given department.

#### Scenario: Prompt assembled from config
- **WHEN** `build_response_create` is called
- **THEN** the `instructions` field SHALL contain system mechanics, identity, department routing rules, guardrails, and language instruction as a single concatenated string

#### Scenario: Department routing rules generated from config
- **WHEN** the config has departments `direct` (triggers: greetings, small talk) and `billing` (triggers: invoices, charges)
- **THEN** the routing rules section SHALL list both departments with their triggers, without duplicating information

#### Scenario: Guardrails rendered as bulleted list
- **WHEN** the config has guardrails `["Never provide medical advice", "Stay calm if user is aggressive"]`
- **THEN** the guardrails section in the prompt SHALL render them as `- Never provide medical advice\n- Stay calm if user is aggressive`

#### Scenario: Tool definition included in payload
- **WHEN** `build_response_create` is called
- **THEN** the payload SHALL include the dynamically generated `ROUTE_TOOL_DEFINITION` in `tools` and `tool_choice: "required"`

#### Scenario: get_department_tool resolves specialist tool
- **WHEN** `get_department_tool("billing")` is called and the config has `billing.tool = ToolConfig(type="internal", name="specialist_billing")`
- **THEN** it SHALL return the `ToolConfig` object

#### Scenario: get_department_tool returns None for direct
- **WHEN** `get_department_tool("direct")` is called and `direct` has `tool: null`
- **THEN** it SHALL return `None`

### Requirement: Per-department filler selection
_New requirement — replaces hardcoded filler in coordinator_

The `RouterPromptBuilder` SHALL expose `get_department_filler(department: str) -> str | None` which returns a randomly selected filler message from the department's `fillers` list. If the department has an empty `fillers` list or the department is unknown, it SHALL return `None`.

#### Scenario: Filler selected from department list
- **WHEN** `get_department_filler("billing")` is called and billing has fillers `["Let me connect you with billing", "One moment, checking your account"]`
- **THEN** it SHALL return one of the two filler strings

#### Scenario: No filler for direct department
- **WHEN** `get_department_filler("direct")` is called and direct has `fillers=[]`
- **THEN** it SHALL return `None`

#### Scenario: No filler for unknown department
- **WHEN** `get_department_filler("nonexistent")` is called
- **THEN** it SHALL return `None`
