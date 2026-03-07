## 1. Two-Step SDP Exchange

- [x] 1.1 [BE] Refactor `POST /calls/{call_id}/offer` to two-step flow: `POST /v1/realtime/sessions` (config + ephemeral key) then `POST /v1/realtime` (SDP exchange with ephemeral key)
- [x] 1.2 [BE] Configure session with `input_audio_transcription: {model: "whisper-1"}` and `turn_detection: {type: "server_vad", create_response: false}` in the sessions call
- [x] 1.3 [BE] Add error handling for session creation failure (HTTP 502 with descriptive detail)

## 2. Runtime Actor Wiring

- [x] 2.1 [BE] Instantiate full actor stack (Coordinator, TurnManager, AgentFSM, ToolExecutor, Bridge) in `POST /calls` and store in `CallSessionEntry`
- [x] 2.2 [BE] Wire Bridge → Coordinator input events via `bridge.on_event(coordinator.handle_event)`
- [x] 2.3 [BE] Wire Coordinator → Bridge output events via `coordinator.set_output_callback()` dispatching to `bridge.send_voice_start()` / `bridge.send_voice_cancel()`
- [x] 2.4 [BE] Add `set_shared_router_and_policies()` function and call it in `main.py` lifespan startup
- [x] 2.5 [BE] Add policies fallback stubs in `_get_policies()` with warning log when not initialized

## 3. WebSocket Event Forwarding

- [x] 3.1 [BE] Add `WS /calls/{call_id}/events` endpoint for bidirectional event forwarding
- [x] 3.2 [BE] Send one-time `session.update` via `bridge.send_to_frontend()` on WebSocket connection
- [x] 3.3 [BE] Forward incoming WebSocket messages to `bridge.handle_frontend_event()` in receive loop
- [x] 3.4 [BE] Handle WebSocket disconnect with cleanup (`bridge.set_frontend_ws(None)`)

## 4. Bridge & Language Detection Fixes

- [x] 4.1 [BE] Rename `_send_to_frontend` → `send_to_frontend` (public method) in `realtime_event_bridge.py`
- [x] 4.2 [BE] Update all internal callers (`send_voice_start`, `send_voice_cancel`) to use the renamed method
- [x] 4.3 [BE] Replace fasttext with langid in `src/routing/language.py`
- [x] 4.4 [BE] Add `langid` dependency to `pyproject.toml`

## 5. Frontend Event Forwarding

- [x] 5.1 [FE] Update `use-voice-session.ts` to connect to `WS /calls/{call_id}/events` after call creation
- [x] 5.2 [FE] Forward OpenAI data channel events from `oai-events` channel to the WebSocket
- [x] 5.3 [FE] Implement `sendOrBuffer` mechanism to queue messages until data channel opens, then flush

## 6. Debugging & Logging

- [x] 6.1 [BE] Add `text=text` to `turn_finalized` structured log in TurnManager

## 7. Tests

- [x] 7.1 [TEST] Update `test_webrtc_signaling.py` to mock two-step SDP flow (sessions + SDP exchange)
- [x] 7.2 [TEST] Add test for WebSocket event forwarding endpoint (connect, forward event, disconnect)
- [x] 7.3 [TEST] Add test for session.update sent on WebSocket connection
- [x] 7.4 [TEST] Add test for actor wiring (Bridge events reach Coordinator, Coordinator output reaches Bridge)
- [x] 7.5 [TEST] Add test for policies fallback stubs when not initialized
