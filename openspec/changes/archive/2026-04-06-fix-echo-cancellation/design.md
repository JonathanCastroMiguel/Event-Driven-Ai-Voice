## Context

Browser AEC (`echoCancellation: true` on `getUserMedia`) is the primary echo cancellation mechanism. The current audio setup follows Chrome's recommended pattern: plain `<audio>` element with `srcObject` from WebRTC remote stream, mic with AEC/NS/AGC enabled.

Despite correct setup, echo loops occur **consistently in every environment** when using speakers (not headphones). This is not an acoustic/room issue — AEC is either not activating at all, or Chrome's AEC3 leaves enough residual echo to trigger OpenAI's very sensitive server-side VAD. The assistant's audio is picked up by the mic, VAD interprets it as user speech, the model responds, and this repeats indefinitely (10+ auto-responses observed). The 2s grace-period mic gating only helps AEC convergence and does not prevent the loop.

Current state:
- `ASSISTANT_VOLUME = 0.20` (reduced to minimize residual echo energy)
- `GRACE_MS = 2000` (mic muted for first 2s of playback for AEC convergence)
- No runtime verification that AEC is actually active
- No detection of echo loop conditions
- Grace period does not respect manual mute state (`endGrace` always re-enables track)

## Goals / Non-Goals

**Goals:**
- Verify at runtime that browser AEC is active and log a warning if not
- Detect echo loop conditions and log them for diagnostics
- Fix grace period to respect manual mute state
- Explore `echoCancellationType: "system"` for hardware AEC where available
- Preserve full barge-in capability — no functionality sacrifice

**Non-Goals:**
- Implementing custom DSP/WASM-based AEC (proven dead end — `MediaStreamDestination` produces silence in WebRTC)
- Increasing grace period or muting mic during playback (destroys barge-in)
- Server-side echo detection heuristics (adds latency, wrong layer)
- Solving AEC at application level if browser AEC is fundamentally insufficient for OpenAI's VAD sensitivity

## Decisions

### D1: Add AEC runtime diagnostics after `getUserMedia`

After obtaining the mic track, call `track.getSettings()` to verify `echoCancellation === true`. Also call `track.getCapabilities()` to check if `system` AEC type is available. Log warnings via `console.warn` if AEC is not active.

**Why**: Zero-cost check that catches edge cases (devices that don't support AEC, browser overriding the constraint). Currently we assume AEC is active but never verify.

### D2: Request `echoCancellationType: "system"` as ideal constraint

Add `echoCancellationType: { ideal: "system" }` to `getUserMedia` constraints. This prefers hardware/OS-level AEC when available (some laptops, macOS DSP), falling back to Chrome's AEC3 automatically if not.

**Why**: Hardware AEC operates at a lower level with access to the actual speaker output signal, making it more effective than browser-only AEC. No downside — falls back gracefully.

**Alternative considered**: Requiring `system` type with `exact` — rejected because it would fail on devices without hardware AEC.

### D3: Detect echo loop via rapid-fire `speech_started` counter

Track a counter of `speech_started` events within a rolling window (e.g., 5 events within 10 seconds). If exceeded, log a warning with `"echo_loop_detected"`. This is diagnostic only — no automatic muting.

**Why**: Gives us visibility into when echo loops happen without affecting behavior. Future iterations could add a UI indicator or auto-recovery, but the first step is measurement.

**Alternative considered**: Auto-mute on echo loop detection — rejected per user requirement of no functionality sacrifice.

### D4: Grace period must respect manual mute

Both `startGrace` and `endGrace` must check the `isMuted` React state before manipulating `track.enabled`. If the user has manually muted, grace logic should not re-enable the track.

**Why**: Currently `endGrace()` unconditionally sets `track.enabled = true`, overriding manual mute. This is a bug independent of the echo issue.

**Implementation**: Share a `manuallyMuted` ref between `toggleMute`, `startGrace`, and `endGrace`. Grace functions skip `track.enabled = true` when `manuallyMuted.current === true`.

### D5: Keep volume at 0.20 and grace at 2000ms

Research confirms that `audio.volume` adjusts within the browser pipeline. At 0.20, physical echo energy is significantly reduced without being inaudible. The 2s grace period matches AEC3 convergence time (2-5s).

**Why**: These values are reasonable for AEC convergence. However, given that AEC fails consistently across all environments, the root cause is likely that AEC is either inactive or that its residual echo exceeds OpenAI's VAD sensitivity threshold. D1 diagnostics will confirm which case it is.

## Risks / Trade-offs

- **[Risk] `echoCancellationType: "system"` has limited availability** → Mitigation: requested as `ideal`, not `exact`. Falls back silently to browser AEC.
- **[Risk] Echo loop detection is diagnostic-only, won't stop loops** → Mitigation: first step is measurement. UI indicator or recovery can be added in a follow-up once we have data on frequency and patterns.
- **[Risk] Manual mute + grace interaction edge cases** → Mitigation: `manuallyMuted` ref is the single source of truth. Grace functions are read-only on this ref, only `toggleMute` writes it.
- **[Risk] AEC may be active but insufficient for OpenAI's VAD** → If diagnostics show AEC is on but echo loops persist, the issue is the combination of browser AEC residual + OpenAI's VAD sensitivity. Possible follow-up: investigate OpenAI Realtime API's VAD threshold configuration (`server_vad` settings like `threshold`, `prefix_padding_ms`, `silence_duration_ms`) to reduce false triggers from residual echo.
- **[Trade-off] Diagnostics-first approach delays a fix** → We need data to know if AEC is inactive vs insufficient. Shipping diagnostics first avoids building the wrong solution.
