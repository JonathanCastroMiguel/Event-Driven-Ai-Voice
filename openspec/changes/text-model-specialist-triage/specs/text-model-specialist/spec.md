## ADDED Requirements

### Requirement: Text model client initialization
The specialist tools module SHALL expose a `configure(api_key: str, model: str, timeout_s: float)` function that creates a shared `httpx.AsyncClient` with connection pooling. This function SHALL be called during application startup (lifespan). A corresponding `close()` function SHALL be provided for graceful shutdown.

#### Scenario: Client configured at startup
- **WHEN** the application starts and calls `configure(api_key, model, timeout_s)`
- **THEN** a shared `httpx.AsyncClient` SHALL be created with the provided API key as a default authorization header and stored as a module-level reference

#### Scenario: Client closed at shutdown
- **WHEN** the application shuts down and calls `close()`
- **THEN** the shared `httpx.AsyncClient` SHALL be closed gracefully

#### Scenario: Tool called before configure
- **WHEN** a specialist tool is called before `configure()` has been invoked
- **THEN** the tool SHALL fall back to building prompt instructions locally (current behavior) and log a warning

### Requirement: Specialist tool calls text model for triage response
Each specialist tool (`specialist_billing`, `specialist_sales`, `specialist_support`, `specialist_retention`) SHALL call the OpenAI Chat Completions API (`/v1/chat/completions`) with the triage prompt and conversation history, and return the model's text response as a plain `str`.

#### Scenario: Successful text model call
- **WHEN** `specialist_billing(summary, history)` is called and the text model responds successfully
- **THEN** the tool SHALL return the model's response text as a `str` (not a `response.create` dict)

#### Scenario: Text model receives correct prompt structure
- **WHEN** a specialist tool calls the text model
- **THEN** the request SHALL include a `system` message with the department triage prompt (role description, clarifying question examples, triage framework, language rule) and a `user` message with the customer summary and formatted conversation history

#### Scenario: Text model response is concise
- **WHEN** a specialist tool calls the text model
- **THEN** the request SHALL set `max_tokens` to a limit appropriate for 1-2 sentence triage responses (e.g., 200) and `temperature` to 0.8

### Requirement: Fallback on text model failure
If the text model call fails (timeout, HTTP error, empty response, or client not configured), the specialist tool SHALL fall back to returning the triage prompt as a `response.create` dict (current behavior), allowing the Realtime model to interpret it. A warning SHALL be logged.

#### Scenario: Text model timeout
- **WHEN** the text model call exceeds the configured timeout
- **THEN** the tool SHALL log a warning with the department name and timeout duration, and return a `response.create` dict with the triage instructions as fallback

#### Scenario: Text model HTTP error
- **WHEN** the text model returns a non-2xx status code
- **THEN** the tool SHALL log a warning with status code and error body, and return a `response.create` dict as fallback

#### Scenario: Text model returns empty content
- **WHEN** the text model responds with an empty `choices[0].message.content`
- **THEN** the tool SHALL treat it as a failure and fall back to the `response.create` dict

### Requirement: Configuration via Settings
The application settings SHALL include `specialist_model: str` (default `"gpt-4o"`) and `specialist_timeout_s: float` (default `5.0`) for the text model used by specialist tools. The existing `openai_api_key` SHALL be reused for authentication.

#### Scenario: Custom model configured via environment
- **WHEN** `SPECIALIST_MODEL=gpt-4o-mini` is set in the environment
- **THEN** specialist tools SHALL use `gpt-4o-mini` for text model calls

#### Scenario: Default model used when not configured
- **WHEN** no `SPECIALIST_MODEL` environment variable is set
- **THEN** specialist tools SHALL use `gpt-4o`
