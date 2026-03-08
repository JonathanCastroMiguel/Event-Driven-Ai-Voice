## MODIFIED Requirements

### Requirement: Audio element DOM attachment for echo cancellation

The audio element for remote playback MUST be appended to `document.body` (hidden) during session setup and removed on cleanup. This is required for browser AEC (Acoustic Echo Cancellation) to correlate speaker output with microphone input.

#### Scenario: Audio element appended on session start
- **WHEN** `startSession()` creates the audio element
- **THEN** the element SHALL be appended to `document.body` with `style.display = "none"` and `autoplay = true`

#### Scenario: Audio element removed on session end
- **WHEN** `cleanup()` is called
- **THEN** the audio element SHALL be removed from `document.body` and its `srcObject` set to `null`

### Requirement: Microphone permission denied UX

When `getUserMedia()` throws `NotAllowedError`, the UI MUST display a clear message explaining that microphone access is required and disable the Start Call button.

#### Scenario: Microphone permission denied
- **WHEN** the user denies microphone permission
- **THEN** the UI SHALL display "Microphone access is required for voice calls" and the Start Call button SHALL be disabled

#### Scenario: Microphone permission granted after denial
- **WHEN** the user grants microphone permission after a previous denial (page reload)
- **THEN** the Start Call button SHALL be enabled and no error message displayed

### Requirement: Debug toggle sends control message

The debug toggle in the voice session UI SHALL send `debug_enable` / `debug_disable` messages to the backend via the event WebSocket, rather than only toggling frontend rendering.

#### Scenario: Debug toggle sends WebSocket message
- **WHEN** the user clicks the debug toggle
- **THEN** a `{"type": "debug_enable"}` or `{"type": "debug_disable"}` message SHALL be sent via the event WebSocket
