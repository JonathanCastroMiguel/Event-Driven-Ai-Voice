## Context

The frontend voice client has `echoCancellation: true` in getUserMedia constraints, but the audio element is not appended to the DOM — some browsers require DOM attachment for AEC to work reliably. The debug panel displays raw OpenAI events with placeholder routing data from the old embedding-based pipeline (Route A/B confidence, short-circuit, LLM fallback) which doesn't match the current model-as-router architecture. The backend has ms-level timing instrumentation (added in the previous integration fix change) but doesn't emit these metrics to the frontend.

## Goals / Non-Goals

**Goals:**
- Enable speaker-without-headphones usage (echo cancellation working reliably)
- Backend-controlled debug mode with zero overhead when disabled
- Visual pipeline timeline showing real per-stage timing for each turn
- Fix voice client browser compatibility issues

**Non-Goals:**
- Changing the voice pipeline architecture or FSM
- Adding frontend observability (Sentry, OpenTelemetry) — separate change
- Redesigning the main voice UI (transcription panel, animations)
- Adding new API endpoints (REST) — debug uses existing WebSocket

## Decisions

### 1. Audio element appended to DOM with AEC attributes

**Decision**: Append the `<audio>` element to `document.body` (hidden) and set `crossOrigin = "anonymous"`. Remove it on cleanup.

**Rationale**: Chrome and Safari require the audio element in the DOM for the browser's AEC engine to correlate speaker output with microphone input. Without DOM attachment, AEC can't identify what to cancel, causing feedback loops. The element is hidden (no visual impact) and removed on session end.

**Alternative considered**: Using AudioContext with MediaStreamDestination — adds complexity, doesn't improve AEC, and breaks the simple `srcObject` model.

### 2. Backend-controlled debug mode via WebSocket control messages

**Decision**: Debug event emission is gated by a per-session `_debug_enabled: bool` flag on the Coordinator, defaulting to `False`. The frontend sends `{"type": "debug_enable"}` or `{"type": "debug_disable"}` via the event WebSocket. The backend's `calls.py` WebSocket handler intercepts these control messages and sets the flag on the Coordinator. When disabled, no debug events are emitted — zero overhead.

**Rationale**: Production calls must have zero debug overhead. Per-session control (not global env var) allows enabling debug on a specific call without affecting others. The frontend toggle controls backend behavior, not just frontend rendering.

**Alternative considered**: Global env var — too coarse, can't debug a single call in production. Frontend-only toggle — no latency savings since backend still computes and sends events.

### 3. Structured debug events from Coordinator and Bridge

**Decision**: When debug is enabled, the Coordinator emits `debug_event` messages via the same WebSocket used for event forwarding. Each debug event has a `stage` field identifying the pipeline step and carries timing data.

Debug event schema:
```json
{
  "type": "debug_event",
  "turn_id": "<uuid>",
  "stage": "speech_start | speech_stop | audio_committed | prompt_sent | model_processing | route_result | fill_silence | generation_start | generation_finish | barge_in | specialist_sent | specialist_processing | specialist_ready",
  "delta_ms": 0,
  "total_ms": 0,
  "label": "greeting | sales | billing | support | retention | direct",
  "route_type": "direct | delegate",
  "ts": 1709913600000
}
```

Stage breakdown (previously opaque gaps are now visible):
- `audio_committed` → `prompt_sent`: prompt building time (RouterPromptBuilder)
- `prompt_sent` → `model_processing`: network RTT to OpenAI (`send_to_created_ms` from bridge)
- `model_processing` → `route_result`: model inference time (`created_to_done_ms` from bridge)

For delegate routes, additional stages track the specialist sub-flow:
- `specialist_sent`: specialist prompt dispatched
- `specialist_processing`: specialist response.created received
- `specialist_ready`: specialist response.done received, ready to generate

The Coordinator already has `_now_ms()` timestamps at every event handler. When debug is enabled, it sends `debug_event` messages through a `_send_debug` helper that writes to the frontend WebSocket via the bridge's `send_to_frontend()`.

**Rationale**: Reuses the existing WebSocket channel (no new connections). The `turn_id` groups events per turn for the timeline. The `stage` enum maps 1:1 to timeline boxes. The 3 new stages (`prompt_sent`, `model_processing`, `route_result`) decompose the previously opaque gap into actionable segments.

### 4. Visual pipeline timeline with branching for delegate routes

**Decision**: Replace the current debug panel with a horizontal box-and-arrow timeline per turn. Each box represents a pipeline stage, showing:
- Stage name (e.g., "speech_start", "route: greeting")
- Delta ms (time since previous stage)
- Cumulative ms (from first event of the turn)

**Direct route layout** (single row):
```
[speech_start] → [speech_stop] → [audio_committed] → [prompt_sent] → [model_processing] → [route_result: greeting (direct)] → [generation_start] → [generation_finish]
```

**Delegate route layout** (branching):
```
Main row:  ... → [route_result: sales (delegate)] → [fill_silence] ─────────────────────────── [generation_start] → [generation_finish]
                          ↓                                                                            ↑
Sub-flow:          [specialist_sent] → [specialist_processing] → [specialist_ready] ───────────────────┘
```

When `route_result` is "delegate", the timeline forks visually:
- **Main row** continues horizontally with a `fill_silence` stage box (emitted when Coordinator launches silence-filling)
- **Sub-flow row** branches downward from `route_result`, showing the specialist lifecycle
- When `specialist_ready` arrives, the sub-flow merges back up into `generation_start` on the main row

Other layout rules:
- Last 5 turns displayed vertically as a FIFO stack (newest on top)
- Barge-in: a red box that cuts the timeline short
- Color coding: green boxes for fast stages (<100ms delta), yellow for moderate (100-300ms), red for slow (>300ms)

**Rationale**: The branching layout makes the parallel nature of specialist routing visible — you can see that silence-filling and specialist processing happen concurrently, and where each one's latency lands. Single-row direct routes stay simple.

**Alternative considered**: Separate panels for main flow and specialist — loses the visual connection between them. Sequential (non-branching) — hides the parallelism.

### 5. Microphone permission denied UX

**Decision**: Catch `NotAllowedError` from `getUserMedia()`, display a clear message ("Microphone access is required for voice calls"), and disable the Start Call button until the user grants permission.

**Rationale**: Current behavior shows a generic error. Users need a clear message explaining what happened and how to fix it (browser permission settings).

## Risks / Trade-offs

- **[Risk] AEC effectiveness varies by browser/device** → Mitigation: AEC is best-effort; headphones remain recommended for noisy environments. DOM attachment is necessary but not sufficient — some devices have poor hardware AEC.
- **[Risk] Debug events add WebSocket traffic** → Mitigation: Gated behind per-session flag, disabled by default. When off, zero messages sent.
- **[Risk] Timeline rendering with many stages per turn** → Mitigation: Fixed set of 8 stages for direct routes, 11 for delegate routes (including specialist sub-flow). Horizontal overflow handled with CSS `overflow-x: auto`. Boxes are compact (stage name + ms only).
- **[Risk] Turn ID correlation across events** → Mitigation: Coordinator assigns a `turn_id` (UUID) at `speech_start` and includes it in all subsequent debug events for that turn.
