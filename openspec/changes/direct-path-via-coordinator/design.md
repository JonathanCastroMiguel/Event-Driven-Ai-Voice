## Context

The current voice runtime supports two routing paths after a user turn:

- **Specialist path** (`department ∈ {billing, sales, support, retention}`):
  Bridge emits `model_router_action`, the Coordinator calls the specialist
  text model, then sends a `response.create` with `"Say exactly: …"`.
  AgentFSM transitions are `IDLE → ROUTING → WAITING_TOOLS → SPEAKING → DONE`.

- **Direct path** (`department = "direct"`): The Bridge intercepts the
  function call locally, sends the `function_call_output` ack, and sends a
  follow-up `response.create` reusing `_last_instructions` — the system
  prompt cached when the original `response.create` was sent. The
  Coordinator only sees the final `voice_generation_completed`. AgentFSM
  is forced to do `ROUTING → SPEAKING → DONE` in a single operation at
  the end of the turn.

The direct shortcut was added when the two-step routing pattern was
introduced and the goal was to minimize latency on the most common
path. It worked, but produced the issues listed in the proposal:
Bridge owns orchestration it should not own, FSM has a structural
workaround, in-flight state is split between Bridge and Coordinator,
and the design is asymmetric with the specialist path.

This refactor unifies the two paths under the Coordinator with the
explicit acceptance of ~5-15 ms of extra latency on direct turns. The
project targets open-source publication; architectural clarity and a
single orchestration owner outweigh the saved milliseconds.

## Goals / Non-Goals

**Goals:**

- The Bridge is a pure event translator. No business orchestration.
- The Coordinator is the single owner of routing dispatch for both
  direct and specialist departments.
- AgentFSM transitions are explicit and uniform — no dual-transition
  workaround in `_on_voice_completed`.
- In-flight state related to the direct two-step (pending function-call
  ids, cached system instructions) lives in the Coordinator.
- No change to external contracts (frontend, public API, database
  schema).
- No regression of existing behavior: direct turns still produce the
  same observed conversation; specialist turns are unchanged.

**Non-Goals:**

- Reworking the FSM transition graph itself. The states and transitions
  defined in `agent_fsm.py` are correct; only the Coordinator's use of
  them changes.
- Performance optimization of the new direct path. The +5-15 ms hop
  through the Coordinator is accepted.
- Changes to the specialist path behavior.
- Changes to barge-in semantics or the cancellation flow. Barge-in
  remains driven by `speech_started` arriving while AgentFSM is in
  `ROUTING` or `SPEAKING`.
- Combining direct + specialist behind a single abstract dispatch
  method. They are distinct enough (one calls a text model, the other
  doesn't) that separate methods on the Coordinator are clearer.

## Decisions

### D1: `model_router_action` is emitted by the Bridge for *all* departments

**Decision:** Remove the `if action.department == "direct"` branch in
`realtime_event_bridge.py`. The Bridge constructs and emits a
`model_router_action` EventEnvelope for every successful parse of
`route_to_specialist`, including `department="direct"`.

The envelope payload includes `department`, `summary`, and the OpenAI
function-call identifiers needed for the acknowledgement
(`pending_fn_call_id`, `pending_fn_item_id`).

**Why:** This restores the Bridge's stated responsibility (translate
OpenAI events ↔ EventEnvelopes) and gives the Coordinator a single
entry point for all routing decisions.

**Alternative considered:** Keep direct in the Bridge, refactor only
the FSM workaround. Rejected because it preserves the split state
ownership and the asymmetric design — the two main reasons we are
doing this refactor.

### D2: Function-call identifiers travel in the envelope payload

**Decision:** Add `fn_call_id` and `fn_item_id` to the
`model_router_action` envelope payload. They are needed by the
Coordinator to send the `function_call_output` ack before the
follow-up `response.create`.

**Why:** They are part of the routing decision the Coordinator needs
to act on. Putting them in the envelope keeps the Coordinator
self-contained for handling direct dispatch.

**Alternative considered:** Have the Coordinator query the Bridge for
the pending ids. Rejected — that re-introduces a stateful coupling
between Bridge and Coordinator that we are trying to remove.

### D3: Coordinator dispatches direct path via a new handler

**Decision:** Extend `Coordinator._on_model_router_action` (or split
into `_on_direct_action` and `_on_specialist_action`) so that when
`department == "direct"` it:

1. Transitions AgentFSM `ROUTING → SPEAKING` via the existing
   `voice_started` event.
2. Builds a `conversation.item.create` payload with
   `type: "function_call_output"`, the `call_id` from the envelope,
   and `output: '{"status":"ok"}'`.
3. Builds a follow-up `response.create` with `output_modalities:
   ["audio"]` and the same system prompt + history used in the
   original dispatch (already constructed via
   `RouterPromptBuilder.build_response_create`, minus the `tools`
   field).
4. Sends both via the Bridge's `send_to_frontend`.

The Coordinator caches the assembled system instructions per
`agent_generation_id` so the follow-up can reuse them without
rebuilding history.

**Why:** Keeps the routing/dispatch logic in one component. The
Coordinator already owns prompt building and the conversation buffer,
so it has everything it needs.

**Alternative considered:** Have the Coordinator call a method on
the Bridge like `bridge.dispatch_direct_followup()`. Rejected
because it preserves the spilled responsibility — even if the call
originates from the Coordinator, the orchestration logic would still
live in the Bridge.

### D4: Cached instructions live in the Coordinator's runtime state

**Decision:** Move `_last_instructions` from the Bridge to
`CoordinatorRuntimeState`, keyed by `agent_generation_id`. The
Bridge no longer caches anything routing-related.

**Why:** It is the Coordinator's prompt — it always was — so it
should live with the Coordinator's other per-generation state.

