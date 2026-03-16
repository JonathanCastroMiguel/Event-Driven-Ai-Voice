## 1. Browser AEC + Volume Reduction

- [x] 1.1 [FE] Enable browser AEC: set `echoCancellation: true`, `noiseSuppression: true`, `autoGainControl: true` in `getUserMedia` constraints in `use-voice-session.ts`
- [x] 1.2 [FE] Add `ASSISTANT_VOLUME` constant (0.35) and apply to DOM `<audio>` element on creation

## 2. Grace-Period Mic Gating

- [x] 2.1 [FE] Implement `startGrace()`: on `output_audio_buffer.started`, mute mic track via `sender.track.enabled = false` and start 2000ms timer to re-enable
- [x] 2.2 [FE] Implement `endGrace()`: on `output_audio_buffer.stopped`, cancel grace timer and unmute mic track immediately
- [x] 2.3 [FE] Wire `startGrace` and `endGrace` to data channel message handler for `output_audio_buffer.started` and `output_audio_buffer.stopped` events

## 3. Debug Timeline Adjustments

- [x] 3.1 [FE] Update `deltaColor()` thresholds in `turn-timeline.tsx`: green < 550ms, yellow < 1000ms
- [x] 3.2 [FE] Update `silenceColor()` thresholds: green < 550ms, yellow < 1000ms

## 4. Cleanup Dead Code

- [x] 4.1 [FE] Remove `scripts/build-speexdsp-wasm.sh` (abandoned SpeexDSP WASM approach)

## 5. Testing

- [x] 5.1 [TEST] Update unit tests in `use-voice-session-aec.test.ts` to reflect browser AEC + grace period approach
- [x] 5.2 [TEST] Manual test: verify echo is eliminated in Chrome (agent no longer detects own audio)
- [x] 5.3 [TEST] Manual test: verify barge-in still works (user can interrupt agent after grace period)
