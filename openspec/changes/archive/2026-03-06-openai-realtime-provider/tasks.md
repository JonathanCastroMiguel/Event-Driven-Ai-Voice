## 1. Configuration

- [x] 1.1 [BE] Add `openai_api_key` and `openai_realtime_model` fields to `Settings` in `src/config.py` (default model: `gpt-4o-mini-realtime-preview`)
- [x] 1.2 [BE] Add `websockets` dependency to `pyproject.toml` and run `uv lock`

## 2. OpenAI Realtime Provider Core

- [x] 2.1 [BE] Create `src/voice_runtime/openai_realtime_provider.py` with class skeleton implementing `RealtimeVoiceProvider` Protocol (init, close, internal queues)
- [x] 2.2 [BE] Implement WebSocket connection lifecycle — `connect()` opens persistent WebSocket to `wss://api.openai.com/v1/realtime`, `close()` shuts it down
- [x] 2.3 [BE] Implement background message reader task — reads all incoming WebSocket messages, routes to STT queue or TTS queue based on message type
- [x] 2.4 [BE] Implement `send_audio()` — base64-encode PCM16 frame, send `input_audio_buffer.append` (fire-and-forget)
- [x] 2.5 [BE] Implement 48kHz→24kHz downsampling in `send_audio()` (take every 2nd sample via numpy slicing)
- [x] 2.6 [BE] Implement `commit_audio_buffer()` — send `input_audio_buffer.commit` message
- [x] 2.7 [BE] Implement `receive_transcription()` — async iterator yielding `TranscriptionEvent` from STT queue
- [x] 2.8 [BE] Implement `send_text_for_tts()` — send `response.create` message, yield audio frames from TTS queue until `None` sentinel

## 3. Bridge Integration

- [x] 3.1 [BE] Add `create_voice_provider()` factory function in `src/voice_runtime/realtime_provider.py` — returns `OpenAIRealtimeProvider` if API key set, else `StubVoiceProvider`
- [x] 3.2 [BE] Add `commit_audio_buffer()` call in `RealtimeVoiceBridge._handle_control_message()` when `speech_ended` is received
- [x] 3.3 [BE] Wire provider creation into `calls.py` `handle_offer()` — call factory, pass provider to bridge, start audio forwarding and STT listener

## 4. Tests

- [x] 4.1 [TEST] Unit test `OpenAIRealtimeProvider` — mock WebSocket, verify `send_audio` sends correct JSON, verify `receive_transcription` yields events from reader, verify `send_text_for_tts` yields audio frames
- [x] 4.2 [TEST] Unit test `create_voice_provider()` factory — verify returns `OpenAIRealtimeProvider` when key set, `StubVoiceProvider` when absent
- [x] 4.3 [TEST] Unit test bridge `commit_audio_buffer` integration — verify `speech_ended` triggers buffer commit on provider
- [x] 4.4 [TEST] Unit test 48kHz→24kHz downsampling — verify correct sample count and values
