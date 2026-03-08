## MODIFIED Requirements

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
