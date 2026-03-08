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
- [5. Model-as-Router Architecture](#5-model-as-router-architecture)
  - [5.1 RouterPromptBuilder](#51-routerpromptbuilder)
  - [5.2 RouterPromptTemplate](#52-routerprompttemplate)
  - [5.3 parse_model_action](#53-parse_model_action)
  - [5.4 Embedding Pipeline (Analytics Only)](#54-embedding-pipeline-analytics-only)
  - [5.5 Router Registry](#55-router-registry)
  - [5.6 Language Detection](#56-language-detection)
  - [5.7 Policies](#57-policies)
- [6. Infrastructure](#6-infrastructure)
  - [6.1 Redis (Idempotency and Caching)](#61-redis-idempotency-and-caching)
  - [6.2 Session Registry](#62-session-registry)
  - [6.3 Persistence (Repositories)](#63-persistence-repositories)
  - [6.4 Realtime Client](#64-realtime-client)
  - [6.5 Realtime Event Bridge](#65-realtime-event-bridge)
  - [6.6 OpenAI WebRTC SDP Proxy & Session Lifecycle](#66-openai-webrtc-sdp-proxy--session-lifecycle)
- [7. Runtime State](#7-runtime-state)
- [8. End-to-End Flows](#8-end-to-end-flows)
  - [8.1 Happy Path: Simple Greeting](#81-happy-path-simple-greeting)
  - [8.2 Domain Route: Specialist Agent](#82-domain-route-specialist-agent)
  - [8.3 Barge-In During Voice Output](#83-barge-in-during-voice-output)
  - [8.4 Guardrail: Disallowed Content](#84-guardrail-disallowed-content)
  - [8.5 Ambiguous Intent: Clarify Department](#85-ambiguous-intent-clarify-department)
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
Browser (WebRTC)
    ↕ Opus audio (direct to OpenAI via WebRTC)
    ↕ Data channel "oai-events" (OpenAI events for UI: transcription, VAD, audio)
    ↕ HTTP (SDP signaling via backend proxy)
Backend
    → SDP Proxy: POST /v1/realtime/calls (OpenAI Realtime WebRTC API)
    → RealtimeEventBridge: WSS /v1/realtime (server-side WebSocket to OpenAI)
        ↕ OpenAI events ↔ Coordinator EventEnvelopes
Coordinator (CallSession)
    ↔ TurnManager         (turn detection via audio_committed)
    ↔ Agent FSM            (state tracking: IDLE→ROUTING→SPEAKING→...)
    ↔ ToolExecutor         (tool execution)
    ↔ RouterPromptBuilder  (builds response.create payloads for model-as-router)
    ↔ RealtimeEventBridge   (OpenAI Realtime API commands + JSON action detection)
```

The browser receives OpenAI events via WebRTC data channel for UI display (transcriptions, speaking indicators). The backend receives the same events via a server-side WebSocket, translates them to EventEnvelopes, and feeds them to the Coordinator for model-as-router dispatch and response control.

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
| Model Router | `backend/src/routing/model_router.py` |
| Router Prompt | `backend/router_registry/v1/router_prompt.yaml` |
| Router (analytics) | `backend/src/routing/router.py` |
| Policies | `backend/src/routing/policies.py` |
| RealtimeEventBridge | `backend/src/voice_runtime/realtime_event_bridge.py` |
| RealtimeClient Protocol | `backend/src/voice_runtime/realtime_client.py` |
| WebRTC Signaling (SDP Proxy) | `backend/src/api/routes/calls.py` |
| Config | `backend/src/config.py` |

---

## 2. Core Types and Enums

Defined in `backend/src/voice_runtime/types.py`.

### Identity Types

```
CallId, TurnId, AgentGenerationId, VoiceGenerationId, ToolRequestId, EventId
```

All are `NewType` wrappers around `UUID`.

### Route A Labels (`RouteALabel`) — Analytics Only

> **Note**: Route A/B labels are no longer used in the hot path. The model-as-router pattern (Section 5) handles intent classification and response in a single inference. These labels are preserved for offline analytics and calibration logging.

The first-level classification of user intent:

| Value | Meaning | Action |
|---|---|---|
| `simple` | Greeting or simple conversational turn | Guided response with `greeting` policy |
| `disallowed` | Blocked content (insults, abuse) | Guided response with `guardrail_disallowed` policy |
| `out_of_scope` | Off-topic question | Guided response with `guardrail_out_of_scope` policy |
| `domain` | Business-related intent | Proceeds to Route B classification |

### Route B Labels (`RouteBLabel`) — Analytics Only

The second-level classification for `domain` intents (used for offline analytics only):

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

- **`AgentState`**: `idle → routing → speaking → waiting_tools → done` (also `cancelled`, `error`)
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
| `TranscriptFinal` | `call_id, text, ts` | Final ASR transcript (async logging only — no longer triggers routing) |
| `AudioCommitted` | `call_id, ts` | Audio buffer committed by server VAD — primary turn trigger for model-as-router |
| `ModelRouterAction` | `call_id, action, department, summary, ts` | Model returned a JSON specialist action instead of direct voice |
| `VoiceGenerationCompleted` | `call_id, voice_generation_id, ts` | Voice playback finished |
| `VoiceGenerationError` | `call_id, voice_generation_id, error, ts` | Voice playback failed |

**TurnManager → Coordinator:**

| Event | Fields | Purpose |
|---|---|---|
| `HumanTurnStarted` | `call_id, turn_id, ts` | New turn opened |
| `HumanTurnFinalized` | `call_id, turn_id, ts` | Turn finalized by audio_committed (text not available yet — transcript arrives async) |
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
| `agent_fsm` | `AgentFSM` | Delegates state tracking |
| `tool_executor` | `ToolExecutor` | Delegates tool execution |
| `router_prompt_builder` | `RouterPromptBuilder` | Builds `response.create` payloads for model-as-router |
| `policies` | `PoliciesRegistry` | Policy templates for prompts |
| `seen_events` | `TTLSet` (optional) | Redis-backed idempotency set |
| `tool_cache` | `TTLMap` (optional) | Redis-backed tool result cache |
| `turn_repo` | `TurnRepository` (optional) | DB persistence for turns |
| `agent_gen_repo` | `AgentGenerationRepository` (optional) | DB persistence for agent generations |
| `voice_gen_repo` | `VoiceGenerationRepository` (optional) | DB persistence for voice generations |
| `max_history_turns` | `int` (default: 10) | Max turns in conversation buffer |
| `max_history_chars` | `int` (default: 2000) | Max total user_text chars in buffer |

**Main entry point**: `handle_event(envelope)` at line 142. This method:

1. Checks idempotency (Redis TTLSet or in-memory fallback)
2. Opens an OpenTelemetry span with `call_id`, `event_type`, `turn_id`, `agent_generation_id`
3. Dispatches via `match envelope.type` to handler methods

**Event handlers:**

| Event Type | Method | What It Does |
|---|---|---|
| `speech_started` | `_on_speech_started` | Barge-in: cancel active voice + generation + filler. Forward to TurnManager |
| `audio_committed` | `_on_audio_committed` | **Primary turn trigger**: finalizes turn via TurnManager, builds router prompt via `RouterPromptBuilder`, emits `response.create` to the Realtime model. The model classifies intent AND responds in a single inference |
| `model_router_action` | `_on_model_router_action` | Handles specialist JSON actions returned by the model (e.g., `{"action":"specialist","department":"billing","summary":"..."}`) — dispatches to specialist agent |
| `transcript_final` | `_on_transcript_final` | **Async logging only**: persists transcript text to DB, appends to conversation buffer, emits debug display. No longer triggers routing or turn finalization |
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

**Model-as-Router Pattern**: Instead of running an embedding classification pipeline, the Coordinator uses `RouterPromptBuilder` to construct a `response.create` payload containing a structured router prompt (from `RouterPromptTemplate`) plus conversation history formatted via `format_history()` (from `backend/src/routing/context.py`). The Realtime model classifies intent AND responds in a single inference. For simple intents (~60-70% of turns), the model speaks directly. For specialist routing, the model returns a JSON action `{"action":"specialist","department":"billing","summary":"..."}` which the bridge detects and emits as a `model_router_action` event.

**Routing context** (`backend/src/routing/context.py`): The `format_history()` function replaces the former `RoutingContextBuilder` class. It formats conversation buffer entries into a simple history string included in the router prompt, enabling the model to reason about conversational continuity.

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
| `handle_audio_committed(ts)` | Timestamp | `HumanTurnFinalized` | If turn is OPEN, finalize it. This is the **primary turn trigger** — fired by `input_audio_buffer.committed` from server VAD, eliminating 200-500ms Whisper transcription latency from the hot path |
| `handle_transcript_final(text, ts)` | Text + timestamp | *(no turn event)* | No longer emits `HumanTurnFinalized`. Transcript text is used for async logging only |
| `handle_no_transcript_timeout(ts)` | Timestamp | `HumanTurnCancelled` | Cancel open turn if no transcript arrived |
| `drain_events()` | — | List of turn events | Return and clear the pending events buffer |

**Turn lifecycle:**
```
speech_started → OPEN
  ├─ audio_committed → FINALIZED (primary trigger)
  ├─ transcript_final → (async logging only, no state change)
  ├─ speech_started (new) → CANCELLED (barge-in) + new OPEN
  └─ timeout → CANCELLED (no_transcript)
```

### 4.3 Agent FSM

**File**: `backend/src/voice_runtime/agent_fsm.py`

Finite state machine for agent generation lifecycle. Tracks the state of each generation through the model-as-router flow. Does NOT execute tools or call the Realtime API directly.

**State transitions:**

```
IDLE ──start_routing()──→ ROUTING
ROUTING ──voice_started()──→ SPEAKING ──voice_completed()──→ DONE
ROUTING ──specialist_action()──→ WAITING_TOOLS ──tool_result()──→ SPEAKING ──voice_completed()──→ DONE
Any active state ──cancel()──→ CANCELLED
Any active state ──error()──→ ERROR
DONE, CANCELLED, ERROR are terminal states
```

**Key methods:**

| Method | Transition | When Called |
|---|---|---|
| `start_routing()` | IDLE → ROUTING | Coordinator sends `response.create` to model |
| `voice_started()` | ROUTING → SPEAKING | Model begins direct voice response |
| `specialist_action()` | ROUTING → WAITING_TOOLS | Model returns JSON specialist action |
| `tool_result()` | WAITING_TOOLS → SPEAKING | Specialist tool completes, voice response starts |
| `voice_completed()` | SPEAKING → DONE | Voice playback finishes |
| `cancel()` | Any active → CANCELLED | Barge-in or timeout |
| `error()` | Any active → ERROR | Unrecoverable error |
| `reset()` | → IDLE | Prepare for next generation cycle |

**Two response modes:**
1. **Direct voice (~60-70%)**: Model speaks directly for simple intents. Flow: IDLE → ROUTING → SPEAKING → DONE
2. **JSON action**: Model returns `{"action":"specialist","department":"billing","summary":"..."}`. Flow: IDLE → ROUTING → WAITING_TOOLS → SPEAKING → DONE

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

## 5. Model-as-Router Architecture

### Why the change

The original architecture used a **multi-step embedding classification pipeline** on the hot path: language detection → lexicon check → sentence-transformer embedding → cosine similarity against centroids → optional LLM fallback. This pipeline added **200-500ms of latency** to every turn before the model could even begin responding. Moreover, it required maintaining training examples, confidence thresholds, and centroid calibration — a significant operational burden.

### What we gain

| Dimension | Before (Embedding Pipeline) | After (Model-as-Router) |
|---|---|---|
| **Latency** | 200-500ms classification + model response time | Single inference — classification and response are simultaneous |
| **Turn trigger** | `transcript_final` (waits for Whisper transcription) | `audio_committed` (server VAD, 300ms silence) — saves 200-500ms Whisper latency |
| **Accuracy** | Cosine similarity against static centroids | LLM reasoning over full conversation context |
| **Context** | Limited enrichment window for short texts | Full conversation history in every prompt |
| **Maintenance** | Training examples, thresholds, centroid calibration | Single YAML prompt template |
| **Ambiguity handling** | Confidence thresholds + `clarify_department` policy | Model asks clarification naturally in conversation |
| **Code complexity** | 6 classification steps, 3 fallback layers | 1 prompt builder, 1 JSON action parser |

The embedding pipeline is preserved for offline analytics (A/B comparison, confidence distribution analysis) and as a potential degraded-mode fallback.

### How it works

The Realtime voice model serves as the primary router. Instead of a multi-step embedding classification pipeline, the model classifies intent AND responds in a **single inference** via `response.create` with a structured router prompt. This eliminates the embedding classification latency from the hot path.

### 5.1 RouterPromptBuilder

**File**: `backend/src/routing/model_router.py`

`RouterPromptBuilder` constructs `response.create` payloads for the Realtime API. It combines:
1. A `RouterPromptTemplate` (loaded from YAML) containing the system instructions for routing behavior
2. Conversation history embedded as text within the `instructions` field (appended after the system prompt as a `Conversation history:` section)

**Important**: History is embedded in `instructions` (not `response.input`) to preserve OpenAI's native conversation context, which includes the current turn's committed audio buffer. Using `response.input` would override the native context and cause the model to ignore the user's current speech.

The resulting payload is sent as a `response.create` message to OpenAI. The model reads the router prompt, classifies the user's intent, and either:
- **Speaks directly** (~60-70% of turns): For simple intents (greetings, guardrails, general questions), the model generates a voice response inline
- **Returns a JSON action**: For specialist routing, the model outputs `{"action":"specialist","department":"billing","summary":"..."}` instead of speaking

### 5.2 RouterPromptTemplate

**File**: `backend/router_registry/v1/router_prompt.yaml`

YAML-defined prompt template that instructs the Realtime model on:
- Available departments and their descriptions
- When to speak directly vs. return a JSON action
- Guardrail rules (disallowed content, out-of-scope handling)
- Response style and dynamic language guidelines (respond in the customer's language)

Loaded at startup and injected into `RouterPromptBuilder`.

### 5.3 parse_model_action

**File**: `backend/src/voice_runtime/realtime_event_bridge.py` (within the bridge)

The bridge accumulates `response.audio_transcript.delta` fragments. On `response.done`, `parse_model_action()` attempts to parse the accumulated text as JSON. If it matches the specialist action schema (`{"action":"specialist","department":"...","summary":"..."}`), the bridge emits a `model_router_action` event to the Coordinator instead of a `voice_generation_completed` event.

### 5.4 Embedding Pipeline (Analytics Only)

The embedding-based classification pipeline (Router, EmbeddingEngine, lexicon checks, LLM fallback) is **preserved** but removed from the hot path. It is still loaded at startup in `main.py` and used for:
- **Offline analytics**: Calibration logging, confidence distribution analysis
- **A/B comparison**: Comparing model-as-router decisions against embedding classifications
- **Fallback potential**: Available as a degraded-mode fallback if the Realtime API is unavailable

The following components remain unchanged but are no longer invoked by the Coordinator during live calls:
- `Router.classify()` — embedding classification pipeline (`backend/src/routing/router.py`)
- `EmbeddingEngine` — sentence-transformers model (`backend/src/routing/embeddings.py`)
- Lexicon and short utterance checks (`backend/src/routing/lexicon.py`)
- LLM fallback (`backend/src/routing/llm_fallback.py`)

### 5.5 Router Registry

**File**: `backend/src/routing/registry.py`

Versioned YAML configuration loaded from `backend/router_registry/v1/`:

```
router_registry/v1/
  ├── router_prompt.yaml     # Model-as-router prompt template (NEW)
  ├── thresholds.yaml        # Confidence thresholds (analytics/calibration)
  ├── policies.yaml          # Base system prompt + policy templates
  ├── route_a/
  │   ├── base.yaml          # Route A training examples (analytics)
  │   └── es.yaml            # Spanish-specific examples
  ├── route_b/
  │   ├── base.yaml          # Route B training examples (analytics)
  │   └── es.yaml
  ├── lexicon_disallowed/
  │   └── es.txt             # One disallowed word/phrase per line
  └── short_utterances/
      └── es.yaml            # Category → list of short phrases
```

**`ThresholdsConfig`** (line 11): Parsed from `thresholds.yaml` (used for analytics/calibration only):
- `version`: Registry version string
- `route_a[label]["high"|"medium"]`: Per-label confidence thresholds
- `route_b[label]["high"|"medium"]`: Per-label confidence thresholds
- `ambiguous_margin`: Minimum margin between top-1 and top-2 scores
- `short_text_len_chars`: Max chars for short utterance matching
- `fallback_enable`, `fallback_min_score`, `fallback_max_latency_budget_ms`
- `filler_enable`, `filler_start_after_ms`, `filler_max_ms`

**Language inheritance**: Each data source (examples, lexicon, short utterances) has a `base` locale and optional per-language overrides.

### 5.6 Language Detection

**File**: `backend/src/routing/language.py`

Uses the `langid` library for language identification (~0.02-0.04ms per call, 97 languages supported, pure Python with no NumPy dependency).

- **`detect_language(text)`**: Returns ISO 639-1 language code (e.g., `"es"`, `"en"`)
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

**`OpenAIRealtimeEventBridge`**: Production implementation (see Section 6.5).

### 6.5 Realtime Event Bridge

**File**: `backend/src/voice_runtime/realtime_event_bridge.py`

`OpenAIRealtimeEventBridge` implements the `RealtimeClient` protocol and connects the Coordinator to the OpenAI Realtime API via **browser-forwarded events**. The browser receives OpenAI events on the WebRTC data channel (`oai-events`) and forwards them to the backend via a WebSocket (`WS /calls/{call_id}/events`). The bridge translates these to Coordinator EventEnvelopes (input direction) and translates Coordinator commands back to OpenAI API messages sent to the browser for forwarding to the data channel (output direction).

**Architecture:**
```
Browser ←WebRTC→ OpenAI (audio + data channel "oai-events")
Browser ←WebSocket→ Backend (event forwarding, both directions)
```

**Frontend WebSocket management:**
- `set_frontend_ws(ws)`: Register or clear the frontend WebSocket connection
- `handle_frontend_event(data)`: Process a raw OpenAI event forwarded from the frontend
- `send_to_frontend(data)`: Send a JSON message to the frontend via WebSocket (public method, used by both the bridge internally and external callers like `calls.py` for session.update)
- `close()`: Clean up bridge state

**JSON action detection**: The bridge accumulates `response.audio_transcript.delta` fragments during each response. On `response.done`, it calls `parse_model_action()` to check if the accumulated text is a JSON specialist action. If it matches (`{"action":"specialist","department":"...","summary":"..."}`), a `model_router_action` event is emitted instead of `voice_generation_completed`.

**Server VAD configuration**: The bridge configures server-side VAD with `silence_duration_ms=300` (from `Settings.vad_silence_duration_ms`), which controls how long the server waits after speech stops before committing the audio buffer. The 300ms value balances responsiveness with avoiding premature commits on natural pauses.

**Input event translation (OpenAI → Coordinator):**

| OpenAI Event | Coordinator EventEnvelope |
|---|---|
| `input_audio_buffer.speech_started` | `type="speech_started"` |
| `input_audio_buffer.speech_stopped` | `type="speech_stopped"` |
| `input_audio_buffer.committed` | `type="audio_committed"` — **primary turn trigger** |
| `conversation.item.input_audio_transcription.completed` | `type="transcript_final"` (async logging only, empty transcripts ignored) |
| `response.done` | `type="voice_generation_completed"` OR `type="model_router_action"` (if JSON action detected) |
| `response.failed` | `type="voice_generation_error"` |

**Output event translation (Coordinator → OpenAI):**
- `send_voice_start(RealtimeVoiceStart)` with dict payload (from RouterPromptBuilder) → sent directly as `response.create` with conversation history embedded in `instructions`. No `response.input` — preserves OpenAI's native conversation context (current turn audio). No per-turn `session.update` — instructions are passed inline to avoid the ~500ms round-trip.
- `send_voice_start(RealtimeVoiceStart)` with string prompt → `response.create` (filler/simple response)
- `send_voice_cancel(RealtimeVoiceCancel)` → `response.cancel`

### 6.6 OpenAI WebRTC SDP Proxy & Session Lifecycle

**File**: `backend/src/api/routes/calls.py`

The backend acts as a **SDP signaling proxy**, **session lifecycle manager**, and **event forwarding hub**. It does NOT process audio or manage WebRTC peer connections. The browser connects directly to OpenAI via WebRTC for audio. Events flow through the backend via WebSocket for Coordinator integration.

**Session lifecycle:**
1. `POST /calls` creates a full runtime actor stack: Coordinator, TurnManager, AgentFSM, ToolExecutor, RouterPromptBuilder, and RealtimeEventBridge. The bridge is wired to the Coordinator bidirectionally:
   - Input: `bridge.on_event(coordinator.handle_event)` — OpenAI events reach the Coordinator
   - Output: `coordinator.set_output_callback(fn)` — Coordinator commands (RealtimeVoiceStart, RealtimeVoiceCancel) are dispatched to `bridge.send_voice_start()` / `bridge.send_voice_cancel()`
2. `POST /calls/{call_id}/offer` performs a **two-step SDP exchange** with OpenAI:
   - Step 1: `POST /v1/realtime/sessions` with session config (model, modalities, `input_audio_transcription` with Whisper auto-language-detection, `turn_detection` with `create_response: false`) → returns an ephemeral key
   - Step 2: `POST /v1/realtime` with the ephemeral key and SDP offer → returns the SDP answer
   - The server API key is only used for the sessions call — the ephemeral key is used for the SDP exchange, so the API key is never exposed to the browser
3. `WS /calls/{call_id}/events` establishes bidirectional event forwarding:
   - On connection: sends a one-time `session.update` via the bridge to configure transcription (`whisper-1`), disable auto-response (`create_response: false`), and set server VAD `silence_duration_ms` (default: 300ms). The `/v1/realtime/sessions` endpoint does NOT reliably apply these settings, so the explicit `session.update` is required.
   - Receive loop: forwards browser-sent OpenAI data channel events to `bridge.handle_frontend_event()`
   - On disconnect: clears the frontend WebSocket reference via `bridge.set_frontend_ws(None)`
4. `DELETE /calls/{call_id}` closes the bridge and removes the session.

**In-memory session registry**: `_sessions: dict[UUID, CallSessionEntry]` tracks active calls. Each `CallSessionEntry` holds: `coordinator`, `turn_manager`, `agent_fsm`, `tool_executor`, `bridge`, `router_prompt_builder`.

**Shared singletons**: `RouterPromptBuilder`, `Router` (analytics), and `PoliciesRegistry` are set at app startup via `set_shared_dependencies()` (called in `main.py` lifespan). If not initialized, a stub `PoliciesRegistry` with default policies is used (logs `policies_not_initialized_using_stubs` warning).

**Endpoints:**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/calls` | POST | Create call session with full actor stack, returns `call_id`. Enforces `max_concurrent_calls`. |
| `/api/v1/calls/{call_id}/offer` | POST | Two-step SDP exchange: create session with config → get ephemeral key → SDP exchange |
| `/api/v1/calls/{call_id}/events` | WS | Bidirectional event forwarding between browser data channel and Coordinator |
| `/api/v1/calls/{call_id}` | DELETE | End call, close bridge, tear down actors |

**Configuration:**
- `OPENAI_API_KEY`: Required for session creation (Step 1 of SDP exchange)
- `OPENAI_REALTIME_MODEL`: Model to use (default: `gpt-4o-realtime-preview`)
- `MAX_CONCURRENT_CALLS`: Session limit (default: 50)
- `VAD_SILENCE_DURATION_MS`: Server VAD silence threshold (default: 300)

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
3. Realtime Provider → input_audio_buffer.committed (server VAD, 300ms silence)
4. Coordinator._on_audio_committed()
   a. TurnManager.handle_audio_committed() → HumanTurnFinalized
   b. AgentFSM.start_routing() → IDLE → ROUTING
   c. RouterPromptBuilder.build(conversation_history) → response.create payload
   d. Emit response.create to Realtime API (model classifies + responds in single inference)
5. Model speaks directly (simple greeting, ~60-70% of turns)
   → AgentFSM.voice_started() → ROUTING → SPEAKING
6. Realtime Provider → transcript_final("hola buenos días") (arrives async)
7. Coordinator._on_transcript_final()
   → Persist text to DB (fire-and-forget)
   → Append to conversation buffer
   → Emit debug display
8. Realtime Provider → voice_generation_completed
9. Coordinator._on_voice_completed()
   → AgentFSM.voice_completed() → SPEAKING → DONE
   → Clear active_voice_generation_id
   → Persist completion
```

### 8.2 Domain Route: Specialist Agent

User says: "tengo un problema con mi factura"

```
1-4. Same as above until audio_committed triggers response.create
5. Model classifies as specialist routing → returns JSON action:
   {"action": "specialist", "department": "billing", "summary": "User has a billing issue with their invoice"}
6. Bridge detects JSON action via parse_model_action()
   → Emits model_router_action event instead of voice_generation_completed
7. Coordinator._on_model_router_action()
   → AgentFSM.specialist_action() → ROUTING → WAITING_TOOLS
   → Dispatch to specialist agent (billing)
   → Specialist responds → voice plays
   → AgentFSM.voice_completed() → SPEAKING → DONE
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
4. audio_committed → new turn proceeds via model-as-router
```

Any late results from the cancelled generation are silently ignored via `is_generation_cancelled()` checks.

### 8.4 Guardrail: Disallowed Content

User says: "maldita sea" (insult)

```
1-3. Same until audio_committed triggers response.create
4. Coordinator._on_audio_committed()
   → RouterPromptBuilder builds payload with router prompt that includes guardrail instructions
   → Emit response.create to Realtime API
5. Model recognizes disallowed content via router prompt instructions
   → Speaks guardrail response directly (no JSON action)
6. transcript_final arrives async → persisted for logging
```

The router prompt template includes explicit guardrail rules. The model handles disallowed content detection inline — no separate lexicon check is needed on the hot path. The embedding pipeline's lexicon checks remain available for offline analytics.

### 8.5 Ambiguous Intent: Clarify Department

User says: "tengo un problema" (unclear which department)

```
1-3. Same until audio_committed triggers response.create
4. Model receives router prompt with department descriptions + user audio
   → Intent is ambiguous — model speaks directly asking for clarification
   (e.g., "I can help you with that. Could you tell me if this is about billing, technical support, or something else?")
5. No JSON action emitted — model handles clarification conversationally
6. User responds with clarification → next audio_committed triggers new response.create with conversation history
```

The model-as-router handles ambiguity naturally through conversation, using the router prompt's department descriptions to guide clarification questions.

### 8.6 Multi-Turn Conversation with History

User has a multi-turn conversation: "hola" → "mi factura" → "¿cuánto debo?"

```
=== Turn 1: "hola" ===
1. speech_started → audio_committed
2. Coordinator._on_audio_committed():
   a. RouterPromptBuilder.build(history=[]) → response.create with router prompt
   b. Model speaks greeting directly (simple intent)
3. transcript_final("hola") → async: persist + append to buffer
4. voice_generation_completed → DONE

=== Turn 2: "mi factura" ===
5. speech_started (barge-in: cancels turn 1 voice) → audio_committed
6. Coordinator._on_audio_committed():
   a. RouterPromptBuilder.build(history=[turn 1]) → response.create with conversation context
   b. Model returns JSON: {"action":"specialist","department":"billing","summary":"..."}
7. Bridge detects JSON → model_router_action event
8. Coordinator._on_model_router_action() → dispatch to billing specialist
9. transcript_final("mi factura") → async: persist + append to buffer

=== Turn 3: "¿cuánto debo?" ===
10. speech_started → audio_committed
11. Coordinator._on_audio_committed():
    a. RouterPromptBuilder.build(history=[turn 1, turn 2]) → response.create
    b. Model sees full conversation context in router prompt
    c. Model recognizes this is a billing follow-up → returns specialist action or speaks directly
12. transcript_final("¿cuánto debo?") → async: persist + append to buffer
```

**Key behaviors:**
- The model-as-router sees **full conversation history** in the router prompt, enabling natural multi-turn reasoning without separate embedding enrichment.
- `audio_committed` triggers routing immediately — transcript arrives async and is used only for logging and buffer updates.
- `TurnEntry` is appended **after** transcript arrives — cancelled turns never enter the buffer.
- Buffer pruning (max 10 turns, max 2000 chars of `user_text`) ensures bounded prompt growth.

### 8.7 Context-Aware Routing: Short Follow-Up

User says "tengo un problema con mi factura" (turn 1), "no me llega el recibo" (turn 2), then "de este mes" (turn 3, short follow-up).

```
=== Turn 1: "tengo un problema con mi factura" ===
1. speech_started → audio_committed
2. RouterPromptBuilder.build(history=[]) → response.create with router prompt
3. Model → JSON action: {"action":"specialist","department":"billing","summary":"..."}
4. transcript_final arrives async → buffer.append(TurnEntry(seq=1, ...))

=== Turn 2: "no me llega el recibo" ===
5. speech_started → audio_committed
6. RouterPromptBuilder.build(history=[turn 1]) → response.create
   → Router prompt includes: conversation history with turn 1 context
7. Model sees billing context from turn 1 → continues billing specialist routing
8. transcript_final arrives async → buffer.append(TurnEntry(seq=2, ...))

=== Turn 3: "de este mes" (short follow-up) ===
9.  speech_started → audio_committed
10. RouterPromptBuilder.build(history=[turn 1, turn 2]) → response.create
    → Router prompt includes full conversation history (2 prior billing turns)
11. Model sees conversation continuity → correctly routes as billing follow-up
    despite the short, ambiguous utterance
12. transcript_final arrives async → buffer.append(TurnEntry(seq=3, ...))
```

**Key behaviors:**
- The model-as-router handles short follow-ups naturally because it sees the **full conversation history** in every `response.create` payload. No separate embedding enrichment or LLM fallback layers are needed.
- `format_history()` in `context.py` formats the conversation buffer into the router prompt, providing the model with prior turn context.
- The original `user_text` is preserved in the conversation buffer for history formatting and logging.
- The embedding pipeline's context enrichment layers (embedding enrichment for short texts, LLM fallback context) remain available for offline analytics comparison.

---

## 9. Observability

**File**: `backend/src/infrastructure/telemetry.py`

### Prometheus Metrics

| Metric | Type | Description |
|---|---|---|
| `voice_turn_latency_ms` | Histogram | Time from finalized to voice start |
| `voice_route_a_confidence` | Histogram | Route A scores (analytics pipeline only — not recorded on hot path) |
| `voice_route_b_confidence` | Histogram | Route B scores (analytics pipeline only — not recorded on hot path) |
| `voice_tool_execution_ms` | Histogram | Tool execution duration |
| `voice_barge_in_total` | Counter | Barge-in events |
| `voice_fallback_llm_total` | Counter | LLM fallback invocations (analytics pipeline only — not incremented on hot path) |
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
| `turn_update` | After `_on_audio_committed` triggers model-as-router | `turn_id`, `text` (empty — transcript not yet available), `state` ("finalized") |
| `fsm_state` | After `AgentFSM.start_routing()` | `agent_generation_id`, `state` |
| `transcript_final` | After `_on_transcript_final` (async) | `turn_id`, `text` |

> **Note**: The `routing` and `latency` debug events from the embedding classification pipeline are no longer emitted on the hot path. The model-as-router pattern eliminates the separate classification step, so there are no Route A/B confidence scores or routing latency measurements to report in real time.

**Emission pattern**: Best-effort via `_emit_debug()` — exceptions are caught and logged, never crash the voice hot path.

### Model-as-Router Logging

The Coordinator emits two structured logs per turn on the hot path:

**`model_router_dispatched`** — when `response.create` is sent to the Realtime model:
```
model_router_dispatched:
  call_id, turn_id, agent_generation_id, has_history
```

**`model_router_action_received`** — when the model returns a JSON specialist action:
```
model_router_action_received:
  call_id, department, summary, agent_generation_id
```

For direct voice responses (no JSON action), no additional log is emitted — the model speaks directly and the existing `voice_generation_completed` log covers it.

> **Note**: The legacy `routing_decision` structured log (with `route_a_label`, `route_a_score`, `route_b_label`, `route_b_score`, `margin`, `short_circuit`, `fallback_used`) is no longer emitted on the hot path. It remains available in the offline analytics pipeline.

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

**WebRTC Signaling — SDP Proxy** (`backend/src/api/routes/calls.py`):

**`POST /api/v1/calls`** — Create a new voice call session. Returns `{ call_id, status }`. Enforces `MAX_CONCURRENT_CALLS` (503 if exceeded).

**`POST /api/v1/calls/{call_id}/offer`** — Proxy SDP offer to OpenAI Realtime WebRTC API, return SDP answer. 502 on OpenAI error.

**`DELETE /api/v1/calls/{call_id}`** — End call, remove from session registry. 204 on success.

---

## 11. Application Startup

**File**: `backend/src/main.py`

The `lifespan()` async context manager wires everything at startup:

```
1. setup_telemetry()            → OpenTelemetry tracer provider
2. setup_sentry()               → Sentry SDK (if DSN configured)
3. create_asyncpg_pool()        → PostgreSQL connection pool
4. create_redis_pool()          → Redis connection pool
5. load_registry()              → Router registry from YAML
6. load_policies()              → Policy templates from YAML
7. load_router_prompt_template()→ RouterPromptTemplate from router_prompt.yaml (NEW)
8. Create RouterPromptBuilder   → Injected into Coordinator per call (NEW)
9. EmbeddingEngine.load()       → sentence-transformers model (analytics only)
10. Router.precompute_centroids() → Compute all centroids (analytics only)
11. Create repositories          → PgCallRepo, PgTurnRepo, PgAgentGenRepo, PgVoiceGenRepo
```

On shutdown: close asyncpg pool and Redis connection.

The app runs via `uvicorn` with `uvloop` for maximum async performance.

---

## 12. Frontend Architecture

### 12.1 Overview

The frontend is a Next.js 15 (App Router) browser-based voice client for runtime testing. It connects directly to OpenAI via WebRTC for audio and events, using the backend only for SDP signaling (keeping the API key server-side).

```
Browser
├─ Microphone (getUserMedia) → MediaStream
├─ WebRTC (RTCPeerConnection → direct to OpenAI)
│     ├─ Audio Track → Opus codec → OpenAI (STT + TTS)
│     └─ DataChannel "oai-events" → OpenAI events (transcriptions, VAD, audio)
├─ HTTP → Backend (SDP proxy only)
├─ Transcription Panel (real-time display)
└─ Debug Panel (optional, lazy-loaded)
```

**Design priorities**: Latency-first. Direct browser-to-OpenAI WebRTC eliminates backend audio relay. OpenAI handles VAD server-side. Opus is native WebRTC codec (zero transformation).

### 12.2 Key Files

| Component | File |
|---|---|
| Page (entry) | `frontend/src/app/page.tsx` |
| Types | `frontend/src/lib/types.ts` |
| API Client | `frontend/src/lib/api.ts` |
| Voice Session Hook | `frontend/src/hooks/use-voice-session.ts` |
| Debug Channel Hook | `frontend/src/hooks/use-debug-channel.ts` |
| Voice Session UI | `frontend/src/components/voice/voice-session.tsx` |
| Mic Animation | `frontend/src/components/voice/mic-animation.tsx` |
| Speaker Animation | `frontend/src/components/voice/speaker-animation.tsx` |
| Transcription Panel | `frontend/src/components/voice/transcription-panel.tsx` |
| Debug Panel | `frontend/src/components/debug/debug-panel.tsx` |
| Dockerfile | `frontend/Dockerfile` |

### 12.3 Hooks

**`useVoiceSession`** — Full WebRTC lifecycle manager with direct OpenAI connection.
- Calls `POST /calls` to create session → `POST /calls/{id}/offer` for SDP proxy exchange
- Creates RTCPeerConnection, captures microphone, creates `"oai-events"` data channel
- Translates OpenAI events to internal format: `conversation.item.input_audio_transcription.completed` → human transcription, `response.audio_transcript.done` → agent transcription
- Filters `response.audio.delta` from debug handler (high-frequency)
- Uses local variable for cleanup (avoids stale closure bug) + `beforeunload` beacon
- Returns: `status`, `callId`, `startSession`, `endSession`, `onControlMessage`, `onDebugMessage`, `error`

**`useDebugChannel`** — Parses debug events into typed state.
- Maintains: `turns` (DebugTurn[]), `fsmState`, `routing` (DebugRouting), `events` (DebugEvent[]), `latencies` (DebugLatency[])
- Limits events array to 100 entries

### 12.4 Components

**`VoiceSession`** — Main orchestrator component. Wires hooks together.
- Lazy-loads `DebugPanel` via `next/dynamic` (no debug overhead when disabled)
- Uses OpenAI events for speaking indicators (`speech_started/stopped`, `response.audio.delta/done`)
- Shows: connection status badge, start/end call buttons, mic/speaker animations, transcription panel

**`MicAnimation`** — Green pulsing circle with mic icon when user is speaking.

**`SpeakerAnimation`** — Blue pulsing circle with speaker icon when agent is speaking.

**`TranscriptionPanel`** — Chat-style display. Human messages right-aligned (primary color), agent messages left-aligned (muted). Auto-scrolls to bottom on new entries.

**`DebugPanel`** — 3-column grid: FSM State badge, Last Routing details (Route A/B confidence, short circuit, LLM fallback), Latency measurements (color-coded: green < 200ms, red > 200ms). Plus Turn History list and Event Log (last 20, monospace JSON).

### 12.5 Data Flow

```
1. User clicks "Start Call"
   → useVoiceSession.startSession()
   → POST /calls → POST /calls/{id}/offer (SDP proxy to OpenAI)
   → RTCPeerConnection established directly with OpenAI
   → getUserMedia → microphone track added to connection
   → Data channel "oai-events" created

2. Audio flows continuously via WebRTC (Opus, UDP) directly to OpenAI
   → OpenAI handles STT, VAD, and response generation

3. OpenAI events arrive on "oai-events" data channel
   → conversation.item.input_audio_transcription.completed → human transcription
   → response.audio_transcript.done → agent transcription
   → input_audio_buffer.speech_started/stopped → speaking indicators
   → response.audio.delta/done → agent speaking indicators

4. Agent response audio streams back via WebRTC directly from OpenAI
   → Browser plays through speaker (remote audio track)

5. Non-audio events forwarded to debug handler (when enabled)
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
