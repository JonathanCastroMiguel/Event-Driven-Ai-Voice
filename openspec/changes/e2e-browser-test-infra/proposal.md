## Why

There is no way to run browser-based end-to-end tests against the full stack. The existing Playwright spec (`voice-client.spec.ts`) has no config file and is incorrectly picked up by Vitest (causing a `test.describe()` error). The Docker Compose only includes backend + Postgres + Redis — no frontend service. Without this infrastructure, we cannot validate the debug panel, voice session flow, or WebSocket communication in a real browser against a real backend.

## What Changes

- **Playwright configuration**: Create `playwright.config.ts` with proper baseURL, webServer config, and project settings (Chromium at minimum). Configure timeouts, retries, and test directory.
- **Vitest exclusion**: Update `vitest.config.ts` to exclude `**/*.spec.ts` files so Playwright tests are not picked up by Vitest. The two test runners must coexist without conflicts.
- **Frontend Dockerfile**: Create a multi-stage `Dockerfile` for the Next.js frontend (build + standalone output). Expose port 3000.
- **Full-stack Docker Compose**: Create a root-level `docker-compose.e2e.yml` that orchestrates all services needed for browser e2e tests:
  - `postgres` (PostgreSQL 16) — existing service definition
  - `redis` (Redis 7) — existing service definition
  - `backend` (FastAPI on port 8000) — built from `backend/Dockerfile`
  - `frontend` (Next.js on port 3000) — built from new frontend Dockerfile, depends on backend
  - All services with health checks and proper dependency ordering
- **Backend API mock/stub layer**: The OpenAI Realtime API requires an API key and real WebRTC. For e2e tests, the backend needs a test mode where:
  - `POST /calls` returns a valid session with a call_id but does not connect to OpenAI
  - WebSocket `/calls/{call_id}/events` works normally for control/debug messages
  - A mock Realtime bridge echoes back predictable responses (e.g., fixed transcript, fixed audio silence) so the frontend can exercise the full flow without external dependencies
  - Activated via `VOICEAI_TEST_MODE=true` environment variable
- **E2e test scripts**: Add npm scripts and a shell script to orchestrate the full e2e flow:
  - `docker compose -f docker-compose.e2e.yml up --build -d`
  - Wait for health checks
  - `pnpm test:e2e`
  - `docker compose -f docker-compose.e2e.yml down`
- **Browser e2e test suite**: Playwright tests that validate:
  - Page loads with correct UI elements (fix existing `voice-client.spec.ts`)
  - Start Call button initiates a session (POST /calls succeeds, status changes to "connecting")
  - Mic permission denied shows proper error UX (using browser context permissions)
  - Debug toggle sends `debug_enable`/`debug_disable` via WebSocket and debug panel appears/disappears
  - Debug events from the backend render as timeline stages in the debug panel
  - End Call cleans up session and resets UI
  - Transcription messages from backend appear in the transcription panel
- **CI considerations**: Document how to run e2e tests in CI (GitHub Actions) with Docker Compose. Not implementing CI pipeline in this change, but the scripts should be CI-ready.

## Capabilities

### New Capabilities

- `e2e-test-infra`: Playwright configuration, Docker Compose for full stack, test orchestration scripts, and backend test mode for deterministic browser testing without external API dependencies.

### Modified Capabilities

- `voice-client-ui`: Existing Playwright spec fixed and expanded with real browser tests against the running stack.
- `coordinator`: Test mode support — mock Realtime bridge that returns predictable responses when `VOICEAI_TEST_MODE=true`.

## Impact

- **Infrastructure**: New `docker-compose.e2e.yml` (root), new `frontend/Dockerfile`, new `playwright.config.ts`, new `scripts/run-e2e.sh`
- **Backend code**: New mock/stub Realtime bridge for test mode, test mode flag in config, conditional wiring in `main.py` or session factory
- **Frontend code**: `vitest.config.ts` (exclude `.spec.ts`), updated and new Playwright specs in `frontend/__tests__/e2e/`
- **No production behavior changes**: Test mode is only activated by explicit env var, all production code paths remain unchanged
- **Dependencies**: `@playwright/test` already installed. May need `playwright install chromium` in Docker/CI.
