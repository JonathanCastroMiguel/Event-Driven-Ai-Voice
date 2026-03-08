## Context

The voice runtime was architecturally complete and unit-tested, but first real-audio browser testing revealed integration bugs invisible to mocked tests. The most critical: on multi-turn conversations, the model ignored the user's current speech entirely because `response.input` overrode OpenAI's native conversation context (which carries the committed audio buffer).

## Goals / Non-Goals

**Goals:**
- Fix multi-turn conversation so the model always hears current-turn audio
- Support multilingual transcription (English + Spanish) without manual switching
- Add ms-level timing instrumentation for latency debugging in production
- Store agent transcripts for conversation history accuracy

**Non-Goals:**
- Changing the routing architecture or FSM state machine
- Adding new API endpoints or modifying external contracts
- Optimizing latency (instrumentation first, optimization later)
- Fixing transcript ordering issues (deferred to a separate change)

## Decisions

### 1. History in `instructions` instead of `response.input`

**Decision**: Embed conversation history as text in the `instructions` field of `response.create`, not as structured messages in `response.input`.

**Rationale**: OpenAI Realtime API's `response.input` field **replaces** the native conversation context, which includes the current turn's committed audio buffer. By using `instructions` instead, the model retains access to its native conversation (hearing the user's audio) while also receiving text-based history for multi-turn context.

**Alternative considered**: Passing audio items for history — rejected because it would add significant latency (large audio payloads re-sent each turn) and redundant re-processing.

### 2. Whisper auto-detection over forced language

**Decision**: Remove `"language": "es"` from Whisper config entirely; rely on auto-detection.

**Rationale**: Whisper's `language` parameter accepts only a single language. Auto-detection handles both English and Spanish without configuration changes. The router prompt instructs the model to respond in the customer's language.

### 3. Timing instrumentation at event boundaries

**Decision**: Add `_now_ms()` timestamps at every Coordinator event handler entry and at bridge send/receive boundaries. Log deltas (e.g., `speech_to_committed_ms`, `send_to_created_ms`).

**Rationale**: Production debugging requires knowing exactly where latency occurs. Event-boundary timing is zero-overhead when not logging and adds <1ms when active.

### 4. TurnEntry model for conversation buffer

**Decision**: Replace simple `list[dict]` with a `TurnEntry` dataclass that tracks user_text and agent_text separately, populated asynchronously as transcripts arrive.

**Rationale**: User transcript (`transcript_final`) and agent transcript (`voice_generation_completed`) arrive at different times. TurnEntry allows each to be set independently without losing data.

## Risks / Trade-offs

- **[Risk] History in instructions grows unbounded** → Mitigated by ConversationBuffer's existing max_turns limit (default 10). Text-based history is compact compared to audio.
- **[Risk] Whisper auto-detection may be less accurate than forced language** → Acceptable trade-off; Whisper v2 auto-detection is reliable for major languages. Can add language hints later if needed.
- **[Risk] Timing logs increase log volume** → Structured logging (structlog) allows filtering. Timing fields are only added to existing log lines, not new log statements.
