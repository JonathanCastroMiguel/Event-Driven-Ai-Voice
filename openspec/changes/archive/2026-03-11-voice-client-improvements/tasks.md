## 1. Mute Toggle

- [x] 1.1 [FE] Add `isMuted` state and `toggleMute` function to `use-voice-session.ts` — toggle `sender.track.enabled` on the WebRTC audio sender
- [x] 1.2 [FE] Add mute button to the call control bar in `voice-session.tsx` — show crossed-out mic icon when muted, only visible during active call
- [x] 1.3 [FE] Deactivate microphone animation when muted, resume on unmute
- [x] 1.4 [FE] Reset mute state to unmuted when call ends
- [x] 1.5 [TEST] Add unit test for `toggleMute` — verify `track.enabled` toggles and state resets on disconnect

## 2. Echo Cancellation Hardening

- [x] 2.1 [FE] Verify remote audio playback uses a DOM `<audio>` element (not Web Audio API) — fix if needed (verified: already correct)
- [x] 2.2 [FE] Ensure `echoCancellation: true` is set in getUserMedia constraints (already present — verify no override) (verified: correct)
- [x] 2.3 [TEST] Manual test: play agent response on laptop speakers, confirm no echo loop (verified in live environment)

## 3. Debug Panel Specialist Timeline Fix

- [x] 3.1 [FE] Refactor `turn-timeline.tsx` specialist row — dynamic offset from `route_result` using invisible spacer instead of fixed `pl-8 ml-4`
- [x] 3.2 [FE] Verify timeline resizes correctly when browser window changes (spacer approach is flex-based, resizes naturally)
- [x] 3.3 [TEST] Visual verification: specialist timeline forks from `route_result` position (verified in live environment)

## 4. Router Prompt Determinism

- [x] 4.1 [BE] Update `decision_rules` in `router_prompt.yaml` — clear routing instructions with examples, simplified to avoid over-constraining the model
- [x] 4.2 [BE] Add investigative annotation: document model non-determinism findings (log analysis results, alternative test phrases) in `ROUTING_NOTES.md`
- [x] 4.3 [TEST] Manual test: routing phrases verified in live environment, `function_call_received=True` confirmed in logs

## 5. Additional Improvements (discovered during testing)

- [x] 5.1 [BE] Add transcript cleanup (`_clean_transcript`) in `realtime_event_bridge.py` — regex strips leaked function call syntax from transcripts in `response.done` and `model_router_action`
- [x] 5.2 [BE] Set model temperature to 0.8 in `model_router.py` — balanced between determinism and flexibility
- [x] 5.3 [BE] Reduce VAD silence duration from 300ms to 200ms in `config.py` (under evaluation)
- [x] 5.4 [BE] Add anti-vocalization instruction in router prompt — model must never speak function names or syntax
