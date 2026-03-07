## Backend

- [x] [BE] Rewrite `calls.py` as pure SDP proxy: remove aiortc peer connection, remove ICE endpoint, proxy SDP offer to OpenAI Realtime WebRTC API (`POST /v1/realtime/calls`), return SDP answer
- [x] [BE] Simplify `CallSessionEntry` to only track `call_id` (remove peer_connection, bridge, coordinator references)
- [x] [BE] Remove backend dependencies: `aiortc`, `websockets` from `pyproject.toml`
- [x] [BE] Remove STUN/TURN configuration from `config.py` (`stun_servers`, `turn_servers`, `turn_username`, `turn_credential`)
- [x] [BE] Delete removed modules: `audio_output_track.py`, `realtime_bridge.py`, `openai_realtime_provider.py`, `realtime_provider.py`

## Frontend

- [x] [FE] Rewrite `use-voice-session.ts`: direct OpenAI WebRTC connection, inline data channel listeners, local `newCallId` variable for cleanup, `beforeunload` beacon handler
- [x] [FE] Add OpenAI event translation in data channel handler: `conversation.item.input_audio_transcription.completed` → human transcription, `response.audio_transcript.done` → agent transcription
- [x] [FE] Update `voice-session.tsx`: use OpenAI events for speaking indicators (`speech_started/stopped`, `response.audio.delta/done`), remove `useMicrophone`/`useVAD` hooks
- [x] [FE] Filter `response.audio.delta` events from debug handler to avoid flooding
- [x] [FE] Remove dead code: `use-microphone.ts`, `use-vad.ts` hooks
- [x] [FE] Remove `@ricky0123/vad-web` from `package.json`, update lockfile
- [x] [FE] Delete VAD assets: `silero_vad_legacy.onnx`, `silero_vad_v5.onnx`, `ort-wasm-simd-threaded.*`
- [x] [FE] Clean up types: remove `ControlOutMessage` (speech_started/speech_ended), remove `sendControl` from voice-session destructuring
- [x] [FE] Remove dead `api.calls.ice()` method from `api.ts`

## Tests

- [x] [TEST] Update `test_webrtc_signaling.py`: remove `TestHandleICE` class, remove stale `CallSessionEntry` field assertions, remove mock_settings references to deleted config fields
- [x] [TEST] Delete removed test files: `test_realtime_bridge.py`, `test_openai_realtime_provider.py`, `test_voice_provider.py`, `test_voice_provider_factory.py`
- [x] [TEST] Verify TypeScript compiles cleanly (`npx tsc --noEmit`)
- [x] [TEST] Verify backend tests pass (`pytest tests/unit/test_webrtc_signaling.py` — 10/10)
