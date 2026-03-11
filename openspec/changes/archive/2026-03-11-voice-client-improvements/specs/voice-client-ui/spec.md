## ADDED Requirements

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
