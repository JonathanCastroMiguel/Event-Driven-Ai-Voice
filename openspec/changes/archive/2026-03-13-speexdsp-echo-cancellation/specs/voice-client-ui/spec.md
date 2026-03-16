## MODIFIED Requirements

### Requirement: Echo cancellation via three-layer approach
The voice client SHALL use a three-layer echo cancellation approach: browser-native AEC (`echoCancellation: true`), reduced assistant volume, and grace-period mic gating. This replaces the originally planned SpeexDSP WASM approach.

#### Scenario: Browser AEC enabled
- **WHEN** the client captures microphone audio via `getUserMedia`
- **THEN** the constraints SHALL include `echoCancellation: true`, `noiseSuppression: true`, `autoGainControl: true`

#### Scenario: Reduced assistant volume
- **WHEN** the DOM `<audio>` element is created for agent playback
- **THEN** the volume SHALL be set to 0.35 (`ASSISTANT_VOLUME` constant)
- **AND** this reduces residual echo energy below the server-side VAD detection threshold

#### Scenario: Grace-period mic gating on playback start
- **WHEN** the data channel receives an `output_audio_buffer.started` event
- **THEN** the mic track SHALL be muted immediately (`track.enabled = false`)
- **AND** a timer SHALL be started for 2000ms (`GRACE_MS` constant)
- **AND** after the timer expires, the mic track SHALL be unmuted (`track.enabled = true`)

#### Scenario: Grace-period cancelled on playback end
- **WHEN** the data channel receives an `output_audio_buffer.stopped` event
- **THEN** any active grace timer SHALL be cancelled
- **AND** the mic track SHALL be unmuted immediately

#### Scenario: Multiple playback events during grace
- **WHEN** a new `output_audio_buffer.started` event arrives while a grace timer is active
- **THEN** the existing timer SHALL be cancelled and a new 2000ms timer SHALL start
- **AND** the mic SHALL remain muted until the new timer expires

#### Scenario: Barge-in preserved after grace period
- **WHEN** the grace period has elapsed and the assistant is still speaking
- **THEN** the mic SHALL be unmuted
- **AND** the user's speech SHALL reach the server-side VAD to trigger barge-in

### Requirement: Audio playback
The client SHALL play back agent audio received via the WebRTC audio track immediately as it arrives (streaming playback, not buffered). The playback volume SHALL be set to a reduced level (0.35) to minimize residual echo energy.

#### Scenario: Agent audio received
- **WHEN** audio frames arrive on the remote WebRTC audio track
- **THEN** the browser SHALL play them through the default audio output device immediately
- **AND** the playback volume SHALL be 0.35

### Requirement: Debug timeline thresholds
The debug turn timeline SHALL use adjusted color thresholds that account for the mic gating grace period.

#### Scenario: Delta color thresholds
- **WHEN** displaying a timing delta in the turn timeline
- **THEN** deltas below 550ms SHALL be green
- **AND** deltas between 550ms and 1000ms SHALL be yellow
- **AND** deltas above 1000ms SHALL be red

#### Scenario: Silence color thresholds
- **WHEN** displaying perceived silence duration
- **THEN** silence below 550ms SHALL be green
- **AND** silence between 550ms and 1000ms SHALL be yellow
- **AND** silence above 1000ms SHALL be red
