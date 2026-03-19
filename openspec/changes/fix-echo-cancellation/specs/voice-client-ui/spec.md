## MODIFIED Requirements

### Requirement: Echo cancellation via three-layer approach
The voice client SHALL use a three-layer echo cancellation approach: browser-native AEC (`echoCancellation: true`) with hardware AEC preference, reduced assistant volume, and grace-period mic gating. This prevents the server-side VAD from detecting the agent's own playback as user speech.

#### Scenario: Browser AEC enabled with hardware preference
- **WHEN** the client captures microphone audio via `getUserMedia`
- **THEN** the constraints SHALL include `echoCancellation: true`, `noiseSuppression: true`, `autoGainControl: true`
- **AND** the constraints SHALL include `echoCancellationType: { ideal: "system" }` to prefer hardware AEC

#### Scenario: Reduced assistant volume
- **WHEN** the DOM `<audio>` element is created for agent playback
- **THEN** the volume SHALL be set to 0.20 (`ASSISTANT_VOLUME` constant)
- **AND** this reduces residual echo energy below the server-side VAD detection threshold

#### Scenario: Grace-period mic gating on playback start
- **WHEN** the data channel receives an `output_audio_buffer.started` event
- **AND** the user has NOT manually muted the microphone
- **THEN** the mic track SHALL be muted immediately (`track.enabled = false`)
- **AND** a timer SHALL be started for 2000ms (`GRACE_MS` constant)
- **AND** after the timer expires, the mic track SHALL be unmuted (`track.enabled = true`) only if the user has not manually muted

#### Scenario: Grace-period skipped when manually muted
- **WHEN** the data channel receives an `output_audio_buffer.started` event
- **AND** the user HAS manually muted the microphone
- **THEN** the mic track SHALL remain muted (`track.enabled = false`)
- **AND** no grace timer SHALL be started

#### Scenario: Grace-period cancelled on playback end
- **WHEN** the data channel receives an `output_audio_buffer.stopped` event
- **THEN** any active grace timer SHALL be cancelled
- **AND** the mic track SHALL be unmuted immediately only if the user has not manually muted

#### Scenario: Multiple playback events during grace
- **WHEN** a new `output_audio_buffer.started` event arrives while a grace timer is active
- **THEN** the existing timer SHALL be cancelled and a new 2000ms timer SHALL start
- **AND** the mic SHALL remain muted until the new timer expires

#### Scenario: Barge-in preserved after grace period
- **WHEN** the grace period has elapsed and the assistant is still speaking
- **THEN** the mic SHALL be unmuted (unless manually muted)
- **AND** the user's speech SHALL reach the server-side VAD to trigger barge-in

### Requirement: Mute toggle
The voice client SHALL provide a mute button that toggles the WebRTC audio sender track's `enabled` property. When muted, silence frames SHALL be sent (no renegotiation). The button SHALL be visible in the call control bar during an active call. Manual mute state SHALL take precedence over grace-period mic gating.

#### Scenario: User mutes microphone
- **WHEN** the user clicks the mute button during an active call
- **THEN** `sender.track.enabled` SHALL be set to `false` on the audio sender
- **AND** the `manuallyMuted` ref SHALL be set to `true`
- **AND** any active grace timer SHALL be cancelled
- **AND** the mute button SHALL display a "muted" visual state (e.g., crossed-out microphone icon)
- **AND** the microphone animation SHALL deactivate

#### Scenario: User unmutes microphone
- **WHEN** the user clicks the mute button while muted
- **THEN** `sender.track.enabled` SHALL be set to `true` on the audio sender
- **AND** the `manuallyMuted` ref SHALL be set to `false`
- **AND** the mute button SHALL return to the "active" visual state
- **AND** the microphone animation SHALL resume reflecting speech detection

#### Scenario: Mute button visibility
- **WHEN** no call is active
- **THEN** the mute button SHALL NOT be rendered

#### Scenario: Mute state reset on call end
- **WHEN** the user ends a call while muted
- **THEN** the mute state SHALL reset to unmuted for the next call
- **AND** the `manuallyMuted` ref SHALL be set to `false`
