## ADDED Requirements

### Requirement: HTTP agent dispatch function
The system SHALL expose an async function `dispatch_http_agent(url: str, auth: str | None, department: str, summary: str, history: list[dict], language: str) -> str | None` that calls an external specialist agent via HTTP POST. It SHALL return the agent's text response on success, or `None` on failure.

#### Scenario: Successful HTTP agent call
- **WHEN** `dispatch_http_agent` is called with a valid URL and the external agent responds with HTTP 200
- **THEN** it SHALL return the response text as a `str`

#### Scenario: Request body contract
- **WHEN** `dispatch_http_agent` sends a POST request to the agent URL
- **THEN** the JSON body SHALL contain `department` (str), `summary` (str), `history` (list of `{role, text}` dicts), and `language` (str)

#### Scenario: Response parsing — plain text
- **WHEN** the agent responds with `Content-Type: text/plain`
- **THEN** `dispatch_http_agent` SHALL return the response body as-is

#### Scenario: Response parsing — JSON with text field
- **WHEN** the agent responds with a JSON body containing a `text` field
- **THEN** `dispatch_http_agent` SHALL return the value of the `text` field

#### Scenario: Auth header injection
- **WHEN** `auth` is not `None`
- **THEN** the request SHALL include an `Authorization: Bearer <auth>` header

#### Scenario: Auth header omitted when not configured
- **WHEN** `auth` is `None`
- **THEN** the request SHALL NOT include an `Authorization` header

#### Scenario: Timeout handling
- **WHEN** the HTTP request exceeds the configured timeout (`specialist_timeout_s`)
- **THEN** `dispatch_http_agent` SHALL log a warning and return `None`

#### Scenario: HTTP error handling
- **WHEN** the agent responds with a non-2xx status code
- **THEN** `dispatch_http_agent` SHALL log a warning with the status code and return `None`

#### Scenario: Empty response handling
- **WHEN** the agent responds with an empty body
- **THEN** `dispatch_http_agent` SHALL return `None`

### Requirement: Shared httpx client access
The `dispatch_http_agent` function SHALL use the shared `httpx.AsyncClient` from `specialist_tools.py`. The module SHALL expose a `get_client() -> httpx.AsyncClient | None` function for external access.

#### Scenario: Client available
- **WHEN** `configure()` has been called and `get_client()` is invoked
- **THEN** it SHALL return the shared `httpx.AsyncClient`

#### Scenario: Client not configured
- **WHEN** `get_client()` is called before `configure()`
- **THEN** it SHALL return `None`
- **AND** `dispatch_http_agent` SHALL return `None` and log a warning
