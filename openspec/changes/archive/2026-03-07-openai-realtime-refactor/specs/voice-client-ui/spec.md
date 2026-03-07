## MODIFIED Requirements

### Requirement: WebRTC connection lifecycle
The voice client SHALL manage a direct WebRTC connection to OpenAI: create a session via `POST /calls`, exchange SDP via `POST /calls/{call_id}/offer` (backend proxies to OpenAI), and create a data channel named `oai-events` for receiving OpenAI events.

#### Scenario: Call initiated
- **WHEN** the user clicks the "Start Call" button
- **THEN** the client SHALL call `POST /calls`, create an RTCPeerConnection, capture microphone audio, add the audio track, create a data channel named `oai-events`, generate an SDP offer, exchange it via `POST /calls/{call_id}/offer`, and apply the SDP answer

#### Scenario: Call ended by user
- **WHEN** the user clicks the "End Call" button
- **THEN** the client SHALL stop all media tracks, close the RTCPeerConnection, call `DELETE /calls/{call_id}`, and reset the UI to idle state

#### Scenario: Connection lost
- **WHEN** the WebRTC peer connection enters "failed" or "disconnected" state
- **THEN** the client SHALL show a connection error message and clean up resources

#### Scenario: Page unload during active call
- **WHEN** the browser tab is closed while a call is active
- **THEN** the client SHALL send a beacon request to `DELETE /calls/{call_id}` for best-effort cleanup

### Requirement: OpenAI event translation
The client SHALL receive events from the OpenAI data channel (`oai-events`) and translate them to internal transcription messages for display.

#### Scenario: User transcription received
- **WHEN** the data channel receives a `conversation.item.input_audio_transcription.completed` event with a non-empty transcript
- **THEN** the client SHALL emit a transcription message with `speaker: "human"` and `is_final: true`

#### Scenario: Agent transcription received
- **WHEN** the data channel receives a `response.audio_transcript.done` event with a non-empty transcript
- **THEN** the client SHALL emit a transcription message with `speaker: "agent"` and `is_final: true`

### Requirement: Speaking indicators from OpenAI events
The client SHALL use OpenAI data channel events for speaking indicators instead of client-side VAD.

#### Scenario: User starts speaking
- **WHEN** the data channel receives an `input_audio_buffer.speech_started` event
- **THEN** the microphone animation SHALL activate

#### Scenario: User stops speaking
- **WHEN** the data channel receives an `input_audio_buffer.speech_stopped` event
- **THEN** the microphone animation SHALL deactivate

#### Scenario: Agent starts speaking
- **WHEN** the data channel receives a `response.audio.delta` event
- **THEN** the speaker animation SHALL activate

#### Scenario: Agent stops speaking
- **WHEN** the data channel receives a `response.audio.done` event
- **THEN** the speaker animation SHALL deactivate

### Requirement: Debug event filtering
The client SHALL forward OpenAI data channel events to the debug handler but SHALL filter out high-frequency `response.audio.delta` events to avoid flooding the debug panel.

#### Scenario: Non-audio event forwarded
- **WHEN** the data channel receives any event other than `response.audio.delta`
- **THEN** the event SHALL be forwarded to the debug handler

#### Scenario: Audio delta filtered
- **WHEN** the data channel receives a `response.audio.delta` event
- **THEN** the event SHALL NOT be forwarded to the debug handler

## REMOVED Requirements

### Requirement: Client-side VAD
**Reason**: OpenAI handles voice activity detection server-side via `input_audio_buffer.speech_started/stopped` events. Client-side Silero VAD (ONNX model + WASM runtime) is no longer needed.
**Migration**: Remove `@ricky0123/vad-web` dependency, delete ONNX model files (`silero_vad_*.onnx`) and WASM runtime assets (`ort-wasm-simd-threaded.*`), remove `use-vad.ts` and `use-microphone.ts` hooks.
