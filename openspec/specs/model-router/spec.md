### Requirement: Router prompt template definition
The model-router SHALL define a router system prompt template stored in `router_registry/v1/router_prompt.yaml`. The template SHALL contain sections for: (1) base system identity (call center agent persona), (2) router decision rules (when to speak directly vs. return JSON), (3) department definitions (sales, billing, support, retention), (4) guardrail rules (disallowed content, out-of-scope topics), (5) language instruction (respond in same language as user).

#### Scenario: Router prompt loaded at startup
- **WHEN** the application starts and initializes the router registry
- **THEN** the router prompt template SHALL be loaded from `router_registry/v1/router_prompt.yaml` and validated for required sections

#### Scenario: Missing router prompt file
- **WHEN** `router_prompt.yaml` does not exist at the expected path
- **THEN** the system SHALL raise a `FileNotFoundError` with a descriptive message

### Requirement: Two response modes — direct voice vs. JSON action
The router prompt SHALL instruct the model to respond in one of two modes: (a) **direct voice** — speak the response immediately for simple intents (greetings, guardrails, out-of-scope, simple questions), or (b) **JSON action** — return a structured JSON object for specialist routing that requires tool execution.

#### Scenario: Direct voice for greeting
- **WHEN** the user says "hola, buenos días"
- **THEN** the model SHALL respond directly with a spoken greeting without returning JSON

#### Scenario: Direct voice for guardrail (disallowed)
- **WHEN** the user uses inappropriate language
- **THEN** the model SHALL respond directly with a calm, professional redirection without returning JSON

#### Scenario: Direct voice for out-of-scope
- **WHEN** the user asks about a topic outside business capabilities (e.g., "who will win the election")
- **THEN** the model SHALL respond directly explaining it can only help with account, billing, sales, and support topics

#### Scenario: JSON action for specialist routing
- **WHEN** the user says "tengo un problema con mi factura"
- **THEN** the model SHALL return a JSON action `{"action": "specialist", "department": "billing", "summary": "customer has a billing issue"}`

### Requirement: JSON action schema
The JSON action returned by the model for specialist routing SHALL conform to the schema: `{"action": "specialist", "department": "<department_name>", "summary": "<brief_description>"}`. The `department` field SHALL be one of: `sales`, `billing`, `support`, `retention`. The `summary` field SHALL be a brief English description of the user's intent.

#### Scenario: Valid JSON action with known department
- **WHEN** the model returns `{"action": "specialist", "department": "sales", "summary": "customer wants to upgrade plan"}`
- **THEN** the action SHALL be accepted as valid

#### Scenario: Unknown department in JSON action
- **WHEN** the model returns `{"action": "specialist", "department": "unknown_dept", "summary": "..."}`
- **THEN** the parser SHALL reject the action and treat the response as a direct voice response, logging a warning

#### Scenario: Malformed JSON from model
- **WHEN** the model returns text that starts with `{` but is not valid JSON
- **THEN** the parser SHALL treat the response as a direct voice response and log a warning for prompt tuning

### Requirement: RouterPromptBuilder builds response.create payloads

The RouterPromptBuilder SHALL embed conversation history as text within the `instructions` field of the `response.create` payload. The payload MUST NOT include a `response.input` field, as this overrides OpenAI's native conversation context (including committed audio from the current turn).

History format in instructions:
```
Conversation history:
User: <text>
Assistant: <text>
...
```

#### Scenario: Build with no history
- **WHEN** `build_response_create` is called with an empty history list
- **THEN** the payload SHALL contain only `instructions` (system prompt) with no `Conversation history:` section and no `input` field

#### Scenario: Build with multi-turn history
- **WHEN** `build_response_create` is called with a history list of user/assistant messages
- **THEN** the payload `instructions` SHALL contain the system prompt followed by a `Conversation history:` section with all turns formatted as `User: <text>` / `Assistant: <text>`
- **AND** the payload MUST NOT contain a `response.input` field

### Requirement: JSON action parser
The model-router SHALL provide a `parse_model_action` function that takes accumulated response transcript text and determines whether it is a valid JSON action or a direct voice response.

#### Scenario: Valid specialist action parsed
- **WHEN** the accumulated transcript is `{"action": "specialist", "department": "billing", "summary": "billing issue"}`
- **THEN** `parse_model_action` SHALL return a `ModelRouterAction` with `department="billing"` and `summary="billing issue"`

#### Scenario: Direct voice response (non-JSON)
- **WHEN** the accumulated transcript is "Buenos días, ¿en qué puedo ayudarle?"
- **THEN** `parse_model_action` SHALL return `None` (indicating direct voice)

#### Scenario: JSON with wrong schema
- **WHEN** the accumulated transcript is `{"type": "something_else", "data": 123}`
- **THEN** `parse_model_action` SHALL return `None` and log a warning

### Requirement: Router prompt supports dynamic language

The router prompt `language_instruction` section SHALL instruct the model to respond in the same language the customer is speaking, rather than forcing a single language.

#### Scenario: Customer speaks Spanish
- **WHEN** the customer speaks in Spanish
- **THEN** the model SHALL respond in Spanish

#### Scenario: Customer speaks English
- **WHEN** the customer speaks in English
- **THEN** the model SHALL respond in English
