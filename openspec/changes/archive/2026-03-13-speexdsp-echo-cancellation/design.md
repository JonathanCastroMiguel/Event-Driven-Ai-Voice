## Context

The OpenAI Realtime API uses server-side VAD that detects the agent's own playback through the user's microphone as user speech, causing barge-in and a self-answering feedback loop. This is the #1 blocking issue for real voice testing.

Current audio pipeline (before this change):
1. `getUserMedia({ echoCancellation: true })` → raw mic track → `pc.addTrack()`
2. `pc.ontrack` → DOM `<audio>` element → speakers
3. No volume reduction, no mic gating

## Goals / Non-Goals

**Goals:**
- Eliminate echo feedback loop so the agent never detects its own playback as user speech
- Maintain barge-in capability (user can interrupt agent mid-speech)
- Work consistently across Chrome, Safari, and Firefox
- Keep the solution self-contained (no external services or server-side processing)

**Non-Goals:**
- Server-side echo cancellation
- Replacing WebRTC transport or changing the signaling flow
- Supporting mobile browsers (desktop-first for this testing tool)
- Perfect zero-latency barge-in during the grace window (2s delay is acceptable)

## Decisions

### 1. Browser AEC + volume reduction + grace-period mic gating (three-layer approach)

**Choice:** Combine browser-native AEC, reduced assistant volume (0.35), and a 2-second mic gate at the start of each assistant utterance.

**Why this combination:** No single technique is sufficient:
- Browser AEC alone: Works for steady-state echo but needs ~1-2s to converge on a new echo path. During convergence, residual echo leaks through and triggers VAD.
- Volume reduction alone: Reduces echo energy but doesn't eliminate it.
- Mic gating alone: Would kill barge-in entirely if permanent.

Together: Browser AEC handles steady-state echo, volume reduction minimizes residual energy, and the grace-period gate covers the convergence window. After 2s, AEC has converged and the mic is unmuted for barge-in.

### 2. Abandoned: SpeexDSP WASM AudioWorklet

**Why abandoned:** `MediaStreamDestination` tracks produce SILENCE when added to `RTCPeerConnection` in Chrome. Tested: direct `addTrack()`, `sender.replaceTrack()`, WebRTC loopback trick — all produce silence. This is a known Chrome limitation that makes any AudioWorklet-based AEC pipeline impossible with WebRTC peer connections.

The SpeexDSP worklet code worked correctly in isolation, but there is no way to feed processed audio from an AudioWorklet back into a WebRTC connection in current browsers.

### 3. Grace period timing (2 seconds)

**Choice:** 2000ms grace period from `output_audio_buffer.started`.

**Why 2s:** Browser AEC convergence time is typically 200ms-2s depending on the acoustic environment. 2s covers worst-case convergence while keeping the barge-in delay acceptable for a demo/testing tool.

### 4. Assistant volume at 0.35

**Choice:** Set `audio.volume = 0.35` on the DOM `<audio>` element.

**Why 0.35:** Low enough that residual echo energy (after browser AEC) is below the VAD detection threshold, but high enough that the agent audio is clearly audible through speakers. Empirically tested to work in typical desktop environments.

### 5. Mic gating via track.enabled

**Choice:** Toggle `sender.track.enabled` on the RTP sender's audio track.

**Why not MediaStream manipulation:** Toggling `track.enabled` is the simplest, most compatible approach. It immediately stops sending audio frames without tearing down the track or requiring renegotiation. The track stays in the peer connection — only the media flow is paused.

## Risks / Trade-offs

**[Risk] No barge-in during grace period** → For the first 2s of assistant playback, the user cannot interrupt. This is acceptable for a testing/demo tool. The grace period is configurable (`GRACE_MS` constant).

**[Risk] Volume too low for some environments** → The 0.35 volume may be too quiet in noisy environments. Users can adjust system volume as needed. The constant `ASSISTANT_VOLUME` is tunable.

**[Risk] Browser AEC quality varies** → Different browsers have different AEC implementations. Chrome's is generally good, Safari's is adequate. Firefox is untested. The volume reduction and grace gate compensate for browser differences.

## Audio Pipeline (After)

```
Mic → getUserMedia(echoCancellation: true) → micTrack → pc.addTrack()
                                                 ↓
                                          track.enabled toggled
                                          by grace period logic
                                                 ↓
                                            WebRTC → OpenAI

Remote Track → DOM <audio> (volume=0.35) → Speakers
     ↓
  Events via data channel:
  output_audio_buffer.started → startGrace (mute mic)
  output_audio_buffer.stopped → endGrace (unmute mic)
```
