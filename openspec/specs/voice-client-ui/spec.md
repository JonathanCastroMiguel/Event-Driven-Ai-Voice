## ADDED Requirements

### Requirement: WebRTC connection lifecycle
The voice client SHALL manage the full WebRTC connection lifecycle: create a session via `POST /calls`, exchange SDP offer/answer via `POST /calls/{call_id}/offer`, handle ICE candidates, and clean up on call end.

#### Scenario: Call initiated
- **WHEN** the user clicks the "Start Call" button
- **THEN** the client SHALL call `POST /calls`, then create an RTCPeerConnection, generate an SDP offer, exchange it via `POST /calls/{call_id}/offer`, and apply the SDP answer

#### Scenario: Call ended by user
- **WHEN** the user clicks the "End Call" button
- **THEN** the client SHALL close the RTCPeerConnection, call `DELETE /calls/{call_id}`, and reset the UI to idle state

#### Scenario: Connection lost
- **WHEN** the WebRTC peer connection enters "failed" or "disconnected" state
- **THEN** the client SHALL show a connection error message and clean up resources

### Requirement: Microphone capture and streaming
The client SHALL capture audio from the user's microphone using the MediaDevices API and stream it via the WebRTC audio track using Opus codec.

#### Scenario: Microphone permission granted
- **WHEN** the user grants microphone access
- **THEN** the client SHALL capture audio and add the media stream track to the RTCPeerConnection

#### Scenario: Microphone permission denied
- **WHEN** the user denies microphone access
- **THEN** the client SHALL display a clear message explaining how to enable microphone access in browser settings
- **AND** the "Start Call" button SHALL be disabled

### Requirement: Client-side VAD
The client SHALL run Silero VAD in WASM via `@ricky0123/vad-web` to detect speech boundaries and send `speech_started` / `speech_ended` signals to the backend via the "control" DataChannel.

#### Scenario: Speech start detected
- **WHEN** Silero VAD detects the user has started speaking
- **THEN** the client SHALL send `{"type": "speech_started", "ts": <epoch_ms>}` on the control DataChannel within 3ms of detection

#### Scenario: Speech end detected
- **WHEN** Silero VAD detects the user has stopped speaking
- **THEN** the client SHALL send `{"type": "speech_ended", "ts": <epoch_ms>}` on the control DataChannel within 3ms of detection

#### Scenario: VAD does not gate audio
- **WHEN** VAD detects silence
- **THEN** the audio stream SHALL continue flowing to the backend (VAD only signals, does not stop the audio track)

### Requirement: Audio playback
The client SHALL play back agent audio received via the WebRTC audio track immediately as it arrives (streaming playback, not buffered).

#### Scenario: Agent audio received
- **WHEN** audio frames arrive on the remote WebRTC audio track
- **THEN** the browser SHALL play them through the default audio output device immediately

### Requirement: Microphone input animation
The client SHALL display a visual animation indicating when the user's microphone is capturing audio.

#### Scenario: User speaking
- **WHEN** VAD detects the user is speaking
- **THEN** a microphone animation SHALL be visible indicating active input

#### Scenario: User silent
- **WHEN** VAD detects the user has stopped speaking
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
The client SHALL display transcriptions received via the control DataChannel for both human (input) and agent (output).

#### Scenario: Human transcription displayed
- **WHEN** a transcription message with `is_final: true` arrives for the user's speech
- **THEN** the text SHALL be displayed in the human transcription area

#### Scenario: Agent transcription displayed
- **WHEN** the agent's response text is received
- **THEN** the text SHALL be displayed in the agent transcription area

### Requirement: Visual design
The voice client SHALL use a light mode design with neutral colors, minimal UI elements, and no visual elements that add rendering latency.

#### Scenario: Light mode appearance
- **WHEN** the voice client loads
- **THEN** it SHALL render with a light background, neutral color palette, and minimal visual complexity
