scope: FE
design-linked: false

## Why

Browser AEC (Acoustic Echo Cancellation) is not effectively cancelling the assistant's audio output when using speakers in Chrome. The microphone captures the assistant's voice, the Realtime API's server-side VAD interprets it as user speech, and the model responds — creating a self-reinforcing echo loop that generates 10+ auto-responses until the call is manually ended.

The current grace-period mic gating (2s mute on playback start) was designed for AEC convergence time, not for preventing echo input. It does not solve the root cause and any increase would degrade barge-in capability.

## What Changes

- Diagnose whether browser AEC is actually active on the mic track (verify `echoCancellation` constraint is applied and effective via `getSettings()`)
- Investigate why AEC fails with speaker output in Chrome (known issues with `<audio>` element setup, volume levels, audio routing)
- Implement a fix that preserves full barge-in capability — no functionality sacrifice
- Add diagnostic logging to detect echo loop conditions for future monitoring

## Capabilities

### New Capabilities

- `echo-cancellation-diagnostics`: Runtime verification that browser AEC is active and effective, plus detection/logging of echo loop conditions

### Modified Capabilities

- `voice-client-ui`: Changes to audio setup in `use-voice-session.ts` to fix AEC behavior without sacrificing barge-in

## Impact

- `frontend/src/hooks/use-voice-session.ts` — audio element setup, mic constraints, grace period logic
- `frontend/src/hooks/use-voice-session.test.ts` — updated tests for any AEC changes
- `frontend/src/hooks/use-voice-session-aec.test.ts` — updated/new AEC-specific tests
- No backend changes required — the issue is entirely in the browser audio pipeline
