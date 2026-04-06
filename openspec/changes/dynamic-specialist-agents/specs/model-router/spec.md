## MODIFIED Requirements

### Requirement: Router prompt template definition
The model-router SHALL consume a router configuration that conforms to the **Target API payload structure** defined in design.md. The configuration is a JSON object with this contract:

```json
{
  "identity": "str",
  "departments": {
    "<name>": {
      "description": "str",
      "triggers": ["str"],
      "fillers": ["str"],
      "tool": { "type": "internal|http", "name": "str?", "url": "str?", "auth": "str?" } | null
    }
  },
  "guardrails": ["str"],
  "language_instruction": "str"
}
```

The `tool.type` field SHALL support `"internal"` (text-model triage via built-in prompts) and `"http"` (external agent endpoint). When `type` is `"http"`, `url` MUST be a non-null, non-empty string. When `type` is `"internal"`, `url` and `auth` MAY be null. The `tool.name` field is optional for all types.

#### Scenario: JSON config loaded at startup
- **WHEN** the application starts and calls `load_router_prompt()`
- **THEN** it SHALL read the JSON file and parse it into a `RouterPromptConfig` containing `identity` (str), `departments` (dict of `DepartmentConfig`), `guardrails` (list of str), and `language_instruction` (str)

#### Scenario: HTTP tool config parsed with URL
- **WHEN** the JSON contains a department `billing` with `tool: { "type": "http", "url": "https://agents.example.com/billing", "auth": "secret-token" }`
- **THEN** the loaded `DepartmentConfig` for `billing` SHALL have `tool` as a `ToolConfig(type="http", url="https://agents.example.com/billing", auth="secret-token")`

#### Scenario: Internal tool config parsed
- **WHEN** the JSON contains a department `billing` with `tool: { "type": "internal", "name": "specialist_billing" }`
- **THEN** the loaded `DepartmentConfig` for `billing` SHALL have `tool` as a `ToolConfig(type="internal", name="specialist_billing")`

#### Scenario: HTTP type requires URL
- **WHEN** the JSON contains a department with `tool: { "type": "http", "url": null }`
- **THEN** `load_router_prompt()` SHALL raise a `ValueError` indicating that `url` is required for `type: "http"`

#### Scenario: Direct department has no tool binding
- **WHEN** the JSON contains a department `direct` with `tool: null`
- **THEN** the loaded `DepartmentConfig` for `direct` SHALL have `tool=None` and `fillers=[]`
