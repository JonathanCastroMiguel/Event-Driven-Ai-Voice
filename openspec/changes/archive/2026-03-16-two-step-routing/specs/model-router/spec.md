## MODIFIED Requirements

### Requirement: Two response modes — direct voice vs. function call action
The router prompt SHALL instruct the model to classify every user message via a mandatory `route_to_specialist` function call with `tool_choice: "required"`. The model SHALL call `route_to_specialist(department="direct", summary="...")` for messages it handles itself (greetings, guardrails, out-of-scope, simple questions), and `route_to_specialist(department="<specialist>", summary="...")` for messages requiring specialist routing. Because `tool_choice: "required"` suppresses audio output, the model produces only the function call in this response — the spoken reply is generated in a separate follow-up `response.create`.

#### Scenario: Direct classification for greeting
- **WHEN** the user says "hola, buenos días"
- **THEN** the model SHALL call `route_to_specialist(department="direct", summary="greeting")` without generating audio

#### Scenario: Direct classification for guardrail (disallowed)
- **WHEN** the user uses inappropriate language
- **THEN** the model SHALL call `route_to_specialist(department="direct", summary="inappropriate language")` without generating audio

#### Scenario: Direct classification for out-of-scope
- **WHEN** the user asks about a topic outside business capabilities
- **THEN** the model SHALL call `route_to_specialist(department="direct", summary="out of scope")` without generating audio

#### Scenario: Specialist classification for routing
- **WHEN** the user says "tengo un problema con mi factura"
- **THEN** the model SHALL call `route_to_specialist(department="billing", summary="billing issue")` without generating audio

#### Scenario: Classification is mandatory for every message
- **WHEN** the model receives any user message
- **THEN** the model MUST call `route_to_specialist` — `tool_choice: "required"` enforces this at the API level

### Requirement: RouterPromptBuilder builds response.create payloads

The RouterPromptBuilder SHALL embed conversation history as text within the `instructions` field of the `response.create` payload. The payload SHALL include `tool_choice: "required"` to enforce mandatory function calling. The `route_to_specialist` tool definition SHALL include `"direct"` in the department enum.

#### Scenario: Build with no history
- **WHEN** `build_response_create` is called with an empty history list
- **THEN** the payload SHALL contain `instructions` (system prompt), `tools` (with `route_to_specialist` including `"direct"` department), `tool_choice: "required"`, and no `Conversation history:` section

#### Scenario: Build with multi-turn history
- **WHEN** `build_response_create` is called with a history list of user/assistant messages
- **THEN** the payload `instructions` SHALL contain the system prompt followed by a `Conversation history:` section
- **AND** the payload SHALL include `tool_choice: "required"` and `tools` with `route_to_specialist`

## ADDED Requirements

### Requirement: Department.DIRECT enum value
The `Department` enum SHALL include a `DIRECT = "direct"` value representing messages the model handles without specialist routing. The `route_to_specialist` tool definition SHALL include `"direct"` in the `department` parameter enum alongside `"sales"`, `"billing"`, `"support"`, and `"retention"`.

#### Scenario: Direct department parsed from function call
- **WHEN** `parse_function_call_action` receives arguments `{"department": "direct", "summary": "greeting"}`
- **THEN** it SHALL return a `RoutingAction` with `department=Department.DIRECT`

#### Scenario: Tool definition includes direct
- **WHEN** the `ROUTE_TOOL_DEFINITION` is inspected
- **THEN** the `department` enum SHALL be `["direct", "sales", "billing", "support", "retention"]`
