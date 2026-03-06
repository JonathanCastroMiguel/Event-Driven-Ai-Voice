## ADDED Requirements

### Requirement: RealtimeVoiceBridge implements RealtimeClient Protocol
The `RealtimeVoiceBridge` SHALL implement the existing `RealtimeClient` Protocol (`send_voice_start`, `send_voice_cancel`, `on_event`, `close`) so the Coordinator can use it as a drop-in replacement for `StubRealtimeClient`.

#### Scenario: Bridge used as RealtimeClient
- **WHEN** the Coordinator is initialized with a `RealtimeVoiceBridge`
- **THEN** the Coordinator SHALL operate identically to when using `StubRealtimeClient`, receiving real events instead of stubs

### Requirement: Audio forwarding to Realtime Voice API
The bridge SHALL receive Opus audio frames from the WebRTC audio track, decode them if needed, and forward them to the `RealtimeVoiceProvider` for streaming STT.

#### Scenario: Audio frames forwarded
- **WHEN** the WebRTC audio track produces audio frames
- **THEN** the bridge SHALL forward each frame to the Realtime Voice API with minimal latency (no buffering beyond one frame)

#### Scenario: Audio format transcoding
- **WHEN** the Realtime Voice API requires PCM16 and the WebRTC track provides Opus
- **THEN** the bridge SHALL decode Opus to PCM16 using aiortc's built-in codec before forwarding

### Requirement: STT transcription to EventEnvelope
The bridge SHALL receive streaming transcription results from the Realtime Voice API and create `transcript_final` EventEnvelopes dispatched to the Coordinator via the `on_event` callback.

#### Scenario: Final transcription received
- **WHEN** the Realtime Voice API emits a final transcription with text "hola, necesito ayuda"
- **THEN** the bridge SHALL create an `EventEnvelope` with `type="transcript_final"`, `payload={"text": "hola, necesito ayuda"}`, `source=REALTIME` and dispatch it to the Coordinator

### Requirement: VAD signal dispatch
The bridge SHALL receive `speech_started` and `speech_ended` messages from the WebRTC "control" DataChannel and create the corresponding EventEnvelopes for the Coordinator.

#### Scenario: Speech started signal
- **WHEN** the browser sends `{"type": "speech_started", "ts": 1234}` on the control DataChannel
- **THEN** the bridge SHALL create an `EventEnvelope` with `type="speech_started"`, `ts=1234`, `source=REALTIME` and dispatch it to the Coordinator

#### Scenario: Speech ended signal
- **WHEN** the browser sends `{"type": "speech_ended", "ts": 5678}` on the control DataChannel
- **THEN** the bridge SHALL create an `EventEnvelope` with `type="speech_ended"`, `ts=5678`, `source=REALTIME` and dispatch it to the Coordinator

### Requirement: TTS audio streaming back to browser
When `send_voice_start` is called by the Coordinator, the bridge SHALL send the response text to the Realtime Voice API for TTS and stream the resulting audio frames back to the browser via the WebRTC audio track.

#### Scenario: Voice start triggers TTS
- **WHEN** the Coordinator calls `send_voice_start` with prompt text
- **THEN** the bridge SHALL send the text to the Realtime Voice API for streaming TTS
- **AND** audio frames SHALL be streamed back to the browser via the WebRTC audio track as they arrive

#### Scenario: Voice generation completed
- **WHEN** the TTS stream finishes
- **THEN** the bridge SHALL create a `voice_generation_completed` EventEnvelope and dispatch it to the Coordinator

#### Scenario: Voice generation error
- **WHEN** the TTS stream fails with an error
- **THEN** the bridge SHALL create a `voice_generation_error` EventEnvelope with the error message and dispatch it to the Coordinator

### Requirement: Voice cancellation
When `send_voice_cancel` is called, the bridge SHALL immediately stop the current TTS stream and cease sending audio frames to the browser.

#### Scenario: Active TTS cancelled
- **WHEN** the Coordinator calls `send_voice_cancel` while TTS audio is streaming
- **THEN** the bridge SHALL stop the TTS stream immediately and stop sending audio frames to the browser

### Requirement: RealtimeVoiceProvider Protocol
The bridge SHALL use a `RealtimeVoiceProvider` Protocol for all interactions with the Realtime Voice API, allowing provider swapping without bridge changes.

#### Scenario: Provider abstraction
- **WHEN** the bridge is initialized with any `RealtimeVoiceProvider` implementation
- **THEN** all STT and TTS operations SHALL go through the provider Protocol methods

### Requirement: Transcription forwarding to frontend
The bridge SHALL forward transcription events (both partial and final) to the browser via the "control" DataChannel as JSON messages for display in the UI.

#### Scenario: Transcription sent to browser
- **WHEN** a transcription event is received from the Realtime Voice API
- **THEN** the bridge SHALL send `{"type": "transcription", "text": "...", "is_final": true/false}` on the control DataChannel

### Requirement: Provider selection via factory
The call setup flow SHALL use a factory function to select the voice provider based on configuration: `OpenAIRealtimeProvider` when `OPENAI_API_KEY` is set, `StubVoiceProvider` otherwise.

#### Scenario: OpenAI provider selected when key is present
- **WHEN** a call is created and `OPENAI_API_KEY` is configured (non-empty)
- **THEN** the bridge SHALL be initialized with an `OpenAIRealtimeProvider` instance

#### Scenario: Stub provider selected when key is absent
- **WHEN** a call is created and `OPENAI_API_KEY` is not set or empty
- **THEN** the bridge SHALL be initialized with a `StubVoiceProvider` instance

#### Scenario: Provider selection logged
- **WHEN** a provider is selected for a new call
- **THEN** the system SHALL log which provider type was selected at info level

### Requirement: Audio buffer commit on speech end
The bridge SHALL call `commit_audio_buffer()` on the provider when a `speech_ended` control message is received, triggering transcription of the accumulated audio.

#### Scenario: Speech ended triggers buffer commit
- **WHEN** the browser sends `{"type": "speech_ended"}` on the control DataChannel
- **THEN** the bridge SHALL call `commit_audio_buffer()` on the provider after dispatching the `speech_stopped` EventEnvelope
