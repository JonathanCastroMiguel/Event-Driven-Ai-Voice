# Voice AI Runtime — Architecture Reference

Detailed documentation of the Event-Driven Voice Runtime: actors, events, processes, and end-to-end flow with code references.

---

## Table of Contents

- [1. System Overview](#1-system-overview)
- [2. Core Types and Enums](#2-core-types-and-enums)
- [3. Event System](#3-event-system)
  - [3.1 EventEnvelope](#31-eventenvelop)
  - [3.2 Event Catalog](#32-event-catalog)
  - [3.3 EventBus](#33-eventbus)
- [4. Actors](#4-actors)
  - [4.1 Coordinator (CallSession)](#41-coordinator-callsession)
  - [4.2 TurnManager](#42-turnmanager)
  - [4.3 Agent FSM](#43-agent-fsm)
  - [4.4 ToolExecutor](#44-toolexecutor)
- [5. Routing Engine](#5-routing-engine)
  - [5.1 Classification Pipeline](#51-classification-pipeline)
  - [5.2 Router Registry](#52-router-registry)
  - [5.3 Embedding Engine](#53-embedding-engine)
  - [5.4 Lexicon and Short Utterance Checks](#54-lexicon-and-short-utterance-checks)
  - [5.5 LLM Fallback](#55-llm-fallback)
  - [5.6 Language Detection](#56-language-detection)
  - [5.7 Policies](#57-policies)
- [6. Infrastructure](#6-infrastructure)
  - [6.1 Redis (Idempotency and Caching)](#61-redis-idempotency-and-caching)
  - [6.2 Session Registry](#62-session-registry)
  - [6.3 Persistence (Repositories)](#63-persistence-repositories)
  - [6.4 Realtime Client](#64-realtime-client)
  - [6.5 RealtimeVoiceProvider](#65-realtimevoiceprovider) (Protocol, StubVoiceProvider, OpenAIRealtimeProvider, factory)
  - [6.6 RealtimeVoiceBridge](#66-realtimevoicebridge)
  - [6.7 WebRTC Signaling](#67-webrtc-signaling)
- [7. Runtime State](#7-runtime-state)
- [8. End-to-End Flows](#8-end-to-end-flows)
  - [8.1 Happy Path: Simple Greeting](#81-happy-path-simple-greeting)
  - [8.2 Domain Route: Specialist Agent](#82-domain-route-specialist-agent)
  - [8.3 Barge-In During Voice Output](#83-barge-in-during-voice-output)
  - [8.4 Guardrail: Disallowed Content](#84-guardrail-disallowed-content)
  - [8.5 Ambiguous Route B: Clarify Department](#85-ambiguous-route-b-clarify-department)
  - [8.6 Multi-Turn Conversation with History](#86-multi-turn-conversation-with-history)
  - [8.7 Context-Aware Routing: Short Follow-Up](#87-context-aware-routing-short-follow-up)
- [9. Observability](#9-observability)
  - [9.1 Debug Event Emission](#91-debug-event-emission)
- [10. API Layer](#10-api-layer)
- [11. Application Startup](#11-application-startup)
- [12. Frontend Architecture](#12-frontend-architecture)
  - [12.1 Overview](#121-overview)
  - [12.2 Key Files](#122-key-files)
  - [12.3 Hooks](#123-hooks)
  - [12.4 Components](#124-components)
  - [12.5 Data Flow](#125-data-flow)
  - [12.6 Deployment](#126-deployment)

---

## 1. System Overview

The Voice AI Runtime is an event-driven system for real-time call center voice interactions. It uses four actors communicating via typed events:

```
Browser (WebRTC + VAD)
    ↕ Opus audio / DataChannels (control + debug)
RealtimeVoiceBridge (implements RealtimeClient Protocol)
    ↕ PCM audio / transcriptions
RealtimeVoiceProvider (STT/TTS — e.g. OpenAI Realtime, Deepgram)
    ↓ speech_started / transcript_final / voice_completed
Coordinator (CallSession)
    ↔ TurnManager       (turn detection)
    ↔ Agent FSM          (intent classification)
    ↔ ToolExecutor       (tool execution)
    ↓ RealtimeVoiceStart / RealtimeVoiceCancel
RealtimeVoiceBridge → RealtimeVoiceProvider (TTS) → Browser (WebRTC audio)
```

The Coordinator is the **single orchestrator** — it receives all events, delegates to actors, manages cancellation, idempotency, and emits voice output commands.

**Key files:**

| Component | File |
|---|---|
| Coordinator | `backend/src/voice_runtime/coordinator.py` |
| TurnManager | `backend/src/voice_runtime/turn_manager.py` |
| Agent FSM | `backend/src/voice_runtime/agent_fsm.py` |
| ToolExecutor | `backend/src/voice_runtime/tool_executor.py` |
| Events | `backend/src/voice_runtime/events.py` |
| Runtime State | `backend/src/voice_runtime/state.py` |
| Types/Enums | `backend/src/voice_runtime/types.py` |
| Event Bus | `backend/src/voice_runtime/bus.py` |
| Router | `backend/src/routing/router.py` |
| Policies | `backend/src/routing/policies.py` |
| RealtimeVoiceProvider | `backend/src/voice_runtime/realtime_provider.py` |
| RealtimeVoiceBridge | `backend/src/voice_runtime/realtime_bridge.py` |
| WebRTC Signaling | `backend/src/api/routes/calls.py` |
| Config | `backend/src/config.py` |

---

## 2. Core Types and Enums

Defined in `backend/src/voice_runtime/types.py`.

### Identity Types

```
CallId, TurnId, AgentGenerationId, VoiceGenerationId, ToolRequestId, EventId
```

All are `NewType` wrappers around `UUID`.

### Route A Labels (`RouteALabel`)

The first-level classification of user intent:

| Value | Meaning | Action |
|---|---|---|
| `simple` | Greeting or simple conversational turn | Guided response with `greeting` policy |
| `disallowed` | Blocked content (insults, abuse) | Guided response with `guardrail_disallowed` policy |
| `out_of_scope` | Off-topic question | Guided response with `guardrail_out_of_scope` policy |
| `domain` | Business-related intent | Proceeds to Route B classification |

### Route B Labels (`RouteBLabel`)

The second-level classification for `domain` intents:

| Value | Meaning |
|---|---|
| `sales` | Sales inquiries |
| `billing` | Billing/invoice questions |
| `support` | Technical support |
| `retention` | Customer retention |

### Policy Keys (`PolicyKey`)

Closed enum that maps to prompt templates. No free-text prompts — all output is policy-driven:

| Value | When Used |
|---|---|
| `greeting` | Simple/conversational turns |
| `guardrail_disallowed` | Blocked content detected |
| `guardrail_out_of_scope` | Off-topic content detected |
| `handoff_offer` | Transfer to human agent |
| `clarify_department` | Ambiguous Route B — ask user to clarify |

### State Machines

- **`AgentState`**: `idle → thinking → waiting_tools → waiting_voice → done` (also `cancelled`, `error`)
- **`TurnState`**: `open → finalized` (also `cancelled`)
- **`VoiceState`**: `starting → speaking → completed` (also `cancelled`, `error`)
- **`ToolState`**: `running → succeeded` (also `failed`, `cancelled`, `timeout`)

---

## 3. Event System

### 3.1 EventEnvelope

All events are wrapped in a canonical `EventEnvelope` (defined in `backend/src/voice_runtime/events.py:10`):

```python
class EventEnvelope(msgspec.Struct, frozen=True):
    event_id: UUID          # Unique per event (for idempotency)
    call_id: UUID           # Which call this belongs to
    ts: int                 # Millisecond epoch timestamp
    type: str               # Event type name (e.g. "speech_started")
    payload: dict           # Event-specific data
    source: EventSource     # Who produced this event
    correlation_id: UUID    # Usually agent_generation_id
    causation_id: UUID      # event_id of the originating event
```

`EventSource` enum values: `REALTIME`, `TURN_MANAGER`, `AGENT`, `COORDINATOR`, `TOOL_EXEC`, `TIMER`.

### 3.2 Event Catalog

Events are organized by communication direction. Each is a frozen `msgspec.Struct`.

**Realtime → Coordinator (input):**

| Event | Fields | Purpose |
|---|---|---|
| `SpeechStarted` | `call_id, ts` | User started speaking (VAD trigger) |
| `SpeechStopped` | `call_id, ts` | User stopped speaking |
| `TranscriptPartial` | `call_id, text, ts` | Partial ASR transcript |
| `TranscriptFinal` | `call_id, text, ts` | Final ASR transcript |
| `VoiceGenerationCompleted` | `call_id, voice_generation_id, ts` | Voice playback finished |
| `VoiceGenerationError` | `call_id, voice_generation_id, error, ts` | Voice playback failed |

**TurnManager → Coordinator:**

| Event | Fields | Purpose |
|---|---|---|
| `HumanTurnStarted` | `call_id, turn_id, ts` | New turn opened |
| `HumanTurnFinalized` | `call_id, turn_id, text, ts` | Turn complete with final text |
| `HumanTurnCancelled` | `call_id, turn_id, reason, ts` | Turn cancelled (barge-in) |

**Coordinator → Agent FSM:**

| Event | Fields | Purpose |
|---|---|---|
| `HandleTurn` | `call_id, turn_id, text, agent_generation_id, ts` | Process this turn |
| `CancelAgentGeneration` | `call_id, agent_generation_id, reason, ts` | Cancel current generation |
| `VoiceDone` | `call_id, agent_generation_id, voice_generation_id, status, ts` | Voice finished for this generation |

**Agent FSM → Coordinator:**

| Event | Fields | Purpose |
|---|---|---|
| `AgentStateChanged` | `call_id, agent_generation_id, state, ts` | FSM state transition |
| `RequestGuidedResponse` | `call_id, agent_generation_id, policy_key, user_text, ts` | Emit voice with this policy |
| `RequestAgentAction` | `call_id, agent_generation_id, specialist, user_text, ts` | Route to specialist agent |
| `RequestToolCall` | `call_id, agent_generation_id, tool_name, args, ts` | Execute a tool |

**Coordinator ↔ ToolExecutor:**

| Event | Fields | Purpose |
|---|---|---|
| `RunTool` | `call_id, agent_generation_id, tool_request_id, tool_name, args, timeout_ms, ts` | Start tool execution |
| `CancelTool` | `call_id, agent_generation_id, tool_request_id, reason, ts` | Cancel running tool |
| `ToolResult` | `call_id, agent_generation_id, tool_request_id, ok, payload, ts` | Tool result (success or error) |

**Coordinator → Realtime (output):**

| Event | Fields | Purpose |
|---|---|---|
| `RealtimeVoiceStart` | `call_id, agent_generation_id, voice_generation_id, prompt, ts` | Start voice synthesis |
| `RealtimeVoiceCancel` | `call_id, voice_generation_id, reason, ts` | Cancel active voice playback |

The `prompt` field in `RealtimeVoiceStart` is either a `str` (for specialist/filler) or `list[dict[str, str]]` (chat messages for guided responses).

### 3.3 EventBus

Defined in `backend/src/voice_runtime/bus.py`. An in-process async event bus backed by `asyncio.Queue`:

- **`register(event_type, handler)`** — Register a handler for an event type (one handler per type)
- **`publish(event)`** — Enqueue an event
- **`run()`** — Infinite loop: dequeue → dispatch to handler. Unhandled types are logged. Handler exceptions are caught and logged (never crash the bus)
- **Max queue size**: 1000 (configurable via `maxsize`)

---

## 4. Actors

### 4.1 Coordinator (CallSession)

**File**: `backend/src/voice_runtime/coordinator.py`

The Coordinator is the central orchestrator for a single call. One `Coordinator` instance exists per active call.

**Constructor dependencies:**

| Parameter | Type | Purpose |
|---|---|---|
| `call_id` | `UUID` | Unique call identifier |
| `turn_manager` | `TurnManager` | Delegates speech/transcript events |
| `agent_fsm` | `AgentFSM` | Delegates classification |
| `tool_executor` | `ToolExecutor` | Delegates tool execution |
| `router` | `Router` | Intent classification engine |
| `policies` | `PoliciesRegistry` | Policy templates for prompts |
| `seen_events` | `TTLSet` (optional) | Redis-backed idempotency set |
| `tool_cache` | `TTLMap` (optional) | Redis-backed tool result cache |
| `turn_repo` | `TurnRepository` (optional) | DB persistence for turns |
| `agent_gen_repo` | `AgentGenerationRepository` (optional) | DB persistence for agent generations |
| `voice_gen_repo` | `VoiceGenerationRepository` (optional) | DB persistence for voice generations |
| `max_history_turns` | `int` (default: 10) | Max turns in conversation buffer |
| `max_history_chars` | `int` (default: 2000) | Max total user_text chars in buffer |
| `routing_context_window` | `int` (default: 1) | Prior turns used for embedding enrichment |
| `routing_short_text_chars` | `int` (default: 20) | Text length threshold for embedding enrichment |
| `llm_context_window` | `int` (default: 3) | Prior turns included in LLM fallback context |

**Main entry point**: `handle_event(envelope)` at line 142. This method:

1. Checks idempotency (Redis TTLSet or in-memory fallback)
2. Opens an OpenTelemetry span with `call_id`, `event_type`, `turn_id`, `agent_generation_id`
3. Dispatches via `match envelope.type` to handler methods

**Event handlers:**

| Event Type | Method | What It Does |
|---|---|---|
| `speech_started` | `_on_speech_started` | Barge-in: cancel active voice + generation + filler. Forward to TurnManager |
| `transcript_final` | `_on_transcript_final` | Forward to TurnManager, drain turn events, process finalized turns |
| `human_turn_finalized` | `_on_human_turn_finalized` | The core turn processing: classify → FSM → prompt → voice start |
| `request_guided_response` | `_on_request_guided_response` | Build prompt from policy, emit `RealtimeVoiceStart` |
| `request_agent_action` | `_on_request_agent_action` | Emit specialist voice start (optionally with filler) |
| `tool_result` | `_on_tool_result` | Handle late/cancelled results, cancel filler |
| `voice_generation_completed` | `_on_voice_completed` | Clear active voice, persist completion |
| `voice_generation_error` | `_on_voice_error` | Clear active voice, persist error |

**Idempotency** (line 118): Uses Redis `TTLSet` with `SET NX EX` pattern. If Redis is unavailable, falls back to an in-memory `set[str]`.

**Barge-in handling** (line 177): When `speech_started` arrives while voice is playing:
1. Cancel active voice → emit `RealtimeVoiceCancel` with `reason="barge_in"`
2. Cancel active agent generation → emit `CancelAgentGeneration`, cancel/reset FSM
3. Cancel filler task if running
4. Persist cancellation to DB (fire-and-forget)
5. Forward to TurnManager to open new turn

**Prompt construction** (line 424): For guided responses, builds a prompt with conversation history:
```python
[
    {"role": "system", "content": base_system_prompt},
    {"role": "system", "content": policy_instructions},
    *conversation_buffer.format_messages(),  # alternating user/assistant history
    {"role": "user",   "content": user_text},
]
```
On the first turn the buffer is empty, so the prompt is `[system, policy, user]` (3 messages). On subsequent turns, history messages are injected between the system messages and the current user message.

**Conversation Buffer** (`backend/src/voice_runtime/conversation_buffer.py`): A `ConversationBuffer` instance is created per call alongside `CoordinatorRuntimeState`. It accumulates `TurnEntry` records (frozen dataclass: `seq`, `user_text`, `route_a_label`, `policy_key`, `specialist`) after each successful `RealtimeVoiceStart` emission. Cancelled turns (barge-in) are never appended. The buffer enforces two bounds: `max_turns` (sliding window, default 10) and `max_chars` (character budget on total `user_text`, default 2000). `format_messages()` returns alternating `user`/`assistant` messages where assistant content is `[{policy_key}] Guided response` or `[{route_a_label}] Specialist: {specialist}`.

**Context-Aware Routing** (`backend/src/routing/context.py`): A `RoutingContextBuilder` is instantiated per Coordinator with `short_text_chars`, `context_window`, and `llm_context_window` from Settings. Before each `Router.classify()` call, the Coordinator calls `builder.build(user_text, language, buffer)` which returns a `RoutingContext(enriched_text, llm_context)`. The two context layers are independently configurable:
- **Layer 1 (embedding enrichment)**: For short texts (< `routing_short_text_chars`), concatenates the previous turn's `user_text` (from `context_window=1` most recent entry) with the current text for richer embedding classification.
- **Layer 2 (LLM fallback context)**: Produces a structured multi-turn context string with up to `llm_context_window` (default: 3) prior turns in a labeled format: `turn[-N] user: {text}` / `turn[-N] route: {label}`. This enables the LLM to reason about conversation flow across 2-3 turns, significantly improving disambiguation of short follow-ups.

Both outputs are passed to `Router.classify()` as optional parameters — the original `user_text` is preserved for lexicon checks, short utterance checks, prompt construction, and buffer storage.

**Filler strategy** (line 604): Disabled by default (`_should_emit_filler()` returns `False`). When enabled, emits a brief filler voice ("Un momento, por favor.") before specialist responses, with a 1200ms auto-cancel timeout.

**Output events**: Accumulated in `_output_events` list, drained via `drain_output_events()`.

**Persistence pattern** (line 107): Fire-and-forget via `_persist_safe()`:
```python
async def _persist_safe(self, coro):
    try:
        await coro
    except Exception:
        logger.warning("persistence_error", exc_info=True)
```
Repos are optional. If `None`, persistence is silently skipped. If the repo call fails, it's logged but never crashes the voice hot path.

### 4.2 TurnManager

**File**: `backend/src/voice_runtime/turn_manager.py`

Detects human speech turns from VAD/transcript events. Has **no knowledge** of tools, agents, or routing.

**State:**
- `_current_turn_id`: UUID of the currently open turn (or None)
- `_current_state`: `TurnState` (OPEN, FINALIZED, CANCELLED)
- `_seq`: Monotonically increasing turn counter
- `_pending_events`: Buffer of output events to drain

**Methods:**

| Method | Input | Output | Logic |
|---|---|---|---|
| `handle_speech_started(ts)` | Timestamp | `HumanTurnStarted` | If a turn is OPEN, cancel it (barge-in). Open new turn, increment seq |
| `handle_transcript_final(text, ts)` | Text + timestamp | `HumanTurnFinalized` | If turn is OPEN, finalize it with the text |
| `handle_no_transcript_timeout(ts)` | Timestamp | `HumanTurnCancelled` | Cancel open turn if no transcript arrived |
| `drain_events()` | — | List of turn events | Return and clear the pending events buffer |

**Turn lifecycle:**
```
speech_started → OPEN
  ├─ transcript_final → FINALIZED
  ├─ speech_started (new) → CANCELLED (barge-in) + new OPEN
  └─ timeout → CANCELLED (no_transcript)
```

### 4.3 Agent FSM

**File**: `backend/src/voice_runtime/agent_fsm.py`

Finite state machine for agent generation lifecycle. Classifies user intent and emits routing events. Does NOT execute tools or call the Realtime API directly.

**State transitions** (line 18):

```
IDLE ──handle_turn──→ THINKING
THINKING ──classification_done──→ DONE
THINKING ──needs_tools──→ WAITING_TOOLS ──tools_done──→ WAITING_VOICE ──voice_done──→ DONE
Any active state ──cancel──→ CANCELLED
Any active state ──error──→ ERROR
DONE, CANCELLED, ERROR are terminal states
```

**`handle_turn()` method** (line 106):

Takes routing results (from Router) and decides the action:

1. If Route A is `simple`/`disallowed`/`out_of_scope`:
   - Map to PolicyKey via `ROUTE_A_POLICY_MAP` (line 44)
   - Emit `RequestGuidedResponse` with that policy key
   - Transition: IDLE → THINKING → DONE

2. If Route A is `domain`:
   - If Route B is `None` (ambiguous): Emit `RequestGuidedResponse` with `clarify_department`
   - If Route B has a value: Emit `RequestAgentAction` with specialist label
   - Transition: IDLE → THINKING → DONE

**`cancel()` method** (line 176): Transitions to CANCELLED if in an active state (THINKING, WAITING_TOOLS, WAITING_VOICE).

**`reset()` method** (line 182): Returns to IDLE for the next generation cycle.

**Output**: `AgentFSMOutput` dataclass containing `state_changes`, `guided_responses`, and `agent_actions` lists.

### 4.4 ToolExecutor

**File**: `backend/src/voice_runtime/tool_executor.py`

Executes tools with whitelist validation, Redis caching, timeout, and cancellation.

**Tool registration**: Tools are registered by name via `register_tool(name, func)`. Only registered tools can execute (whitelist, line 60).

**`execute()` method** (line 48):

1. **Whitelist check**: Reject unknown tools immediately
2. **Cache check**: Look up `tool_request_id` in Redis TTLMap. If hit, return cached result
3. **Execute with timeout**: `asyncio.wait_for(tool_func(**args), timeout=timeout_s)`
4. **Cache on success**: Store result in Redis TTLMap
5. **Error handling**: Returns `ToolResult(ok=False)` for timeout, cancellation, or exceptions

**Deterministic `tool_request_id`** (line 22): Generated from `agent_generation_id + tool_name + SHA256(args)` using `uuid5`. This ensures the same tool call always produces the same ID, enabling idempotent caching.

**Cancellation** (line 140): `cancel(tool_request_id)` finds the running `asyncio.Task` and calls `.cancel()` on it.

---

## 5. Routing Engine

### 5.1 Classification Pipeline

**File**: `backend/src/routing/router.py`

The `Router.classify(text, language, enriched_text=None, llm_context=None)` method (line 64) runs a multi-step pipeline:

```
Input text + optional enriched_text + optional llm_context
  │
  ├─ Step 1: Lexicon check (original text, exact word match) ──→ DISALLOWED
  │
  ├─ Step 2: Short utterance check (original text, ≤N chars) ──→ SIMPLE
  │
  ├─ Step 3: Route A embedding classification (uses enriched_text if provided)
  │    ├─ If confident → Route A label
  │    └─ If ambiguous (score < threshold AND margin < ambiguous_margin)
  │         └─ LLM fallback (uses llm_context if provided) → Route A label
  │
  └─ Step 4: If Route A = DOMAIN → Route B embedding (uses enriched_text if provided)
       ├─ If confident → RouteBLabel (sales/billing/support/retention)
       ├─ If ambiguous → LLM fallback (uses llm_context if provided)
       └─ If still ambiguous → route_b_label=None (triggers clarify_department)
```

**Context enrichment**: The Coordinator's `RoutingContextBuilder` produces `enriched_text` for short follow-up turns (< 20 chars by default) by concatenating the previous turn's text. Lexicon and short utterance checks always use the original `text` to ensure exact-match behavior is preserved.

**Returns**: `RoutingResult` dataclass (line 23) with:
- `route_a_label`, `route_a_confidence`, `route_a_margin` (top1 - top2)
- `route_b_label`, `route_b_confidence`, `route_b_margin` (optional)
- `short_circuit` ("lexicon", "short_utterance", or None)
- `fallback_used` (bool)
- `all_scores_a`, `all_scores_b` (full score maps for calibration logging)

**Calibration logging**: Every `classify()` call emits a `routing_completed` structured log with `router_version`, `language`, all scores/margins, `short_circuit`, and `fallback_used`. Used for threshold recalibration from production data.

### 5.2 Router Registry

**File**: `backend/src/routing/registry.py`

Versioned YAML configuration loaded from `backend/router_registry/v1/`:

```
router_registry/v1/
  ├── thresholds.yaml        # Confidence thresholds, margins, filler/fallback config
  ├── policies.yaml          # Base system prompt + policy templates
  ├── route_a/
  │   ├── base.yaml          # Route A training examples (default locale)
  │   └── es.yaml            # Spanish-specific examples
  ├── route_b/
  │   ├── base.yaml          # Route B training examples
  │   └── es.yaml
  ├── lexicon_disallowed/
  │   └── es.txt             # One disallowed word/phrase per line
  └── short_utterances/
      └── es.yaml            # Category → list of short phrases
```

**`ThresholdsConfig`** (line 11): Parsed from `thresholds.yaml`:
- `version`: Registry version string
- `route_a[label]["high"|"medium"]`: Per-label confidence thresholds
- `route_b[label]["high"|"medium"]`: Per-label confidence thresholds
- `ambiguous_margin`: Minimum margin between top-1 and top-2 scores
- `short_text_len_chars`: Max chars for short utterance matching
- `fallback_enable`, `fallback_min_score`, `fallback_max_latency_budget_ms`
- `filler_enable`, `filler_start_after_ms`, `filler_max_ms`

**Language inheritance**: Each data source (examples, lexicon, short utterances) has a `base` locale and optional per-language overrides. If the detected language matches, use the locale-specific data; otherwise fall back to `base`.

### 5.3 Embedding Engine

**File**: `backend/src/routing/embeddings.py`

Uses `sentence-transformers` model (`all-MiniLM-L6-v2` by default) for text embedding and cosine similarity classification.

**Startup flow:**
1. `EmbeddingEngine.load()` (line 25): Loads the sentence-transformers model
2. `Router.precompute_centroids()` (line 52 of router.py): For each locale and each label, compute the centroid (mean of normalized embeddings of training examples)

**Classification flow** (`classify()` at line 66):
1. Embed the input text
2. Compute cosine similarity against each label's centroid
3. Return `(best_label, best_score, all_scores)`

**`get_top_two()`** (line 76): Helper to extract the top-2 scoring labels for margin computation.

### 5.4 Lexicon and Short Utterance Checks

**File**: `backend/src/routing/lexicon.py`

- **`check_lexicon(text, disallowed)`** (line 4): Case-insensitive substring match against a set of disallowed words/phrases. Returns `True` if any disallowed word is found in the text.

- **`check_short_utterance(text, short_utterances, max_chars)`** (line 10): If text is ≤ `max_chars`, check for exact match (case-insensitive) against short utterance phrase lists. Returns the category name (e.g. `"greetings"`) or `None`.

### 5.5 LLM Fallback

**File**: `backend/src/routing/llm_fallback.py`

Async HTTP client for 3rd-party LLM classification when embeddings are ambiguous.

- **Protocol**: POST to `llm_fallback_url` with chat completions format (compatible with OpenAI API)
- **Model**: Configurable via `llm_fallback_model` (default: `gpt-4o-mini`)
- **Timeout**: Configurable via `llm_fallback_timeout_s` (default: 2.0s)
- **Prompt**: Asks the LLM to classify text into one of the given labels, respond with JSON `{"label": "...", "confidence": 0.0-1.0}`
- **Context parameter**: Accepts a `context` string. When context-aware routing is active, the Coordinator passes a structured multi-turn context with up to 3 prior turns (configurable via `llm_context_window`), formatted as `language={lang}\nturn[-N] user: {text}\nturn[-N] route: {label}` lines. This enables the LLM to reason about conversational continuity across multiple turns
- **Failure mode**: Returns `None` on timeout or error — classification continues without fallback

### 5.6 Language Detection

**File**: `backend/src/routing/language.py`

Uses Facebook's fasttext language identification model (`lid.176.ftz`).

- **Model loading**: Lazy-loaded on first call. Checks local path → env var → downloads via `huggingface_hub`
- **Supported languages**: `es`, `en`. Unsupported languages fall back to `es` (default)
- **Error handling**: Returns default language on any exception

### 5.7 Policies

**File**: `backend/src/routing/policies.py`

- **`PoliciesRegistry`**: Holds a `base_system` prompt and a dictionary of policy key → instructions text
- **`get_instructions(policy_key)`** (line 15): Returns the instructions string for a PolicyKey
- **`build_prompt(policy_key, user_text)`** (line 21): Concatenates base_system + policy instructions + user text into a single string
- **`load_policies(registry_path)`** (line 26): Loads from `policies.yaml`. Validates that all `PolicyKey` enum values have entries

---

## 6. Infrastructure

### 6.1 Redis (Idempotency and Caching)

**File**: `backend/src/infrastructure/redis_client.py`

Two Redis-backed data structures:

**`TTLSet`** (line 18): Used for event idempotency. Each event_id is stored as a Redis key with TTL.
- `add(member)`: `SET key "1" NX EX ttl` — returns `True` if newly added
- `contains(member)`: `EXISTS key`

**`TTLMap`** (line 38): Used for tool result caching.
- `get(key)`: `GET key`
- `set(key, value)`: `SET key value EX ttl`

Default TTL: 300 seconds.

### 6.2 Session Registry

**File**: `backend/src/infrastructure/session_registry.py`

`RedisSessionRegistry` tracks active call sessions as Redis hashes:
- `register(call_id, data)`: Store session data as hash fields with 1-hour TTL
- `get(call_id)`: Retrieve session hash
- `update_field(call_id, field, value)`: Update a single field
- `remove(call_id)`: Delete session hash

### 6.3 Persistence (Repositories)

**Directory**: `backend/src/infrastructure/repositories/`

Five PostgreSQL repositories, one per entity:

| Repository | Table | Entity |
|---|---|---|
| `PgCallRepository` | `call_sessions` | CallSession |
| `PgTurnRepository` | `turns` | Turn |
| `PgAgentGenerationRepository` | `agent_generations` | AgentGeneration |
| `PgVoiceGenerationRepository` | `voice_generations` | VoiceGeneration |
| `PgToolExecutionRepository` | `tool_executions` | ToolExecution |

All repos use raw `asyncpg` for maximum performance. Tables are created via Alembic migration at `backend/alembic/versions/9ec54cec5c1d_create_core_tables.py`.

**Fire-and-forget pattern**: The Coordinator calls repos through `_persist_safe()` — failures are logged but never block the voice hot path. Repos are optional (`None` if not injected).

### 6.4 Realtime Client

**File**: `backend/src/voice_runtime/realtime_client.py`

**`RealtimeClient` Protocol** (line 22):
- `send_voice_start(event)`: Start voice synthesis on the provider
- `send_voice_cancel(event)`: Cancel active voice playback
- `on_event(callback)`: Register callback for provider events
- `close()`: Clean up resources

**`StubRealtimeClient`** (line 45): Test implementation that:
- Tracks all `voice_starts` and `voice_cancels` for assertions
- Auto-emits `VoiceGenerationCompleted` after a configurable delay
- Supports error injection via `fail_voice_ids` set
- Respects cancellation (cancelled IDs skip completion emission)

### 6.5 RealtimeVoiceProvider

**File**: `backend/src/voice_runtime/realtime_provider.py`

**`RealtimeVoiceProvider` Protocol** — abstraction for streaming STT/TTS providers (OpenAI Realtime, Deepgram, etc.):
- `async send_audio(frame: bytes)`: Send a PCM audio frame to the STT engine
- `async receive_transcription() -> AsyncIterator[TranscriptionEvent]`: Yield transcription events (partial/final) as they arrive
- `async send_text_for_tts(text: str) -> AsyncIterator[bytes]`: Send text for TTS, yield PCM audio frames as generated
- `async close()`: Clean up provider resources

**`TranscriptionEvent`** dataclass: `text: str`, `is_final: bool`.

**`StubVoiceProvider`** (line 43): Test implementation that returns canned transcriptions and silent audio frames. Stores received audio for assertions.

**`create_voice_provider()`** (line 79): Async factory function that returns `OpenAIRealtimeProvider` when `OPENAI_API_KEY` is set, otherwise `StubVoiceProvider`. Called during SDP offer handling in `calls.py`.

**`OpenAIRealtimeProvider`** — File: `backend/src/voice_runtime/openai_realtime_provider.py`

Production implementation backed by the OpenAI Realtime API (`gpt-4o-mini-realtime-preview`). Uses a single persistent WebSocket per call for bidirectional streaming STT and TTS, optimized for minimum latency.

| Method | Behavior |
|---|---|
| `connect()` | Opens WebSocket to `wss://api.openai.com/v1/realtime`, starts background reader task |
| `send_audio(frame)` | Downsamples 48kHz→24kHz (every 2nd sample), base64-encodes, sends `input_audio_buffer.append` (fire-and-forget) |
| `commit_audio_buffer()` | Sends `input_audio_buffer.commit` to trigger transcription |
| `receive_transcription()` | Yields `TranscriptionEvent` from internal STT queue (fed by reader) |
| `send_text_for_tts(text)` | Sends `response.create`, yields PCM16 audio frames from TTS queue |
| `close()` | Cancels reader, closes WebSocket, signals queues |

**Architecture**: Fire-and-forget sends + async reader task. Reader routes `conversation.item.input_audio_transcription.completed` → STT queue, `response.audio.delta` → TTS queue (base64-decoded), `response.audio.done` → None sentinel.

### 6.6 RealtimeVoiceBridge

**File**: `backend/src/voice_runtime/realtime_bridge.py`

Bridges WebRTC audio ↔ `RealtimeVoiceProvider` ↔ Coordinator. Implements the `RealtimeClient` Protocol so the Coordinator uses it as a drop-in replacement for `StubRealtimeClient`.

**Constructor dependencies:**

| Parameter | Type | Purpose |
|---|---|---|
| `call_id` | `UUID` | Unique call identifier |
| `provider` | `RealtimeVoiceProvider` | STT/TTS provider instance |
| `control_channel` | `RTCDataChannel` | For VAD signals + transcriptions |
| `debug_channel` | `RTCDataChannel` | For telemetry data |

**RealtimeClient Protocol methods:**

| Method | What It Does |
|---|---|
| `send_voice_start(event)` | Streams `event.prompt` to `provider.send_text_for_tts()`, emits `voice_generation_completed` when done |
| `send_voice_cancel(event)` | Adds voice_id to cancelled set, cancels active TTS task |
| `on_event(callback)` | Registers Coordinator's event callback |
| `close()` | Cancels all async tasks, closes provider |

**Audio forwarding** (line 143): `start_audio_forwarding(track)` creates an async task that reads frames from the WebRTC audio track (`track.recv()`), converts to PCM via `to_ndarray().tobytes()`, and sends to `provider.send_audio()`.

**STT listener** (line 162): `start_stt_listener()` creates an async task that iterates `provider.receive_transcription()`, forwards transcription JSON to browser via control DataChannel, and dispatches final transcriptions as `transcript_final` EventEnvelopes to the Coordinator.

**VAD signal handling** (line 197): Parses `speech_started`/`speech_ended` JSON from the control DataChannel. Maps browser `speech_ended` to internal `speech_stopped` event type (matching the `SpeechStopped` event in `events.py`). On `speech_ended`, also calls `provider.commit_audio_buffer()` if available (triggers transcription of accumulated audio).

**Debug forwarding** (line 244): `emit_debug(event)` sends debug JSON to the debug DataChannel when debug mode is enabled. Debug enable/disable is toggled via control DataChannel messages.

### 6.7 WebRTC Signaling

**File**: `backend/src/api/routes/calls.py`

REST-based WebRTC signaling for browser-to-backend audio connections. Uses `aiortc` for server-side WebRTC.

**In-memory session registry**: `_sessions: dict[UUID, CallSessionEntry]` tracks active WebRTC calls. Each entry holds:
- `call_id`, `peer_connection`, `coordinator`, `bridge`, `control_channel`, `debug_channel`

**ICE configuration**: Built from environment variables via `build_rtc_configuration()`:
- `STUN_SERVERS` (default: `stun:stun.l.google.com:19302`)
- `TURN_SERVERS`, `TURN_USERNAME`, `TURN_CREDENTIAL` (optional, for NAT traversal)

**Endpoints:**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/calls` | POST | Create call session, returns `call_id` |
| `/api/v1/calls/{call_id}/offer` | POST | Accept SDP offer, create `RTCPeerConnection` with audio transceiver (sendrecv) and DataChannels ("control", "debug"), return SDP answer |
| `/api/v1/calls/{call_id}/ice` | POST | Receive trickle ICE candidates (logged; aiortc gathers during SDP exchange) |
| `/api/v1/calls/{call_id}` | DELETE | End call, clean up all resources |

**Peer connection lifecycle:**
- Audio transceiver added as `sendrecv` for bidirectional Opus audio
- DataChannels created server-side: `"control"` (ordered) and `"debug"` (ordered)
- During SDP offer handling: `create_voice_provider()` selects provider, creates `RealtimeVoiceBridge`, starts STT listener, and registers `on("track")` handler for audio forwarding
- `connectionstatechange` event triggers auto-cleanup on `"failed"` or `"closed"` states (closes bridge + provider)
- `MAX_CONCURRENT_CALLS` (default: 50) enforced at session creation

---

## 7. Runtime State

**File**: `backend/src/voice_runtime/state.py`

`CoordinatorRuntimeState` is an **in-memory dataclass** (not persisted to DB) that tracks the transient state of one active call:

| Field | Type | Purpose |
|---|---|---|
| `call_id` | `UUID` | The call this state belongs to |
| `active_turn_id` | `UUID \| None` | Currently active turn |
| `active_agent_generation_id` | `UUID \| None` | Currently active agent generation |
| `active_voice_generation_id` | `UUID \| None` | Currently active voice output |
| `active_tool_request_id` | `UUID \| None` | Currently active tool execution |
| `cancelled_agent_generations` | `set[UUID]` | Set of cancelled generation IDs |
| `cancelled_voice_generations` | `set[UUID]` | Set of cancelled voice IDs |
| `turn_seq` | `int` | Monotonic turn counter |

**Key methods:**
- `is_generation_cancelled(id)` / `is_voice_cancelled(id)`: Check if an ID was cancelled (used for late result filtering)
- `cancel_active_generation()`: Move active generation to cancelled set, return its ID
- `cancel_active_voice()`: Move active voice to cancelled set, return its ID

This state is ephemeral — destroyed when the call ends. The cancelled sets grow unboundedly within a call but are small in practice (typically < 10 entries per call).

---

## 8. End-to-End Flows

### 8.1 Happy Path: Simple Greeting

User says: "hola buenos días"

```
1. Realtime Provider → speech_started event
2. Coordinator._on_speech_started()
   → TurnManager.handle_speech_started() → opens turn (seq=1)
3. Realtime Provider → transcript_final("hola buenos días")
4. Coordinator._on_transcript_final()
   → TurnManager.handle_transcript_final() → HumanTurnFinalized
5. Coordinator._on_human_turn_finalized()
   a. detect_language("hola buenos días") → "es"
   b. Router.classify("hola buenos días", "es")
      → Lexicon check: no match
      → Short utterance check: too long (>max_chars) or not in list
      → Route A embeddings: best="simple", confidence=0.92
      → RoutingResult(route_a_label=SIMPLE, confidence=0.92)
   c. Persist turn + agent generation (fire-and-forget)
   d. AgentFSM.handle_turn(route_a=SIMPLE)
      → RequestGuidedResponse(policy_key="greeting")
6. Coordinator._on_request_guided_response()
   → buffer.format_messages() → [] (empty, first turn)
   → Build prompt: [system: base, system: greeting_policy, user: "hola buenos días"]
   → Emit RealtimeVoiceStart with prompt
   → buffer.append(TurnEntry(seq=1, user_text="hola buenos días", ...))
   → Persist voice generation (fire-and-forget)
7. Realtime Provider plays voice → voice_generation_completed
8. Coordinator._on_voice_completed()
   → Clear active_voice_generation_id
   → Persist completion
```

### 8.2 Domain Route: Specialist Agent

User says: "tengo un problema con mi factura"

```
1-4. Same as above until turn finalized
5. Coordinator._on_human_turn_finalized()
   a. detect_language → "es"
   b. Router.classify:
      → Lexicon: no match
      → Short utterance: no match
      → Route A embeddings: best="domain", confidence=0.85
      → Route B embeddings: best="billing", confidence=0.88
      → RoutingResult(route_a=DOMAIN, route_b=BILLING)
   c. AgentFSM.handle_turn(route_a=DOMAIN, route_b=BILLING)
      → RequestAgentAction(specialist="billing")
6. Coordinator._on_request_agent_action()
   → Emit RealtimeVoiceStart(prompt="Specialist: billing. User said: ...")
```

### 8.3 Barge-In During Voice Output

User interrupts while the system is speaking:

```
1. Turn 1 completes → voice is playing (active_voice_generation_id is set)
2. Realtime Provider → speech_started (barge-in)
3. Coordinator._on_speech_started():
   a. cancel_active_voice() → adds voice_id to cancelled set
      → Emit RealtimeVoiceCancel(reason="barge_in")
      → BARGE_IN_TOTAL.inc() (Prometheus counter)
   b. cancel_active_generation() → adds gen_id to cancelled set
      → Emit CancelAgentGeneration(reason="barge_in")
      → FSM.cancel() + FSM.reset()
      → Persist cancellation (fire-and-forget)
   c. _cancel_filler() → cancel filler task if running
   d. TurnManager.handle_speech_started() → cancel old turn, open new turn
4. transcript_final → new turn proceeds normally
```

Any late results from the cancelled generation are silently ignored via `is_generation_cancelled()` checks.

### 8.4 Guardrail: Disallowed Content

User says: "maldita sea" (insult in lexicon)

```
1-4. Same until turn finalized
5. Router.classify:
   → Lexicon check: "maldita sea" matches disallowed list
   → RoutingResult(route_a=DISALLOWED, confidence=1.0, short_circuit="lexicon")
   (Embeddings and Route B are never reached)
6. AgentFSM.handle_turn(route_a=DISALLOWED)
   → RequestGuidedResponse(policy_key="guardrail_disallowed")
7. Coordinator emits voice with guardrail_disallowed policy
```

If the insult is NOT in the lexicon:
- Falls through to embedding classification
- If embeddings classify as `disallowed` with sufficient confidence → guardrail response
- If embeddings don't catch it → passes as `simple`/`domain` (3rd-party LLM guardrails may still catch it)

### 8.5 Ambiguous Route B: Clarify Department

User says: "tengo un problema" (unclear which department)

```
5. Router.classify:
   → Route A: "domain", confidence=0.80
   → Route B: best="support", confidence=0.45, margin=0.05
   → is_ambiguous_b = True (score < threshold AND margin < ambiguous_margin)
   → LLM fallback (if enabled): may resolve or return None
   → If still ambiguous: RoutingResult(route_a=DOMAIN, route_b=None)
6. AgentFSM.handle_turn(route_a=DOMAIN, route_b=None)
   → RequestGuidedResponse(policy_key="clarify_department")
7. Coordinator emits voice asking user to clarify which department
```

### 8.6 Multi-Turn Conversation with History

User has a multi-turn conversation: "hola" → "mi factura" → "¿cuánto debo?"

```
=== Turn 1: "hola" ===
1. speech_started → transcript_final("hola")
2. Router.classify → SIMPLE → AgentFSM → RequestGuidedResponse(policy_key="greeting")
3. Coordinator._on_request_guided_response():
   a. buffer.format_messages() → [] (empty, first turn)
   b. Build prompt: [system: base, system: greeting_policy, user: "hola"]
   c. Emit RealtimeVoiceStart
   d. buffer.append(TurnEntry(seq=1, user_text="hola", route_a_label="greeting", policy_key="greeting"))
4. Voice plays → voice_generation_completed

=== Turn 2: "mi factura" ===
5. speech_started (barge-in: cancels turn 1 voice) → transcript_final("mi factura")
6. Router.classify → DOMAIN, route_b=BILLING → AgentFSM → RequestAgentAction(specialist="billing")
7. Coordinator._on_request_agent_action():
   a. Emit RealtimeVoiceStart(prompt="Specialist: billing. User said: mi factura")
   b. buffer.append(TurnEntry(seq=2, user_text="mi factura", route_a_label="domain", specialist="billing"))
8. Voice plays → voice_generation_completed

=== Turn 3: "¿cuánto debo?" ===
9.  speech_started → transcript_final("¿cuánto debo?")
10. Router.classify("¿cuánto debo?", "es") → SIMPLE (classified in isolation)
    → AgentFSM → RequestGuidedResponse(policy_key="greeting")
11. Coordinator._on_request_guided_response():
    a. buffer.format_messages() → [
         {role: "user", content: "hola"},
         {role: "assistant", content: "[greeting] Guided response"},
         {role: "user", content: "mi factura"},
         {role: "assistant", content: "[domain] Specialist: billing"}
       ]
    b. Build prompt: [
         system: base,
         system: greeting_policy,
         user: "hola",                                    ← history
         assistant: "[greeting] Guided response",          ← history
         user: "mi factura",                               ← history
         assistant: "[domain] Specialist: billing",        ← history
         user: "¿cuánto debo?"                             ← current turn
       ]
    c. Emit RealtimeVoiceStart — LLM sees full conversation context
    d. buffer.append(TurnEntry(seq=3, ...))
```

**Key behaviors:**
- The router classifies with **context-aware enrichment**: short follow-up texts (< 20 chars) get enriched with the previous turn's text for embedding classification. The LLM fallback also receives conversation context when triggered. See [8.7](#87-context-aware-routing-short-follow-up) for details.
- `TurnEntry` is appended **after** `RealtimeVoiceStart` emission — cancelled turns never enter the buffer.
- Buffer pruning (max 10 turns, max 2000 chars of `user_text`) ensures bounded prompt growth.

### 8.7 Context-Aware Routing: Short Follow-Up

User says "tengo un problema con mi factura" (turn 1), "no me llega el recibo" (turn 2), then "de este mes" (turn 3, short follow-up).

```
=== Turn 1: "tengo un problema con mi factura" ===
1. speech_started → transcript_final("tengo un problema con mi factura")
2. RoutingContextBuilder.build():
   → buffer is empty → RoutingContext(enriched_text=None, llm_context=None)
3. Router.classify("tengo un problema con mi factura", "es")
   → Route A: DOMAIN → Route B: BILLING
4. AgentFSM → RequestAgentAction(specialist="billing")
5. buffer.append(TurnEntry(seq=1, user_text="tengo un problema con mi factura", route_a_label="domain", specialist="billing"))

=== Turn 2: "no me llega el recibo" ===
6. speech_started → transcript_final("no me llega el recibo")
7. RoutingContextBuilder.build("no me llega el recibo", "es", buffer):
   → len = 21 >= 20 → Layer 1 inactive (enriched_text=None)
   → Layer 2: llm_context with 1 prior turn:
     language=es
     turn[-1] user: tengo un problema con mi factura
     turn[-1] route: domain
8. Router.classify → DOMAIN → BILLING
9. buffer.append(TurnEntry(seq=2, user_text="no me llega el recibo", ...))

=== Turn 3: "de este mes" (11 chars, < 20 threshold) ===
10. speech_started → transcript_final("de este mes")
11. RoutingContextBuilder.build("de este mes", "es", buffer):
    → len("de este mes") = 11 < 20 → Layer 1 active
    → enriched_text = "no me llega el recibo. de este mes" (context_window=1, most recent)
    → Layer 2: llm_context with 2 prior turns (llm_context_window=3, only 2 available):
      language=es
      turn[-2] user: tengo un problema con mi factura
      turn[-2] route: domain
      turn[-1] user: no me llega el recibo
      turn[-1] route: domain
12. Router.classify("de este mes", "es",
      enriched_text="no me llega el recibo. de este mes",
      llm_context=<multi-turn context>):
    → Lexicon check on "de este mes" → no match
    → Short utterance check on "de este mes" → no match
    → Route A embeddings on enriched text → DOMAIN
    → Route B embeddings on enriched text → BILLING
    → If ambiguous, LLM fallback receives multi-turn llm_context for conversational reasoning
13. AgentFSM → RequestAgentAction(specialist="billing")
    → Correct classification despite the short, ambiguous follow-up
```

**Key behaviors:**
- **Embedding enrichment** (Layer 1): Only applies to texts shorter than `routing_short_text_chars` (default: 20). Uses `context_window=1` (most recent turn only). Long, self-contained utterances are classified as-is.
- **LLM fallback context** (Layer 2): Always produced when buffer is non-empty. Includes up to `llm_context_window` (default: 3) prior turns in structured format with `turn[-N] user:` and `turn[-N] route:` labels, enabling the LLM to reason about multi-turn conversation flow.
- The two layers are independently configurable: embeddings use 1 turn, LLM uses up to 3 turns.
- Lexicon and short utterance checks always use the original text — enrichment cannot bypass guardrails.
- The original `user_text` is preserved for prompt construction, buffer storage, and logging.

---

## 9. Observability

**File**: `backend/src/infrastructure/telemetry.py`

### Prometheus Metrics

| Metric | Type | Description |
|---|---|---|
| `voice_turn_latency_ms` | Histogram | Time from finalized to voice start |
| `voice_route_a_confidence` | Histogram | Route A scores |
| `voice_route_b_confidence` | Histogram | Route B scores |
| `voice_tool_execution_ms` | Histogram | Tool execution duration |
| `voice_barge_in_total` | Counter | Barge-in events |
| `voice_fallback_llm_total` | Counter | LLM fallback invocations |
| `voice_active_calls` | Gauge | Currently active calls |
| `voice_filler_emitted_total` | Counter | Filler voice starts |

### OpenTelemetry Tracing

Every `handle_event()` call creates a span (`coordinator.<event_type>`) with attributes:
- `call_id`, `event_type`, `event_id`, `turn_id`, `agent_generation_id`

Setup: `setup_telemetry()` creates a `TracerProvider` with optional OTLP gRPC exporter.

### 9.1 Debug Event Emission

The Coordinator supports an optional debug callback for real-time telemetry, used by the `RealtimeVoiceBridge` to forward debug data to the browser via the "debug" DataChannel.

**Setup**: `Coordinator.set_debug_callback(callback)` registers an async callback. When `None` (default), no debug events are emitted — zero overhead on the hot path.

**Debug events emitted:**

| Event Type | When | Data |
|---|---|---|
| `turn_update` | After `_on_human_turn_finalized` processes routing | `turn_id`, `text`, `route_a`, `route_b`, `policy_key`, `specialist` |
| `routing` | During classification | `route_a_label`, `route_a_confidence`, `route_b_label`, `route_b_confidence`, `short_circuit`, `fallback_used` |
| `fsm_state` | After `AgentFSM.handle_turn` | `agent_generation_id`, `state`, `guided_responses`, `agent_actions` |
| `latency` | In `_on_request_guided_response` | `turn_processing_ms` (time from turn finalization to voice start) |

**Emission pattern**: Best-effort via `_emit_debug()` — exceptions are caught and logged, never crash the voice hot path.

### Router Calibration Logging

Every routing decision emits a structured log (line 395 of coordinator.py):
```
routing_decision:
  router_version, call_id, turn_id, agent_generation_id,
  language, route_a_label, route_a_score, route_b_label,
  route_b_score, margin, short_circuit, fallback_used, final_action
```

### Sentry

Setup: `setup_sentry()` initializes Sentry SDK if `SENTRY_DSN` is configured. Captures unhandled exceptions with `call_id` as a tag.

---

## 10. API Layer

### FastAPI App

**File**: `backend/src/api/app.py`

Factory function `create_app()` with:
- CORS middleware (all origins in dev)
- Request ID middleware (`X-Request-ID` header)
- Unhandled exception handler (500 response)
- Health and admin routers

### Endpoints

**Health & Metrics:**

**`GET /health`** (`backend/src/api/routes/health.py`):
- Checks asyncpg pool (executes `SELECT 1`)
- Checks Redis (executes `PING`)
- Checks models loaded flag
- Returns 200 if all ok, 503 if any degraded

**`GET /metrics`** (`backend/src/api/routes/health.py:54`):
- Returns Prometheus metrics in text exposition format

**Admin:**

**`GET /api/v1/calls`** (`backend/src/api/routes/admin.py`):
- Lists 50 most recent call sessions

**`GET /api/v1/calls/{call_id}`** (`backend/src/api/routes/admin.py:39`):
- Returns call detail with turns and agent generations

**WebRTC Signaling** (`backend/src/api/routes/calls.py`):

**`POST /api/v1/calls`** — Create a new voice call session. Returns `{ call_id, status }`. Enforces `MAX_CONCURRENT_CALLS` (503 if exceeded).

**`POST /api/v1/calls/{call_id}/offer`** — Accept SDP offer, create RTCPeerConnection with audio transceiver and DataChannels, return SDP answer. 409 if offer already processed.

**`POST /api/v1/calls/{call_id}/ice`** — Receive trickle ICE candidate. Logged for debugging; aiortc gathers candidates during SDP exchange. 204 on success.

**`DELETE /api/v1/calls/{call_id}`** — End call, close peer connection, clean up all resources. 204 on success.

---

## 11. Application Startup

**File**: `backend/src/main.py`

The `lifespan()` async context manager wires everything at startup:

```
1. setup_telemetry()        → OpenTelemetry tracer provider
2. setup_sentry()           → Sentry SDK (if DSN configured)
3. create_asyncpg_pool()    → PostgreSQL connection pool
4. create_redis_pool()      → Redis connection pool
5. load_registry()          → Router registry from YAML
6. load_policies()          → Policy templates from YAML
7. EmbeddingEngine.load()   → sentence-transformers model
8. Router.precompute_centroids() → Compute all centroids
9. Create repositories      → PgCallRepo, PgTurnRepo, PgAgentGenRepo, PgVoiceGenRepo
```

On shutdown: close asyncpg pool and Redis connection.

The app runs via `uvicorn` with `uvloop` for maximum async performance.

---

## 12. Frontend Architecture

### 12.1 Overview

The frontend is a Next.js 15 (App Router) browser-based voice client for runtime testing. It connects to the backend via WebRTC, captures microphone audio, runs client-side VAD, and displays real-time transcriptions with an optional debug panel.

```
Browser
├─ Microphone (getUserMedia) → MediaStream
│     ↓
├─ Client-side VAD (Silero WASM via @ricky0123/vad-web)
│     ↓ speech_started / speech_ended
├─ WebRTC (RTCPeerConnection)
│     ├─ Audio Track → Opus codec → Backend (RealtimeVoiceBridge)
│     ├─ DataChannel "control" → VAD signals, transcriptions
│     └─ DataChannel "debug" → FSM state, routing, latency
├─ Transcription Panel (real-time display)
└─ Debug Panel (optional, lazy-loaded)
```

**Design priorities**: Latency-first. Client-side VAD avoids network RTT for speech detection. Opus is native WebRTC codec (zero transformation). Frontend overhead target: < 5ms (VAD ~1-3ms + Opus encode ~2-3ms).

### 12.2 Key Files

| Component | File |
|---|---|
| Page (entry) | `frontend/src/app/page.tsx` |
| Types | `frontend/src/lib/types.ts` |
| API Client | `frontend/src/lib/api.ts` |
| Voice Session Hook | `frontend/src/hooks/use-voice-session.ts` |
| Microphone Hook | `frontend/src/hooks/use-microphone.ts` |
| VAD Hook | `frontend/src/hooks/use-vad.ts` |
| Debug Channel Hook | `frontend/src/hooks/use-debug-channel.ts` |
| Voice Session UI | `frontend/src/components/voice/voice-session.tsx` |
| Mic Animation | `frontend/src/components/voice/mic-animation.tsx` |
| Speaker Animation | `frontend/src/components/voice/speaker-animation.tsx` |
| Transcription Panel | `frontend/src/components/voice/transcription-panel.tsx` |
| Debug Panel | `frontend/src/components/debug/debug-panel.tsx` |
| Dockerfile | `frontend/Dockerfile` |

### 12.3 Hooks

**`useVoiceSession`** — Full WebRTC lifecycle manager.
- Calls `POST /calls` to create session → `POST /calls/{id}/offer` for SDP exchange → ICE handling
- Creates two DataChannels client-side: `"control"` (VAD signals + transcriptions) and `"debug"` (telemetry)
- Monitors `connectionstatechange` (connected/failed/disconnected)
- Returns: `status`, `callId`, `startSession`, `endSession`, `peerConnection`, `sendControl`, `onControlMessage`, `onDebugMessage`, `error`

**`useMicrophone`** — getUserMedia with echo cancellation, noise suppression, auto gain control.
- Returns: `status` (`idle`/`requesting`/`active`/`denied`/`error`), `stream`, `startMicrophone`, `stopMicrophone`, `attachToConnection`
- Handles `NotAllowedError` for mic denial fallback UX

**`useVAD`** — Client-side Voice Activity Detection via Silero WASM.
- Dynamic import of `@ricky0123/vad-web` to avoid SSR issues
- Uses `MicVAD.new({ getStream: () => Promise.resolve(stream) })` to attach to existing mic stream
- Parameters: `positiveSpeechThreshold: 0.8`, `negativeSpeechThreshold: 0.4`, `minSpeechMs: 100`, `preSpeechPadMs: 30`, `redemptionMs: 250`
- Sends `speech_started` / `speech_ended` messages on control DataChannel with timestamps

**`useDebugChannel`** — Parses debug DataChannel events into typed state.
- Maintains: `turns` (DebugTurn[]), `fsmState`, `routing` (DebugRouting), `events` (DebugEvent[]), `latencies` (DebugLatency[])
- Limits events array to 100 entries

### 12.4 Components

**`VoiceSession`** — Main orchestrator component. Wires all hooks together.
- Lazy-loads `DebugPanel` via `next/dynamic` (no debug overhead when disabled)
- Debug toggle sends `debug_enable` / `debug_disable` on control channel
- Shows: connection status badge, mic denied fallback, start/end call buttons, mic/speaker animations, transcription panel

**`MicAnimation`** — Green pulsing circle with mic icon when user is speaking.

**`SpeakerAnimation`** — Blue pulsing circle with speaker icon when agent is speaking.

**`TranscriptionPanel`** — Chat-style display. Human messages right-aligned (primary color), agent messages left-aligned (muted). Auto-scrolls to bottom on new entries.

**`DebugPanel`** — 3-column grid: FSM State badge, Last Routing details (Route A/B confidence, short circuit, LLM fallback), Latency measurements (color-coded: green < 200ms, red > 200ms). Plus Turn History list and Event Log (last 20, monospace JSON).

### 12.5 Data Flow

```
1. User clicks "Start Call"
   → useVoiceSession.startSession()
   → POST /calls → POST /calls/{id}/offer (SDP exchange)
   → RTCPeerConnection established

2. User clicks "Allow" on mic permission
   → useMicrophone.startMicrophone()
   → getUserMedia → MediaStream
   → attachToConnection(pc) adds audio track to WebRTC

3. Audio flows continuously via WebRTC (Opus, UDP)
   → Backend receives via aiortc
   → RealtimeVoiceBridge forwards to RealtimeVoiceProvider (STT)

4. User speaks
   → useVAD detects speech_started → sends on control channel
   → Backend Coordinator receives speech_started event
   → User stops → VAD detects speech_ended → sends on control channel
   → Backend processes turn (classify, route, generate response)

5. Transcriptions arrive on control channel
   → onControlMessage callback → TranscriptionPanel updates

6. Agent response audio streams back via WebRTC
   → Browser plays through speaker (remote audio track)

7. Debug events arrive on debug channel (when enabled)
   → useDebugChannel parses → DebugPanel updates
```

### 12.6 Deployment

3-stage Docker build (`frontend/Dockerfile`): deps (pnpm install) → builder (next build) → runner (standalone server.js). Uses `output: "standalone"` in `next.config.ts`.

Root `docker-compose.yml` runs 4 services:
- `frontend` (Next.js, port 3000) → depends on `voice-runtime`
- `voice-runtime` (FastAPI + asyncio, port 8000)
- `postgres` (PostgreSQL 16)
- `redis` (Redis 7)

Frontend env: `NEXT_PUBLIC_API_URL=http://voice-runtime:8000`
