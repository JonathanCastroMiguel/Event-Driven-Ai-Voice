## Context

The current voice runtime processes each turn through a multi-stage pipeline:

1. Server VAD detects speech end → `input_audio_buffer.speech_stopped`
2. Whisper transcription completes → `transcript_final` (200-500ms)
3. Language detection via langid (~0.04ms)
4. Lexicon/short-utterance checks
5. Embedding Route A classification (simple/disallowed/out_of_scope/domain)
6. Embedding Route B classification if domain (sales/billing/support/retention)
7. Optional LLM fallback if ambiguous
8. Agent FSM decision → policy key or specialist
9. Prompt construction → `response.create`

Real-world testing exposed two fundamental problems:
- **Accuracy**: Embedding centroids struggle with natural conversational phrases. "Hola, ¿qué tal?" classified as `out_of_scope` (0.58) instead of greeting. Scores cluster in 0.2-0.7 range with poor separation.
- **Latency**: The pipeline adds 200-800ms on top of Whisper's 200-500ms transcription gate, making the system noticeably slower than direct Realtime API interaction.

The Realtime voice model (gpt-4o-realtime) is already capable of multilingual intent classification — it just needs the right prompt. This design replaces the embedding pipeline with a single model inference that both classifies and responds.

## Goals / Non-Goals

**Goals:**
- Reduce turn processing latency to near-zero additional overhead (single model inference)
- Improve routing accuracy by leveraging the model's native language understanding
- Simplify the architecture by removing embedding classification, language detection, and multi-step FSM from the hot path
- Maintain all existing infrastructure: barge-in, conversation buffer, persistence, debug events, filler strategy
- Keep the system testable with clear separation between router prompt logic and Coordinator orchestration

**Non-Goals:**
- Changing the frontend or WebRTC/WebSocket architecture
- Modifying external API contracts (POST /calls, SDP exchange)
- Removing embedding infrastructure entirely (may be retained for offline analytics/calibration)
- Supporting multiple simultaneous router models
- Changing the persistence schema (turns, agent_generations, voice_generations tables remain)

## Decisions

### Decision 1: Turn closing signal — `input_audio_buffer.committed` instead of `transcript_final`

**Choice**: React to `input_audio_buffer.committed` from server VAD as the turn-closing trigger.

**Rationale**: The current pipeline waits for Whisper transcription to complete before routing can begin. With model-as-router, the model receives the audio context directly via the Realtime session — there's no need to wait for a text transcript. The `committed` event fires when server VAD determines the user has stopped speaking (configurable via `silence_duration_ms`), which is the earliest reliable signal.

**Alternatives considered**:
- Keep `transcript_final` as trigger: Adds 200-500ms of unnecessary latency since the model doesn't need the transcript to classify.
- Use `speech_stopped` as trigger: Too early — fires immediately when silence begins, before the VAD has confirmed the utterance is complete. Would cause false triggers on pauses.

**Transcript handling**: `input_audio_transcription.completed` events still flow to the Coordinator but are used only for: (a) conversation buffer logging, (b) persistence, (c) debug panel display. They do NOT trigger routing.

### Decision 2: Single `response.create` with router prompt (no session.update per turn)

**Choice**: On `committed`, send a single `response.create` with the router system prompt as `instructions` and conversation history as `input`. No `session.update` per turn.

**Rationale**: `session.update` adds ~500ms round-trip. The current implementation already uses inline `instructions` in `response.create` (implemented during bugfix session). The router prompt goes in `instructions`, conversation context in `input`.

**Alternatives considered**:
- `session.update` + `response.create` per turn: Adds unnecessary latency for the session update round-trip.
- Pre-configured session with static instructions: Would prevent dynamic routing prompts that adapt to conversation state.

### Decision 3: Two response modes — direct voice vs. JSON action

**Choice**: The router prompt instructs the model to either:
- **Speak directly** (simple greetings, guardrails, out-of-scope) — the model generates audio response immediately.
- **Return JSON action** (specialist routing) — the model outputs `{"action": "specialist", "department": "<name>", "summary": "<brief>"}` as text, which the Coordinator intercepts.

**Rationale**: For simple intents (~60-70% of turns in call center scenarios), the model can respond in the same inference that classifies. This eliminates any classification→response latency. For specialist routing, the model still needs to signal which department, but the JSON format is deterministic and parseable.

**Detection mechanism**: The Bridge monitors `response.audio_transcript.delta` events. If the accumulated text starts with `{` and parses as valid JSON matching the action schema, it's intercepted as a routing action. Otherwise, it flows as normal voice output.

**Alternatives considered**:
- Always return JSON, then construct response: Adds an extra round-trip for simple cases (classify → construct prompt → response.create again). Defeats the purpose.
- Use function calling: Realtime API function calling adds latency and complexity. The model-as-router pattern is simpler.
- Modality switching (text-only for JSON, audio for direct): Could work but adds complexity. Keeping `modalities: ["text", "audio"]` always and intercepting JSON from the text transcript is simpler.

### Decision 4: Router prompt structure

**Choice**: The router prompt is a structured system instruction containing:
1. Base system identity (call center agent persona)
2. Router decision rules (when to speak directly vs. return JSON)
3. Department definitions (sales, billing, support, retention)
4. Guardrail rules (disallowed content, out-of-scope topics)
5. Language instruction (respond in same language as user)
6. Conversation history (formatted from ConversationBuffer)

**Rationale**: A single well-structured prompt replaces the entire classification pipeline. The model's native understanding handles multilingual intent, context-dependent follow-ups, and edge cases better than embedding centroids.

**Template location**: New file `router_registry/v1/router_prompt.yaml` alongside existing `policies.yaml`. Keeps router configuration declarative and version-controlled.

