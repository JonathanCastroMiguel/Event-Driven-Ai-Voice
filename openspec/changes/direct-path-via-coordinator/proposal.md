## Why

The direct path (smalltalk, guardrails, out-of-scope, simple questions) is
currently handled **inside the Bridge** as a short-circuit: when the model
emits `function_call(department="direct")`, the Bridge intercepts the event,
acknowledges the function call, and sends a second `response.create`
reusing the cached system prompt — all without notifying the Coordinator.
The Coordinator only learns the turn happened when
`voice_generation_completed` arrives at the end.

This optimization shaved ~5-15ms off the hot path but produced four
architectural problems that block clean open-source publication:

1. **The Bridge violates its stated responsibility** ("translate OpenAI
   events ↔ EventEnvelopes"). It now also orchestrates a multi-step flow.
2. **The AgentFSM has a workaround** in [coordinator.py:848-856](backend/src/voice_runtime/coordinator.py#L848-L856)
   that performs `routing→speaking→done` in a single operation because the
   Coordinator never observed the intermediate transitions for direct path.
3. **In-flight state is split**: `_pending_direct_audio`, `_pending_fn_call_id`,
   `_pending_fn_item_id`, and `_last_instructions` live in the Bridge.
   The Coordinator has no visibility into them, complicating cancellation
   and observability.
4. **The design is asymmetric** with the specialist path: for specialists,
   the Bridge emits `model_router_action` and the Coordinator owns the
   flow; for direct, the Bridge owns it. New contributors have to trace
   two different orchestration patterns to understand one routing system.

## What Changes

- **Bridge emits `model_router_action(department, summary)` for ALL
  function-call routing decisions** — including `department="direct"`.
  No more special-case handling inside the Bridge.
- **Coordinator becomes the single dispatcher**:
  - For `direct`: Coordinator sends the function-call acknowledgement
    (`function_call_output`) and the second `response.create` reusing the
    cached system prompt + conversation history.
  - For specialist departments (`billing`, `sales`, `support`, `retention`):
    existing flow (call specialist text model → "say exactly"
    `response.create`).
- **AgentFSM transitions become clean and uniform**:
  - Direct path: `IDLE → ROUTING → SPEAKING → DONE`
  - Specialist path: `IDLE → ROUTING → WAITING_TOOLS → SPEAKING → DONE`
  - Removed: the dual `voice_started + voice_completed` transition
    workaround in `_on_voice_completed`.
- **In-flight state moves to the Coordinator**: pending function-call ids
  and cached system instructions are owned by the Coordinator.
- **Bridge returns to being a pure event translator**.

**No external API or contract changes.** This is an internal refactor
of the routing orchestration. Latency cost on the direct path is
~5-15ms (one extra Coordinator hop), accepted as the price of
architectural clarity for open source.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `realtime-event-bridge`: Remove direct-path orchestration. The Bridge
  always emits `model_router_action` envelopes for any
  `route_to_specialist` function call (regardless of department) and no
  longer sends `function_call_output` acks or follow-up `response.create`
  messages. Bridge state fields specific to the direct two-step
  (`_pending_direct_audio`, `_pending_fn_call_id`, `_pending_fn_item_id`,
  `_last_instructions`) are removed.

- `coordinator`: Add direct-path dispatch. When a `model_router_action`
  envelope arrives with `department="direct"`, the Coordinator sends the
  function-call acknowledgement and a follow-up `response.create` (without
  tools, reusing the system prompt + history it built in the original
  dispatch). The existing specialist dispatch path is unchanged. The
  Coordinator also exercises the natural `ROUTING → SPEAKING → DONE`
  AgentFSM transitions on the direct path (removing the dual-transition
  workaround in `_on_voice_completed`).

**Note on `agent-fsm`**: the FSM transition definitions
(`openspec/specs/agent-fsm/spec.md`) already describe the clean
`routing + voice_started → speaking` transition. The current
dual-transition behavior is a Coordinator-side workaround that diverges
from the spec. This change brings the Coordinator into compliance with
the existing `agent-fsm` spec, so no delta is needed for that
capability.

## Impact

**Code:**
- `backend/src/voice_runtime/realtime_event_bridge.py` — remove direct
  short-circuit (`_pending_direct_audio` branch, `bridge_direct_*` events,
  `function_call_output` sending, second `response.create` sending).
  Simplify state.
- `backend/src/voice_runtime/coordinator.py` — handle
  `model_router_action` with `department="direct"`; emit
  `function_call_output` and follow-up `response.create`. Remove the
  dual-transition workaround in `_on_voice_completed`.
- `backend/src/voice_runtime/agent_fsm.py` — no transition table change
  needed (existing `voice_started` and `voice_completed` events still
  apply); confirm tests cover natural direct-path transitions.
- `backend/src/voice_runtime/state.py` — Coordinator state may gain
  fields previously owned by Bridge (cached instructions, pending
  function-call ids).

**Tests:**
- `backend/tests/unit/test_realtime_event_bridge.py` — update direct-path
  tests; remove tests that asserted Bridge sends `function_call_output`
  for direct.
- `backend/tests/unit/test_coordinator.py` — add tests for Coordinator
  handling `model_router_action(direct)` and the follow-up dispatch.
- `backend/tests/unit/test_agent_fsm.py` — verify clean direct-path
  transitions (no dual-transition).
- `backend/tests/e2e/` — confirm end-to-end direct-path flow still works.

**Specs:**
- `openspec/specs/realtime-event-bridge/spec.md` — remove requirements
  about direct two-step inside the bridge; update routing requirements
  to be department-agnostic.
- `openspec/specs/coordinator/spec.md` — add requirements for direct-path
  dispatch.
- `openspec/specs/agent-fsm/spec.md` — clarify that direct-path
  transitions are explicit and uniform with specialist.

**Documentation:**
- `ai-specs/specs/architecture.md` and `architecture-diagram.md` — update
  the direct-path flow description so the diagram and prose reflect
  Coordinator ownership.

**Observability:**
- `model_router_action` events will fire for direct turns too —
  consumers (debug panel, traces) gain visibility into direct-path
  routing that previously was invisible.

**Latency:**
- Direct path adds ~5-15ms (one Coordinator event hop). Specialist
  path latency is unchanged.

**No external contract change.** Frontend, public API, and database
schema are unaffected.
