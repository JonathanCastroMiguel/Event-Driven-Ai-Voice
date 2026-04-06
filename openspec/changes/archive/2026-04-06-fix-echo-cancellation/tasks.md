## 1. AEC Runtime Diagnostics

- [x] 1.1 [FE] After `getUserMedia`, call `track.getSettings()` and `track.getCapabilities()` to verify AEC is active. Log `"aec_verified"` or `console.warn("aec_not_active")` with device details. Log `"hardware_aec_available"` if system AEC type is detected.
- [x] 1.2 [FE] Add `echoCancellationType: { ideal: "system" }` to the `getUserMedia` audio constraints to prefer hardware AEC when available.

## 2. Grace Period Respects Manual Mute

- [x] 2.1 [FE] Add a `manuallyMuted` ref (`useRef<boolean>(false)`) in `use-voice-session.ts`. Set it to `true` in `toggleMute` when muting, `false` when unmuting, and `false` in `endSession`.
- [x] 2.2 [FE] Update `startGrace`: skip muting if `manuallyMuted.current === true`. Skip starting the grace timer if manually muted.
- [x] 2.3 [FE] Update `endGrace`: skip `track.enabled = true` if `manuallyMuted.current === true`.
- [x] 2.4 [FE] Update `toggleMute`: when user mutes, cancel any active grace timer.

## 3. Echo Loop Detection

- [x] 3.1 [FE] Track `input_audio_buffer.speech_started` events from the data channel in a rolling 10-second window (array of timestamps).
- [x] 3.2 [FE] When the count reaches 5 within the window, emit `console.warn("echo_loop_detected")` with event count and window duration. Rate-limit the warning to once per 10-second window.

## 4. Tests

- [x] 4.1 [TEST] Update `use-voice-session.test.ts`: test that `toggleMute` sets `manuallyMuted` ref and cancels active grace timer.
- [x] 4.2 [TEST] Update `use-voice-session-aec.test.ts`: test that `startGrace` and `endGrace` respect `manuallyMuted` state (skip track.enabled changes when manually muted).
- [x] 4.3 [TEST] Add test for echo loop detection: verify warning is emitted after 5 rapid `speech_started` events and rate-limited to once per window.
- [x] 4.4 [TEST] Add test for AEC diagnostics: verify `getSettings()` and `getCapabilities()` are called after `getUserMedia` and appropriate logs emitted.
