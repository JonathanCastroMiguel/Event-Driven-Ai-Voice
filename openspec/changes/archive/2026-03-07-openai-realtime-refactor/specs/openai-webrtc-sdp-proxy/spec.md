## ADDED Requirements

### Requirement: SDP proxy to OpenAI Realtime WebRTC API
The backend SHALL proxy the browser's SDP offer to OpenAI's Realtime WebRTC endpoint (`POST https://api.openai.com/v1/realtime/calls?model={model}`) and return the SDP answer. The OpenAI API key MUST remain server-side and SHALL NOT be exposed to the browser.

#### Scenario: Successful SDP proxy exchange
- **WHEN** a client sends `POST /calls/{call_id}/offer` with a valid SDP offer
- **THEN** the backend SHALL forward the raw SDP to OpenAI with `Content-Type: application/sdp` and `Authorization: Bearer {openai_api_key}`
- **AND** return the SDP answer from OpenAI to the browser

#### Scenario: OpenAI returns error
- **WHEN** the OpenAI Realtime API returns a non-2xx status code
- **THEN** the backend SHALL return HTTP 502 with an error message including the OpenAI status code

#### Scenario: OpenAI returns 200 or 201
- **WHEN** the OpenAI Realtime API returns either 200 or 201
- **THEN** the backend SHALL treat both as success and return the SDP answer

### Requirement: Model configuration
The SDP proxy SHALL use the model configured via `OPENAI_REALTIME_MODEL` environment variable (default: `gpt-4o-realtime-preview`).

#### Scenario: Default model used
- **WHEN** no `OPENAI_REALTIME_MODEL` is configured
- **THEN** the proxy SHALL use `gpt-4o-realtime-preview` in the API URL query parameter

#### Scenario: Custom model configured
- **WHEN** `OPENAI_REALTIME_MODEL` is set to a custom model identifier
- **THEN** the proxy SHALL use that model in the API URL query parameter
