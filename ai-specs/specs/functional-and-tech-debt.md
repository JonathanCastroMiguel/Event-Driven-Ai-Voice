# Functional and Tech Debt

> **Note:** This document is for the Product Owner only. It must NOT be used as input for OpenSpec changes, automated analysis, or artifact generation. Items here represent future work candidates to be prioritized by the PO.

---

## Functional

### Debug Event Persistence

**Context:** The debug event pipeline currently passes all events — including frontend-originated audio playback events (`audio_playback_start`, `audio_playback_end`) — through the backend's `_send_debug()` → `_emit_debug()` → `_debug_callback` path. Events are then forwarded to the frontend via WebSocket for ephemeral display in the debug timeline. No events are persisted.

**Current state:**
- All debug events (backend-originated and frontend-originated) flow through the Coordinator's `_emit_debug` method
- The `_on_debug_event` callback in `calls.py` (WebSocket handler) receives every event and forwards it to the browser
- The frontend stores only the last 5 turns in memory — data is lost on page refresh or session end

**Proposed change:**
- Add a persistence hook at the `_emit_debug` level or in the `_on_debug_event` callback in `calls.py`
- Store each debug event to a database table keyed by `call_id` + `turn_id`, preserving insertion order
- This enables post-call analysis of the full event sequence with accurate timing (delta_ms, total_ms, bridge timing)
- Useful for: latency regression detection, routing accuracy analysis, audio playback duration trends, specialist vs router response time comparison

**Considerations:**
- Persistence must not add latency to the hot path — use fire-and-forget or background task
- Storage volume: ~8-12 events per turn, ~50-100 bytes each — negligible at current scale
- Retention policy TBD (suggestion: 30 days default, configurable)

---

## Tech Debt

### True End-to-End Tests (Playwright)

**Context:** The current "e2e" tests (`backend/tests/e2e/`) are integration tests that exercise the backend event pipeline with mocked dependencies (no real browser, no real WebRTC, no real audio). There are no Playwright tests that validate the full system from the browser through the backend and back.

**Current state:**
- Unit tests cover individual components (Coordinator, RealtimeEventBridge, debug events)
- Integration tests simulate event flows with mocks (e.g., `test_debug_pipeline_e2e.py`)
- Frontend has no automated test coverage — all browser testing is manual
- The debug timeline, WebRTC signaling, audio capture/playback, and client debug events are only validated by manual testing against the deployed stack

**Proposed change:**
- Add Playwright tests that run against the Docker Compose stack (`localhost:3000` + `localhost:8000`)
- Cover at minimum:
  - Session creation (POST `/calls`) and WebRTC signaling (SDP offer/answer)
  - Debug panel toggle and debug event rendering in the timeline
  - Client debug events (`audio_playback_start`, `audio_playback_end`) sent back to backend via WebSocket
  - Microphone permission handling and fallback UX
- Mock the OpenAI Realtime API at the backend boundary to avoid external dependencies in CI

**Considerations:**
- Playwright is already in the frontend tech stack (per frontend standards)
- Tests should run in CI with Docker Compose up as a prerequisite
- Audio I/O cannot be tested in headless mode — focus on signaling, event flow, and UI state
