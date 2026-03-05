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
```

### 3. Start Infrastructure

```bash
docker compose up -d  # PostgreSQL 16 + Redis 7
```

### 4. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 5. Database Migrations

```bash
cd backend
alembic upgrade head
```

### 6. Router Registry

The router registry lives at `backend/router_registry/v1/` and contains:
- `config.yml` — thresholds, centroid definitions, lexicon rules
- `policies.yml` — policy key to prompt template mapping

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

- `tests/unit/` — Unit tests for individual components (coordinator, router, turn manager, agent FSM, tool executor, realtime client, telemetry, API routes)
- `tests/e2e/` — End-to-end tests exercising the full event pipeline via FakeRealtime + OutputCapture fixtures

## Architecture Overview

The runtime uses an **Event-Driven Actor Model** with four actors communicating via typed events:

1. **Coordinator** (CallSession) — Central orchestrator: state management, barge-in cancellation, idempotency, prompt construction
2. **TurnManager** — Detects human speech turns from VAD/transcript events
3. **Agent FSM** — Intent classification (Route A/B) via embeddings, policy key emission
4. **ToolExecutor** — Deterministic tool execution with timeout, cancellation, result caching

### Key Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check (DB, Redis, models) |
| `GET /metrics` | Prometheus metrics exposition |
| `GET /api/v1/calls` | List recent call sessions |
| `GET /api/v1/calls/{call_id}` | Call detail with turns and generations |

### Observability

- **OpenTelemetry**: Spans per event with `call_id`, `turn_id`, `agent_generation_id` attributes
- **Prometheus**: 8 metrics (latency histograms, confidence histograms, counters, gauges)
- **Sentry**: DSN-based error tracking with `call_id` tagging
- **Structured logging**: via `structlog` with router calibration fields
