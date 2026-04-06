## ADDED Requirements

### Requirement: AEC runtime verification
After obtaining the microphone track via `getUserMedia`, the client SHALL verify that echo cancellation is active by calling `track.getSettings()` and checking that `echoCancellation === true`. The client SHALL also check `track.getCapabilities()` for available AEC types.

#### Scenario: AEC active
- **WHEN** `getUserMedia` succeeds and `track.getSettings().echoCancellation === true`
- **THEN** the client SHALL log `"aec_verified"` with `echoCancellation: true` and the available AEC types from `getCapabilities()`

#### Scenario: AEC not active
- **WHEN** `getUserMedia` succeeds but `track.getSettings().echoCancellation === false`
- **THEN** the client SHALL log `console.warn("aec_not_active")` with device details from `getSettings()`

#### Scenario: AEC type detection
- **WHEN** `track.getCapabilities()` includes `echoCancellationType` containing `"system"`
- **THEN** the client SHALL log `"hardware_aec_available"` for diagnostic purposes

### Requirement: Hardware AEC preference
The `getUserMedia` audio constraints SHALL include `echoCancellationType: { ideal: "system" }` to prefer hardware/OS-level AEC when available, falling back to browser AEC3 automatically.

#### Scenario: Hardware AEC available
- **WHEN** the device supports hardware AEC
- **THEN** `getUserMedia` SHALL select the hardware AEC implementation

#### Scenario: Hardware AEC not available
- **WHEN** the device does not support hardware AEC
- **THEN** `getUserMedia` SHALL fall back to Chrome's software AEC3 without error

### Requirement: Echo loop detection
The client SHALL track `input_audio_buffer.speech_started` events from the data channel within a rolling time window. If the count exceeds a threshold, the client SHALL log a warning for diagnostics.

#### Scenario: Normal conversation pace
- **WHEN** fewer than 5 `speech_started` events occur within a 10-second window
- **THEN** no echo loop warning SHALL be emitted

#### Scenario: Echo loop detected
- **WHEN** 5 or more `speech_started` events occur within a 10-second window
- **THEN** the client SHALL log `console.warn("echo_loop_detected")` with the event count and window duration
- **AND** the warning SHALL be emitted at most once per 10-second window (no spam)

#### Scenario: Counter resets after quiet period
- **WHEN** the rolling window elapses with no new `speech_started` events
- **THEN** the counter SHALL reset to zero
