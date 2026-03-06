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
Every routing decision SHALL be logged as a single `routing_completed` structured log entry at the end of `Router.classify()`. The log SHALL include: `router_version` (from ThresholdsConfig), `language`, `route_a_label`, `route_a_score` (float), `route_a_margin` (top1 - top2, float), `route_b_label` (str or None), `route_b_score` (float or None), `route_b_margin` (float or None), `short_circuit` (str or None: "lexicon" / "short_utterance"), `fallback_used` (bool). The log SHALL be emitted for every code path including lexicon short-circuit, short utterance match, embedding classification, LLM fallback, and ambiguous Route B.

#### Scenario: Routing decision logged for domain with Route B
- **WHEN** Router classifies user text as `domain` with Route B `billing` (score 0.88, margin 0.15) without fallback
- **THEN** a structured log entry `routing_completed` SHALL include `router_version="v1.0.0"`, `route_a_label="domain"`, `route_a_score=0.82`, `route_a_margin=0.10`, `route_b_label="billing"`, `route_b_score=0.88`, `route_b_margin=0.15`, `short_circuit=None`, `fallback_used=false`

#### Scenario: Routing decision logged for lexicon short-circuit
- **WHEN** Router classifies user text via lexicon match as `disallowed`
- **THEN** a structured log entry `routing_completed` SHALL include `route_a_label="disallowed"`, `route_a_score=1.0`, `route_a_margin=0.0`, `route_b_label=None`, `route_b_score=None`, `route_b_margin=None`, `short_circuit="lexicon"`, `fallback_used=false`

#### Scenario: Routing decision logged for short utterance
- **WHEN** Router classifies user text via short utterance match as `simple`
- **THEN** a structured log entry `routing_completed` SHALL include `route_a_label="simple"`, `route_a_score=1.0`, `route_a_margin=0.0`, `short_circuit="short_utterance"`, `fallback_used=false`

#### Scenario: Routing decision logged with LLM fallback
- **WHEN** Router classifies user text using LLM fallback for ambiguous Route A
- **THEN** a structured log entry `routing_completed` SHALL include `fallback_used=true` and the LLM-determined `route_a_label`

#### Scenario: Routing decision logged for ambiguous Route B (no LLM)
- **WHEN** Router classifies Route B as ambiguous and LLM fallback is disabled or times out
- **THEN** a structured log entry `routing_completed` SHALL include `route_b_label=None`, `fallback_used=false`

#### Scenario: Router version included in every log
- **WHEN** any routing decision is logged
- **THEN** the `router_version` field SHALL match the `version` field from `thresholds.yaml`

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
