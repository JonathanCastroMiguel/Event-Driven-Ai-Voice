## MODIFIED Requirements

### Requirement: Router prompt decision rules
The router prompt `decision_rules` section SHALL instruct the model to ALWAYS call `route_to_specialist` for every user message. The model SHALL use `department="direct"` when handling messages itself (greetings, small talk, general questions, inappropriate language, out-of-scope, unclear input) and a specialist department when the user needs system access (billing, sales, support, retention). The decision rules SHALL include examples mapping common inputs to the appropriate department and function call.

#### Scenario: Decision rules specify always-classify pattern
- **WHEN** the router prompt is loaded from `router_prompt.yaml`
- **THEN** the `decision_rules` section SHALL instruct the model to call `route_to_specialist` for every message with no exceptions

#### Scenario: Direct department examples in prompt
- **WHEN** the router prompt is loaded
- **THEN** the `decision_rules` SHALL include examples like: "hola" → `route_to_specialist(department="direct", summary="greeting")`

#### Scenario: Specialist department examples in prompt
- **WHEN** the router prompt is loaded
- **THEN** the `decision_rules` SHALL include examples like: "me han cobrado de más" → `route_to_specialist(department="billing", ...)`

#### Scenario: Function call is silent reminder
- **WHEN** the router prompt is loaded
- **THEN** the `decision_rules` SHALL remind the model that the function call is silent and invisible to the customer
