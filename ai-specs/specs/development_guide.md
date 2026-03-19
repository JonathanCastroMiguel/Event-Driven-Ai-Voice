# Development Guide

This guide provides step-by-step instructions for setting up the development environment and running the Voice AI Runtime.

## Prerequisites

- **Python** 3.12+
- **Docker** and **Docker Compose** (for PostgreSQL and Redis)
- **Git**

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <repo-url>
cd VoiceAIV3
```

### 2. Environment Configuration

Create `backend/.env`:

```env
DATABASE_URL=postgresql://voiceai:voiceai@localhost:5432/voiceai
REDIS_URL=redis://localhost:6379/0

# Optional observability
OTEL_ENDPOINT=
SENTRY_DSN=

# LLM fallback (for Route A/B classification)
LLM_FALLBACK_URL=
LLM_FALLBACK_API_KEY=
LLM_FALLBACK_MODEL=gpt-4o-mini

# OpenAI Realtime (for real STT/TTS — omit for stub provider)
OPENAI_API_KEY=
OPENAI_REALTIME_MODEL=gpt-4o-mini-realtime-preview

# WebRTC (optional — defaults are suitable for local dev)
STUN_SERVERS=stun:stun.l.google.com:19302
TURN_SERVERS=
TURN_USERNAME=
TURN_CREDENTIAL=
MAX_CONCURRENT_CALLS=50

# Server VAD
VAD_SILENCE_DURATION_MS=200
```

### 3. Start Infrastructure

```bash
docker compose up -d  # PostgreSQL 16 + Redis 7
```

### 4. Backend Setup

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

> **Note**: The project uses `uv` as its package manager. Key dependencies include `aiortc` for server-side WebRTC.

### 5. Database Migrations

```bash
cd backend
alembic upgrade head
```

### 6. Router Registry

The router registry lives at `backend/router_registry/v1/` and contains:
- `config.yml` — thresholds, centroid definitions, lexicon rules
- `policies.yml` — policy key to prompt template mapping
- `router_prompt.json` — model-as-router JSON config (identity, agents with triggers/fillers/tool bindings, guardrails, language instruction). Uses always-classify pattern with `tool_choice: "required"` — every message triggers a `route_to_specialist` call with `department="direct"` or a specialist department. The JSON structure matches the future API payload, enabling zero-change migration from local file to API-driven config.

### 6.1 Specialist Tools

Mock specialist tools live at `backend/src/voice_runtime/specialist_tools.py`. Four tools (`specialist_sales`, `specialist_billing`, `specialist_support`, `specialist_retention`) are registered in `ToolExecutor` at call creation via `register_specialist_tools()`. Each tool has its own prompt builder with department-specific triage examples (sales: plan/features/budget, billing: invoice/charge/amount, support: device/error/timing, retention: reason/tenure/retention). Shared `_TRIAGE_FRAMEWORK` enforces mandatory clarifying questions before transfer and dynamic language matching from conversation history. These simulate future LangGraph/LangChain sub-agents.

Tests: `backend/tests/unit/test_specialist_tools.py` (9 tests: prompt differentiation, no hardcoded Spanish, department-specific keywords, history embedding) + `backend/tests/unit/test_two_step_routing.py` (13 tests: function call parsing, tool registration, payload structure).

### 7. Run the Server

```bash
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000 --loop uvloop --log-level info
```

## Testing

### Run All Tests

```bash
cd backend
pytest
```

### Run by Category

```bash
# Unit tests only
pytest tests/unit/

# E2E integration tests only
pytest tests/e2e/

# Specific test file
pytest tests/unit/test_coordinator.py -v
```

### Test Structure

- `tests/unit/` — 303 unit tests for individual components (coordinator, router, turn manager, agent FSM, tool executor, specialist tools, realtime event bridge, two-step routing, telemetry, API routes)
- `tests/e2e/` — 23 E2E integration tests exercising the full event pipeline via FakeRealtime + OutputCapture fixtures, plus 4 Playwright E2E tests

## Architecture Overview

The runtime uses an **Event-Driven Actor Model** with four actors communicating via typed events:

1. **Coordinator** (CallSession) — Central orchestrator: state management, barge-in cancellation, idempotency, model-as-router dispatch via response.create
2. **TurnManager** — Detects human speech turns from VAD events and audio_committed signals
3. **Agent FSM** — State machine tracking agent lifecycle: idle → routing → speaking → waiting_tools → done. No longer performs classification — that's handled by the model-as-router.
4. **ToolExecutor** — Deterministic tool execution with timeout, cancellation, result caching

The runtime uses a **model-as-router** architecture where the Realtime voice model classifies intent AND responds in a single inference. The embedding pipeline (Router, EmbeddingEngine) is preserved for offline analytics but removed from the hot path.

### Key Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check (DB, Redis, models) |
| `GET /metrics` | Prometheus metrics exposition |
| `GET /api/v1/calls` | List recent call sessions (admin) |
| `GET /api/v1/calls/{call_id}` | Call detail with turns and generations (admin) |
| `POST /api/v1/calls` | Create voice call session with full runtime actor stack |
| `POST /api/v1/calls/{call_id}/offer` | Two-step SDP exchange (sessions + ephemeral key + SDP) |
| `WS /api/v1/calls/{call_id}/events` | Bidirectional event forwarding (browser ↔ Coordinator) |
| `DELETE /api/v1/calls/{call_id}` | End call, tear down actors, close bridge |

### Observability

- **OpenTelemetry**: Spans per event with `call_id`, `turn_id`, `agent_generation_id` attributes
- **Prometheus**: 8 metrics (latency histograms, confidence histograms, counters, gauges)
- **Sentry**: DSN-based error tracking with `call_id` tagging
- **Structured logging**: via `structlog` with router calibration fields
