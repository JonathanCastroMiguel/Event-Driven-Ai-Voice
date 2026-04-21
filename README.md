# Event-Driven AI Voice

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)

**Event-Driven Voice Runtime for real-time call center AI automation.**

Real-time voice agent built on the OpenAI Realtime API with WebRTC, featuring
model-as-router dispatch, multi-specialist agents, and an event-driven backend
optimized for stability and latency.

---

## What It Is

A production-oriented voice AI runtime that powers conversational agents for
call center scenarios (sales, billing, support, retention). The system
combines:

- **Browser ↔ OpenAI Realtime API** over WebRTC for low-latency voice.
- **Event-driven Python backend** that orchestrates turn management, routing,
  tool execution, and persistence.
- **Model-as-router** dispatch: one always-call tool classifies intent and
  delegates to specialist agents.
- **Next.js admin/monitoring frontend** with real-time call visibility.

MVP focus: **stability and latency**.

---

## Architecture Overview

```
Browser (WebRTC)
    ↕ Opus audio  (direct to OpenAI via WebRTC)
    ↕ oai-events  (data channel for UI: transcription, VAD, audio state)
    ↕ HTTP        (SDP signaling via backend proxy)

Backend
    → SDP Proxy              POST /v1/realtime/calls
    → RealtimeEventBridge    WSS /v1/realtime  (OpenAI events ↔ EventEnvelopes)

Coordinator (CallSession)
    ↔ TurnManager            turn detection via audio_committed
    ↔ Agent FSM              IDLE → ROUTING → SPEAKING → ...
    ↔ ToolExecutor           tool execution
    ↔ RouterPromptBuilder    response.create payloads for model-as-router
```

The **Coordinator** is the single orchestrator: it receives all events,
delegates to actors, manages cancellation and idempotency, and emits voice
output commands.

Full architecture reference: [`ai-specs/specs/architecture.md`](ai-specs/specs/architecture.md)

---

## Tech Stack

### Backend
- **Python 3.12** + asyncio + uvloop
- **FastAPI** (admin/health/webhooks); voice runtime is pure asyncio
- **asyncpg** (hot path) + **SQLAlchemy 2.0 async** (admin CRUD)
- **PostgreSQL 16** + **Redis 7** (caches, rate limiting, session registry)
- **msgspec** + **orjson**
- **sentence-transformers / onnxruntime** + **hnswlib** (routing analytics)
- **OpenTelemetry** + **Prometheus** + **Sentry**
- **pytest** + **pytest-asyncio**
- **ruff** + **mypy** (strict)
- **uv** (package manager)

### Frontend
- **Next.js 15** (App Router, React Server Components)
- **TypeScript 5** (strict)
- **Tailwind CSS 4** + **shadcn/ui**
- **TanStack Query**
- **pnpm**
- **Vitest** + **Playwright**

### Infrastructure
- **Docker Compose** (MVP deployment)

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+ and pnpm
- Docker + Docker Compose
- [`uv`](https://docs.astral.sh/uv/) package manager

### 1. Clone & configure

```bash
git clone https://github.com/JonathanCastroMiguel/Event-Driven-Ai-Voice.git
cd Event-Driven-Ai-Voice
cp .env.example .env   # fill in OPENAI_API_KEY and other secrets
```

### 2. Start infrastructure

```bash
docker compose up -d
```

### 3. Backend

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --loop uvloop
```

### 4. Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:3000`.

Full setup instructions (env vars, router registry, migrations, tests):
[`ai-specs/specs/development_guide.md`](ai-specs/specs/development_guide.md)

---

## Testing

```bash
# Backend
cd backend && uv run pytest

# Frontend unit tests
cd frontend && pnpm test

# Frontend E2E
cd frontend && pnpm test:e2e
```

---

## Documentation

All authoritative documentation lives under [`ai-specs/specs/`](ai-specs/specs/):

| Document | Purpose |
|---|---|
| [`architecture.md`](ai-specs/specs/architecture.md) | End-to-end system reference |
| [`api-spec.yml`](ai-specs/specs/api-spec.yml) | OpenAPI specification |
| [`data-model.md`](ai-specs/specs/data-model.md) | Database schema |
| [`development_guide.md`](ai-specs/specs/development_guide.md) | Setup & workflows |
| [`backend-standards.mdc`](ai-specs/specs/backend-standards.mdc) | Backend conventions |
| [`frontend-standards.mdc`](ai-specs/specs/frontend-standards.mdc) | Frontend conventions |

---

## Development Workflow

This project follows **Spec-Driven Development (SDD)** through a customized
OpenSpec workflow. Specs are the source of truth; code is an implementation
artifact.

Lifecycle commands live under `.claude/commands/opsx/` and
`.claude/commands/ai-specs/`. See [CONTRIBUTING.md](CONTRIBUTING.md) for
the full contribution process.

---

## Contributing

Contributions are welcome. Please read:

- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, setup, commit style
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community standards

---

## License

This project is distributed under the **MIT License**.

See the [LICENSE](LICENSE) file for the full text.

Copyright (c) 2026 Jonathan Castro Miguel
