## ADDED Requirements

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

### Requirement: Microphone capture and streaming
The client SHALL capture audio from the user's microphone using the MediaDevices API and stream it via the WebRTC audio track using Opus codec.

#### Scenario: Microphone permission granted
- **WHEN** the user grants microphone access
- **THEN** the client SHALL capture audio and add the media stream track to the RTCPeerConnection

#### Scenario: Microphone permission denied
- **WHEN** the user denies microphone access
- **THEN** the client SHALL display a clear message explaining how to enable microphone access in browser settings
- **AND** the "Start Call" button SHALL be disabled

### Requirement: Audio playback
The client SHALL play back agent audio received via the WebRTC audio track immediately as it arrives (streaming playback, not buffered).

#### Scenario: Agent audio received
- **WHEN** audio frames arrive on the remote WebRTC audio track
- **THEN** the browser SHALL play them through the default audio output device immediately

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

### Requirement: Microphone input animation
The client SHALL display a visual animation indicating when the user's microphone is capturing audio.

#### Scenario: User speaking
- **WHEN** OpenAI detects the user is speaking (via `input_audio_buffer.speech_started`)
- **THEN** a microphone animation SHALL be visible indicating active input

#### Scenario: User silent
- **WHEN** OpenAI detects the user has stopped speaking (via `input_audio_buffer.speech_stopped`)
- **THEN** the microphone animation SHALL return to idle state

### Requirement: Speaker output animation
The client SHALL display a visual animation indicating when the agent is producing audio output.

#### Scenario: Agent speaking
- **WHEN** audio is being played back from the remote WebRTC track
- **THEN** a speaker animation SHALL be visible indicating active output

#### Scenario: Agent silent
- **WHEN** no audio is being played back
- **THEN** the speaker animation SHALL return to idle state

### Requirement: Real-time transcription display
The client SHALL display transcriptions for both human (input) and agent (output).

#### Scenario: Human transcription displayed
- **WHEN** a transcription message with `is_final: true` and `speaker: "human"` arrives
- **THEN** the text SHALL be displayed in the human transcription area

#### Scenario: Agent transcription displayed
- **WHEN** a transcription message with `is_final: true` and `speaker: "agent"` arrives
- **THEN** the text SHALL be displayed in the agent transcription area

### Requirement: Debug event filtering
The client SHALL forward OpenAI data channel events to the debug handler but SHALL filter out high-frequency `response.audio.delta` events to avoid flooding the debug panel.

#### Scenario: Non-audio event forwarded
- **WHEN** the data channel receives any event other than `response.audio.delta`
- **THEN** the event SHALL be forwarded to the debug handler

#### Scenario: Audio delta filtered
- **WHEN** the data channel receives a `response.audio.delta` event
- **THEN** the event SHALL NOT be forwarded to the debug handler

### Requirement: Mute toggle
The voice client SHALL provide a mute button that toggles the WebRTC audio sender track's `enabled` property. When muted, silence frames SHALL be sent (no renegotiation). The button SHALL be visible in the call control bar during an active call.

#### Scenario: User mutes microphone
- **WHEN** the user clicks the mute button during an active call
- **THEN** `sender.track.enabled` SHALL be set to `false` on the audio sender
- **AND** the mute button SHALL display a "muted" visual state (e.g., crossed-out microphone icon)
- **AND** the microphone animation SHALL deactivate

#### Scenario: User unmutes microphone
- **WHEN** the user clicks the mute button while muted
- **THEN** `sender.track.enabled` SHALL be set to `true` on the audio sender
- **AND** the mute button SHALL return to the "active" visual state
- **AND** the microphone animation SHALL resume reflecting speech detection

#### Scenario: Mute button visibility
- **WHEN** no call is active
- **THEN** the mute button SHALL NOT be rendered

#### Scenario: Mute state reset on call end
- **WHEN** the user ends a call while muted
- **THEN** the mute state SHALL reset to unmuted for the next call

### Requirement: Echo cancellation via DOM audio element
The voice client SHALL ensure remote WebRTC audio is played through a DOM `<audio>` element (not Web Audio API) so the browser's built-in acoustic echo cancellation can correlate input and output signals.

#### Scenario: Remote audio playback path
- **WHEN** a remote audio track is received on the RTCPeerConnection
- **THEN** the track SHALL be assigned to a DOM `<audio>` element's `srcObject` for playback
- **AND** the element SHALL have `autoplay` enabled

#### Scenario: Echo cancellation active
- **WHEN** the user's microphone is captured with `echoCancellation: true`
- **AND** remote audio plays through a DOM `<audio>` element
- **THEN** the browser's AEC SHALL be able to correlate input/output for echo suppression

### Requirement: Visual design
The voice client SHALL use a light mode design with neutral colors, minimal UI elements, and no visual elements that add rendering latency.

#### Scenario: Light mode appearance
- **WHEN** the voice client loads
- **THEN** it SHALL render with a light background, neutral color palette, and minimal visual complexity