### D5: AgentFSM transitions become uniform

**Decision:** Remove the special case in
`coordinator.py:_on_voice_completed` that does
`voice_started + voice_completed` when the FSM is still in `ROUTING`.

After this refactor:

- Direct path: Coordinator explicitly calls
  `agent_fsm.voice_started()` when sending the follow-up
  `response.create`, then `agent_fsm.voice_completed()` when
  `voice_generation_completed` arrives.
- Specialist path: unchanged — Coordinator already calls
  `voice_started` (implicitly via the `tool_result → SPEAKING`
  transition) and `voice_completed` at the end.

**Why:** A consistent FSM lifecycle is easier to reason about,
observe, and test. The workaround was a side-effect of the Bridge
short-circuit; removing the short-circuit also removes the need for
the workaround.

### D6: The follow-up `response.create` reuses the original instructions verbatim

**Decision:** For direct dispatch, the Coordinator reuses the same
`instructions` string from the original `response.create` (the one
that included system mechanic + identity + routing rules + guardrails
+ language instruction + history). It does NOT rebuild from
`RouterPromptBuilder` a second time, and it does NOT include the
`tools` field.

**Why:** Two reasons. First, this is what the Bridge does today —
preserving exact behavior on the direct path is a goal. Second,
rebuilding would risk subtle drift (e.g., a new turn appended to
history between the two `response.create` calls), which could
confuse the voice model.

**Alternative considered:** Rebuild from scratch. Rejected for the
drift risk above.

### D7: Telemetry — `model_router_action` events for direct will be visible

**Decision:** When direct routing now emits `model_router_action`,
debug and observability consumers (debug panel, OpenTelemetry traces)
will see these events for direct turns where previously they did
not. We accept this as a feature, not a bug — it gives operators
visibility into direct-path classification that was previously
invisible.

**Why:** More observability is better. Operators already see
`model_router_action` for specialists; seeing it for direct provides
parity.

**Note:** Any dashboards or alerts that filter on `department !=
"direct"` to deduplicate should be reviewed and adjusted.

## Risks / Trade-offs

- **[Risk] Direct path adds ~5-15 ms latency.** → Mitigation:
  acceptable per proposal. The Coordinator dispatch is in-process
  asyncio; no network or persistence hop is added. We can measure
  with the existing `send_to_created_ms` / `created_to_done_ms`
  metrics in `bridge_raw_event` logs.

- **[Risk] In-progress refactor could regress barge-in.** Barge-in
  depends on the AgentFSM being in a cancellable state when
  `speech_started` arrives mid-flight. The new flow keeps the FSM in
  `ROUTING` until the Coordinator explicitly transitions to
  `SPEAKING`, which is the same window the current code provides.
  → Mitigation: add an integration test that simulates barge-in during
  direct path (`speech_started` arriving between
  `model_router_action(direct)` and the follow-up `voice_completed`).

- **[Risk] Cached instructions key collision.** Two consecutive turns
  could overlap if cancellation timing is unlucky. → Mitigation: key
  cached instructions by `agent_generation_id`, which is unique per
  generation. Clear the cache entry when the generation completes,
  errors, or is cancelled.

- **[Risk] Tests in `test_realtime_event_bridge.py` will need broad
  changes**. The unit tests assert on the Bridge sending
  `function_call_output` and the follow-up `response.create`. These
  assertions move to `test_coordinator.py`. → Mitigation: this is
  expected work, captured in tasks.md.

- **[Trade-off] We're adding code to the Coordinator** (already the
  largest file in the runtime). → Net effect: ~30-50 lines added to
  Coordinator, ~40-60 lines removed from Bridge. Slight increase in
  Coordinator complexity, but the complexity has a clear home now.

- **[Risk] Debug panel may show new event flow.** Operators who know
  the current behavior may be surprised by `model_router_action`
  events for direct turns. → Mitigation: documentation update in
  `ai-specs/specs/architecture.md` and `architecture-diagram.md`.

## Migration Plan

This is an internal refactor with no external contracts and no data
schema changes. Deployment is a single backend image rebuild and
container restart.

**Steps:**

1. Implement Bridge changes (D1, D2): emit `model_router_action` for
   all departments, drop direct short-circuit. Remove Bridge state
   fields specific to direct two-step.
2. Implement Coordinator changes (D3, D4, D5, D6): handle
   `model_router_action(direct)`, dispatch follow-up
   `response.create`, manage `voice_started`/`voice_completed` for
   direct, cache instructions in CoordinatorRuntimeState.
3. Update unit tests for both components.
4. Add a barge-in integration test for direct path.
5. Update spec deltas (`realtime-event-bridge`, `coordinator`,
   `agent-fsm`).
6. Update architecture docs.
7. Build, deploy, verify with the existing e2e test for direct
   smalltalk turns.

**Rollback strategy:** Single commit revert. The change is internal;
no migration is needed.

## Open Questions

- **Q1:** Do we want to keep `_pending_fn_call_id` and
  `_pending_fn_item_id` as Bridge-side fields in case OpenAI sends
  another event that needs them, or fully remove them? → Proposed
  answer: fully remove. They are routing-specific and the Coordinator
  is the routing owner. If a future need emerges, we will add them
  back where needed.

- **Q2:** Should the `model_router_action` envelope payload include
  the cached `instructions` string for the direct follow-up, or
  should the Coordinator hold it? → Proposed answer: Coordinator
  holds it. Envelopes should be small and stateless; orchestration
  state belongs to the Coordinator.

- **Q3:** Do we want to add a feature flag for the new flow during
  rollout? → Proposed answer: no. The refactor is small and tests
  cover the regression risk. A single revert is sufficient if
  something is wrong.
