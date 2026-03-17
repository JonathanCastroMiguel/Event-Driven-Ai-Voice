## MODIFIED Requirements

### Requirement: Router prompt template definition
_Replaces: "Router prompt template definition"_

The model-router SHALL define a router configuration stored in `router_registry/v1/router_prompt.yaml`. The configuration SHALL use structured data (not free-text prompt sections) with: (1) `identity` — agent persona as a text string, (2) `departments` — a dict where each key is a department name and each value contains `description` (str), `triggers` (list of strings), and optionally `tool` (specialist function name, absent for `direct`), (3) `guardrails` — a list of behavioral restriction strings, (4) `language_instruction` — language matching rules as a text string. The tool-calling mechanics (`system_mechanic`) SHALL be generated as a constant by the builder, not stored in the YAML.

#### Scenario: Structured YAML loaded at startup
- **WHEN** the application starts and calls `load_router_prompt()`
- **THEN** it SHALL parse the YAML into a `RouterPromptConfig` containing `identity` (str), `departments` (dict of `DepartmentConfig`), `guardrails` (list of str), and `language_instruction` (str)

#### Scenario: Department config parsed with tool binding
- **WHEN** the YAML contains a department `billing` with `tool: "specialist_billing"`
- **THEN** the loaded `DepartmentConfig` for `billing` SHALL have `tool="specialist_billing"`, `description` (str), and `triggers` (list of str)

#### Scenario: Direct department has no tool binding
- **WHEN** the YAML contains a department `direct` without a `tool` field
- **THEN** the loaded `DepartmentConfig` for `direct` SHALL have `tool=None`

#### Scenario: Missing required YAML sections
- **WHEN** the YAML is missing `identity`, `departments`, `guardrails`, or `language_instruction`
- **THEN** `load_router_prompt()` SHALL raise a `ValueError` with a descriptive message

#### Scenario: Missing router prompt file
- **WHEN** `router_prompt.yaml` does not exist at the expected path
- **THEN** the system SHALL raise a `FileNotFoundError` with a descriptive message

### Requirement: Dynamic ROUTE_TOOL_DEFINITION generation
_Replaces: part of "Department.DIRECT enum value" — tool definition is no longer static_

The `ROUTE_TOOL_DEFINITION` SHALL be generated dynamically from the loaded department configuration. The `department` parameter enum SHALL be built from the keys of the `departments` dict in the YAML. The tool description SHALL remain fixed (classify every user message).

#### Scenario: Tool definition matches YAML departments
- **WHEN** the YAML defines departments `direct`, `sales`, `billing`, `support`, `retention`
- **THEN** `ROUTE_TOOL_DEFINITION["parameters"]["properties"]["department"]["enum"]` SHALL be `["direct", "sales", "billing", "support", "retention"]`

#### Scenario: Adding a department to YAML updates tool definition
- **WHEN** a new department `escalation` is added to the YAML
- **THEN** the generated tool definition SHALL include `"escalation"` in the enum without code changes

### Requirement: Dynamic department validation
_Replaces: "Department.DIRECT enum value" — static enum replaced by runtime validation_

The system SHALL validate department names from function call arguments against the set of department keys loaded from YAML. The static `Department(str, Enum)` SHALL be replaced by a `valid_departments: set[str]` attribute on the config. `parse_function_call_action` SHALL accept the valid set and reject unknown department names.

#### Scenario: Valid department parsed
- **WHEN** `parse_function_call_action` receives `{"department": "billing", "summary": "invoice issue"}` and `billing` is in the valid set
- **THEN** it SHALL return a `ModelRouterAction` with `department="billing"`

#### Scenario: Unknown department rejected
- **WHEN** `parse_function_call_action` receives `{"department": "unknown"}` and `unknown` is NOT in the valid set
- **THEN** it SHALL return `None` and log a warning

### Requirement: RouterPromptBuilder assembles prompt from structured config
_Replaces: "RouterPromptBuilder builds response.create payloads"_

The `RouterPromptBuilder` SHALL assemble the system prompt at runtime from the structured `RouterPromptConfig`. The assembled prompt SHALL concatenate: (1) system mechanics (constant text about mandatory tool calling), (2) identity from config, (3) routing rules generated from departments (each department with its description and triggers), (4) guardrails joined as a bulleted list, (5) language instruction from config. The builder SHALL also expose `get_department_tool(department: str) -> str | None` to resolve the specialist tool name for a given department.

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
- **WHEN** `get_department_tool("billing")` is called and the config has `billing.tool = "specialist_billing"`
- **THEN** it SHALL return `"specialist_billing"`

#### Scenario: get_department_tool returns None for direct
- **WHEN** `get_department_tool("direct")` is called and `direct` has no `tool` field
- **THEN** it SHALL return `None`
