### Requirement: Router prompt template definition
The model-router SHALL define a router system prompt template stored in `router_registry/v1/router_prompt.yaml`. The template SHALL contain sections for: (1) base system identity (call center agent persona), (2) router decision rules (when to speak directly vs. call route_to_specialist), (3) department definitions (sales, billing, support, retention), (4) guardrail rules (disallowed content, out-of-scope topics), (5) language instruction (respond in same language as user).

#### Scenario: Router prompt loaded at startup
- **WHEN** the application starts and initializes the router registry
- **THEN** the router prompt template SHALL be loaded from `router_registry/v1/router_prompt.yaml` and validated for required sections

#### Scenario: Missing router prompt file
- **WHEN** `router_prompt.yaml` does not exist at the expected path
- **THEN** the system SHALL raise a `FileNotFoundError` with a descriptive message

### Requirement: Two response modes — direct voice vs. function call action
The router prompt SHALL instruct the model to respond in one of two modes: (a) **direct voice** — speak the response immediately for simple intents (greetings, guardrails, out-of-scope, simple questions), or (b) **function call** — call the `route_to_specialist` function for specialist routing that requires system access, while simultaneously speaking a brief filler message.

The decision_rules SHALL include explicit reinforcement to ensure deterministic function calling:
1. A clear instruction that the model MUST call `route_to_specialist` (not just speak about routing)
2. Negative examples of what NOT to do (e.g., "NEVER say you will connect the customer without also calling route_to_specialist")
3. End-of-prompt reinforcement repeating the function call requirement (leveraging recency bias)

#### Scenario: Direct voice for greeting
- **WHEN** the user says "hola, buenos días"
- **THEN** the model SHALL respond directly with a spoken greeting without calling any function

#### Scenario: Direct voice for guardrail (disallowed)
- **WHEN** the user uses inappropriate language
- **THEN** the model SHALL respond directly with a calm, professional redirection without calling any function

#### Scenario: Direct voice for out-of-scope
- **WHEN** the user asks about a topic outside business capabilities (e.g., "who will win the election")
- **THEN** the model SHALL respond directly explaining it can only help with account, billing, sales, and support topics

#### Scenario: Function call for specialist routing
- **WHEN** the user says "tengo un problema con mi factura"
- **THEN** the model SHALL speak a brief filler message (e.g., "Un momento, le conecto con facturación")
- **AND** the model SHALL call the `route_to_specialist` function with `department: "billing"` and a brief English summary

#### Scenario: Function call is mandatory for routing
- **WHEN** the model determines the user needs specialist help
- **THEN** the model MUST call `route_to_specialist` — speaking about routing without calling the function is a failure mode that SHALL be prevented by prompt reinforcement

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

### Requirement: Router prompt supports dynamic language

The router prompt `language_instruction` section SHALL instruct the model to respond in the same language the customer is speaking, rather than forcing a single language.

#### Scenario: Customer speaks Spanish
- **WHEN** the customer speaks in Spanish
- **THEN** the model SHALL respond in Spanish

#### Scenario: Customer speaks English
- **WHEN** the customer speaks in English
- **THEN** the model SHALL respond in English
