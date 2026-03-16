## Why

Browser built-in Acoustic Echo Cancellation (AEC) alone fails to prevent the OpenAI Realtime API's server-side VAD from detecting the agent's own playback as user speech, causing barge-in and a self-answering feedback loop. The initial approach (SpeexDSP WASM in an AudioWorklet) was abandoned because `MediaStreamDestination` tracks produce silence when added to `RTCPeerConnection` in Chrome — making any AudioWorklet-based AEC pipeline impossible with WebRTC.

The working solution combines three complementary techniques: browser-native AEC (which handles the bulk of echo removal), reduced assistant volume (to minimize residual echo energy), and a grace-period mic gate (to cover the ~2s window where browser AEC hasn't converged on a new echo path).

## What Changes

- Enable browser AEC (`echoCancellation: true`) on microphone capture
- Reduce assistant audio volume to 0.35 via the DOM `<audio>` element
- Add grace-period mic gating: mute the mic track for the first 2s of assistant playback, then unmute to allow barge-in
- Hook mic gating to OpenAI data channel events (`output_audio_buffer.started` / `output_audio_buffer.stopped`)
- Adjust debug timeline thresholds to account for the mic gating grace period

## Capabilities

### Modified Capabilities
- `voice-client-ui`: Echo cancellation changes from browser AEC only to a three-layer approach (browser AEC + reduced volume + grace-period mic gating). The mic track is gated during early assistant playback to prevent the server-side VAD from detecting residual echo.

## Impact

- **Frontend audio pipeline** (`use-voice-session.ts`): Mic track is temporarily disabled via `track.enabled = false` during assistant playback grace period. Volume set to 0.35 on the `<audio>` element.
- **Debug timeline** (`turn-timeline.tsx`): Color thresholds adjusted (green < 550ms, yellow < 1000ms) to reflect realistic latency with mic gating.
- **No backend changes required.**
- **No new dependencies.**
