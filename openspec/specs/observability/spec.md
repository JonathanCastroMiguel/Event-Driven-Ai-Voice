## ADDED Requirements

### Requirement: OpenTelemetry tracing across event pipeline
Every event processed by an actor SHALL create or continue an OpenTelemetry span. Spans SHALL include attributes: `call_id`, `turn_id`, `agent_generation_id` (when applicable), `event_type`, and `source`.

#### Scenario: Turn lifecycle traced
- **WHEN** a turn flows from TurnManager → Coordinator → Agent FSM → Coordinator → Realtime
- **THEN** the full chain SHALL be visible as connected spans in the tracing backend

#### Scenario: Span attributes on coordinator event
- **WHEN** Coordinator processes a `human_turn_finalized` event
- **THEN** the span SHALL include `call_id`, `turn_id`, and `event_type="human_turn_finalized"` as attributes

### Requirement: Prometheus metrics
The system SHALL expose the following metrics via a Prometheus endpoint:

- `voice_turn_latency_ms` (histogram): time from `human_turn_finalized` to `realtime_voice_start`
- `voice_route_a_confidence` (histogram): Route A classification confidence scores
- `voice_route_b_confidence` (histogram): Route B classification confidence scores
- `voice_tool_execution_ms` (histogram): tool execution duration
- `voice_barge_in_total` (counter): number of barge-in events
- `voice_fallback_llm_total` (counter): number of 3rd-party LLM fallback invocations
- `voice_active_calls` (gauge): number of currently active calls
- `voice_filler_emitted_total` (counter): number of filler voice starts

#### Scenario: Turn latency recorded
- **WHEN** a turn completes from finalized to voice start
- **THEN** the elapsed time in ms SHALL be recorded in `voice_turn_latency_ms`

#### Scenario: Barge-in counted
- **WHEN** a barge-in event is handled by the Coordinator
- **THEN** `voice_barge_in_total` SHALL be incremented by 1

### Requirement: Router calibration logging
Every routing decision SHALL be logged with structured fields: `router_version`, `language`, `route_a_label`, `route_a_score`, `route_b_label` (if applicable), `route_b_score` (if applicable), `margin` (top1 - top2), `fallback_used` (bool), `final_action` (guided_response/tool/clarify/handoff).

#### Scenario: Routing decision logged
- **WHEN** Agent FSM classifies user text as `domain` with Route B `billing`
- **THEN** a structured log entry SHALL include `route_a_label="domain"`, `route_a_score=0.82`, `route_b_label="billing"`, `route_b_score=0.88`, `margin=0.15`, `fallback_used=false`, `final_action="tool"`

#### Scenario: Fallback logged
- **WHEN** embedding classification falls back to LLM
- **THEN** the log entry SHALL have `fallback_used=true` and include the LLM result

### Requirement: Sentry error tracking
Unhandled exceptions SHALL be captured by Sentry with `call_id` as a tag. Performance transactions SHALL be enabled for the Coordinator event loop and FastAPI endpoints.

#### Scenario: Unhandled exception captured
- **WHEN** an unhandled exception occurs in the Coordinator loop
- **THEN** Sentry SHALL capture it with `call_id` tag and full stack trace

#### Scenario: Call ID as Sentry tag
- **WHEN** any error is reported to Sentry during a call
- **THEN** the `call_id` SHALL be set as a Sentry tag for filtering

### Requirement: Health check endpoint
FastAPI SHALL expose `GET /health` that returns `{"status": "ok"}` only when: (1) asyncpg pool is connected, (2) Redis is reachable, (3) embedding models are loaded. If any check fails, it SHALL return HTTP 503 with details.

#### Scenario: Healthy system
- **WHEN** all dependencies are available and models loaded
- **THEN** `GET /health` SHALL return HTTP 200 with `{"status": "ok"}`

#### Scenario: Unhealthy during model loading
- **WHEN** embedding models are still loading at startup
- **THEN** `GET /health` SHALL return HTTP 503 with `{"status": "unhealthy", "reason": "models_loading"}`

### Requirement: Metrics endpoint
FastAPI SHALL expose `GET /metrics` in Prometheus exposition format for scraping.

#### Scenario: Prometheus scrape
- **WHEN** Prometheus scrapes `GET /metrics`
- **THEN** all registered metrics SHALL be returned in Prometheus text format
