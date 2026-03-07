## Tasks

### Backend

- [x] [BE] Add `websockets` dependency to `backend/pyproject.toml` and regenerate `uv.lock`
- [x] [BE] Create `OpenAIRealtimeEventBridge` class in `backend/src/voice_runtime/realtime_event_bridge.py` implementing `RealtimeClient` protocol with WebSocket lifecycle (connect, close, reconnect with backoff)
- [x] [BE] Implement input event translation: OpenAI WebSocket events (`input_audio_buffer.speech_started`, `speech_stopped`, `conversation.item.input_audio_transcription.completed`, `response.done`, `response.failed`) → Coordinator EventEnvelopes
- [x] [BE] Implement output event translation: `send_voice_start()` → `session.update` + `response.create` messages, `send_voice_cancel()` → `response.cancel` message
- [x] [BE] Implement background event listener task that reads WebSocket messages and dispatches translated events to the registered callback
- [x] [BE] Update `CallSessionEntry` in `calls.py` to hold runtime actors (Coordinator, TurnManager, AgentFSM, ToolExecutor, Router, RealtimeEventBridge)
- [x] [BE] Update `POST /calls` to instantiate full runtime actor stack and store in session entry
- [x] [BE] Update `POST /calls/{call_id}/offer` to open the RealtimeEventBridge WebSocket connection after successful SDP proxy
- [x] [BE] Update `DELETE /calls/{call_id}` to tear down all runtime actors and close the bridge WebSocket

### Tests

- [x] [TEST] Unit tests for `OpenAIRealtimeEventBridge`: input event translation (speech_started, speech_stopped, transcript_final, voice_completed, voice_error)
- [x] [TEST] Unit tests for `OpenAIRealtimeEventBridge`: output event translation (send_voice_start with message array, send_voice_start with string, send_voice_cancel)
- [x] [TEST] Unit tests for `OpenAIRealtimeEventBridge`: WebSocket lifecycle (connect, close, reconnect on disconnect, malformed message handling)
- [x] [TEST] Integration tests for session lifecycle: POST /calls creates actors, POST /calls/{id}/offer opens bridge, DELETE /calls/{id} tears down everything
