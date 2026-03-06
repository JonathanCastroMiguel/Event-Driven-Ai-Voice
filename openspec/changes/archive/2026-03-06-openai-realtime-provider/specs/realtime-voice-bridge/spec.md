## ADDED Requirements

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
