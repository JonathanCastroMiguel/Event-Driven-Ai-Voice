## Why

The voice runtime pipeline is fully wired — Coordinator, TurnManager, AgentFSM, Router, WebRTC signaling, and frontend — but it runs with a `StubVoiceProvider` that returns canned responses. No real speech-to-text or text-to-speech flows through the system. An OpenAI Realtime API implementation is needed to enable real voice conversations end-to-end.

The `RealtimeVoiceProvider` Protocol already defines the integration surface (`send_audio`, `receive_transcription`, `send_text_for_tts`, `close`). This change provides the first real implementation.

## What Changes

- Implement `OpenAIRealtimeProvider` — a concrete `RealtimeVoiceProvider` backed by the OpenAI Realtime API (`gpt-4o-mini-realtime-preview`) over a single WebSocket connection
- Add streaming STT: forward PCM16 audio frames to the WebSocket, receive transcription events
- Add streaming TTS: send response text, yield audio frames as they arrive from the WebSocket
- Add configuration settings (`OPENAI_API_KEY`, `OPENAI_REALTIME_MODEL`) to `Settings`
- Wire the provider into `CallSessionManager` so real calls use `OpenAIRealtimeProvider` instead of `StubVoiceProvider`
- Keep `StubVoiceProvider` available for testing (switchable via config or absence of API key)

## Capabilities

### New Capabilities
- `openai-realtime-provider`: OpenAI Realtime API implementation of the `RealtimeVoiceProvider` Protocol — single WebSocket for bidirectional streaming STT and TTS, optimized for minimum latency

### Modified Capabilities
- `realtime-voice-bridge`: Wire provider selection logic — use `OpenAIRealtimeProvider` when `OPENAI_API_KEY` is set, fall back to `StubVoiceProvider` otherwise

## Impact

- **Code:** New `src/voice_runtime/openai_realtime_provider.py` + config additions in `src/config.py`
- **Dependencies:** `websockets` package for async WebSocket client
- **Configuration:** `OPENAI_API_KEY` and `OPENAI_REALTIME_MODEL` environment variables (already in `.env`)
- **Docker:** No changes needed — `.env` already injected via `env_file` in `docker-compose.yml`
- **APIs:** No REST API changes — the provider is internal to the voice pipeline