### Decision 5: Simplified Agent FSM

**Choice**: The Agent FSM transitions simplify from the current 6-step classification pipeline to:
- `idle` → `routing` (on `committed` event, Coordinator sends `response.create`)
- `routing` → `speaking` (model responds directly — voice output in progress)
- `routing` → `tool_execution` (model returned JSON action — run specialist tool)
- `tool_execution` → `speaking` (tool result received — construct specialist response)
- `speaking` → `done` (voice generation completed)
- Any active state → `cancelled` (barge-in)

**Rationale**: The FSM no longer performs classification — that's the model's job. The FSM tracks the lifecycle of the model's response (direct speech vs. tool-mediated).

**Alternatives considered**:
- Remove FSM entirely: Coordinator becomes too complex managing state directly. FSM provides clean state machine guarantees and testability.
- Keep current FSM with model-as-router: Unnecessary complexity — embedding states have no purpose.

### Decision 6: Bridge intercepts JSON actions from model response

**Choice**: The `OpenAIRealtimeEventBridge` accumulates `response.audio_transcript.delta` text. On `response.done`, if the accumulated transcript is valid JSON matching the action schema, it emits a new event type `model_router_action` instead of `voice_generation_completed`. The Coordinator handles this by dispatching specialist tool execution.

**Rationale**: The Bridge already sits between OpenAI events and the Coordinator. It's the natural place to detect whether the model responded with speech or a routing action. This keeps the Coordinator's event handling clean.

**Fallback**: If JSON parsing fails or the schema doesn't match, treat the response as a normal voice response. Log a warning for investigation.

### Decision 7: Server VAD configuration via session.update

**Choice**: Configure server VAD `silence_duration_ms` in the one-time `session.update` sent on WebSocket connection. Default: 500ms. Configurable via environment variable `VAD_SILENCE_DURATION_MS`.

**Rationale**: The existing one-time `session.update` (added during bugfix session) already configures `turn_detection` and `input_audio_transcription`. Adding `silence_duration_ms` is a single field addition. 500ms is a good default — short enough for responsive interaction, long enough to avoid cutting off mid-sentence pauses.

### Decision 8: Conversation history in router prompt

**Choice**: The ConversationBuffer continues to store turn entries. For the router prompt, history is formatted as a sequence of user/assistant message pairs included in the `input` array of `response.create`. The router prompt's `instructions` contain the static routing rules; the `input` contains the dynamic conversation context.

**Rationale**: Separating static instructions from dynamic context follows the Realtime API's design pattern. The model sees conversation history as prior turns, which helps with context-dependent routing (e.g., follow-up questions about billing after an initial billing inquiry).

**Transcript race condition**: Since `committed` fires before `transcript_final`, the current turn's text may not be available yet. The model has access to the audio directly, so it doesn't need the current turn's text — only prior turns for context. The current turn's transcript is appended to the buffer asynchronously when it arrives.

## Risks / Trade-offs

**[Model accuracy for routing]** → The model may occasionally misroute or respond inappropriately. Mitigation: The router prompt is iteratively tunable. Log all routing decisions for calibration. The prompt can include few-shot examples for edge cases.

**[JSON action parsing reliability]** → The model might produce malformed JSON or unexpected formats. Mitigation: Strict schema validation with fallback to treating the response as direct speech. Log parsing failures for prompt tuning.

**[Transcript race condition]** → `committed` fires before `transcript_final`, so the conversation buffer may not have the current turn's text when building the router prompt. Mitigation: The model hears the audio directly — it doesn't need the text. Prior turn history is already in the buffer. Current turn text is appended asynchronously for subsequent turns.

**[Cost increase]** → Model inference per turn may be more expensive than embedding classification. Mitigation: The model inference was already happening (for TTS/response generation). We're combining classification + response into one inference instead of classification (embeddings) + response (model). Net cost may be neutral or lower.

**[Latency regression if model is slow]** → If the Realtime model's response time degrades, there's no fast embedding fallback. Mitigation: Monitor model response latency. Filler strategy still applies for specialist routing. Direct responses should be near-instant since the model starts speaking immediately.

**[Loss of embedding analytics]** → Removing embeddings from hot path means less structured classification data. Mitigation: Retain embedding infrastructure for offline batch analysis. Log model routing decisions in structured format for calibration.

## Migration Plan

1. **Phase 1 — Router prompt + Bridge changes**: Add `input_audio_buffer.committed` event translation to Bridge. Add JSON action detection in Bridge. Create router prompt template. This can coexist with current pipeline.
2. **Phase 2 — Coordinator refactor**: Switch Coordinator's turn trigger from `transcript_final` to `committed`. Replace embedding routing dispatch with router-prompt-based `response.create`. Handle both response modes.
3. **Phase 3 — FSM simplification**: Remove embedding classification from Agent FSM. Simplify state transitions.
4. **Phase 4 — Cleanup**: Remove hot-path dependencies on embedding infrastructure, language detection. Update tests.

**Rollback**: Revert Coordinator's event handler to use `transcript_final` trigger and re-enable embedding routing. The embedding infrastructure remains available.

## Open Questions

- **Optimal `silence_duration_ms`**: 500ms is a starting point. May need tuning based on real conversations (shorter for fast-paced, longer for thoughtful speakers).
- **Router prompt few-shot examples**: How many examples to include in the prompt for reliable JSON action formatting? Need to balance prompt length vs. reliability.
- **Specialist tool execution after JSON action**: Current tool executor is a stub. The full implementation of specialist tool calls (CRM lookup, billing queries) needs separate design.
- **Echo cancellation**: The echo/feedback loop issue (AI hearing itself through mic) is a separate concern not addressed by this architecture change. Requires hardware solution (headphones) or additional client-side echo suppression.
