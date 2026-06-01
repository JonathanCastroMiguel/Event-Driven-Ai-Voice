## 1. Coordinator state preparation

- [ ] 1.1 [BE] Add `pending_function_calls: dict[UUID, tuple[str, str]]` to `CoordinatorRuntimeState` to hold `(fn_call_id, fn_item_id)` keyed by `agent_generation_id`
- [ ] 1.2 [BE] Add `cached_instructions: dict[UUID, str]` to `CoordinatorRuntimeState` for system-prompt reuse on direct follow-up, keyed by `agent_generation_id`
- [ ] 1.3 [BE] Add helper methods on `CoordinatorRuntimeState` to set/clear these entries (clear on `done`, `cancelled`, `error`)

## 2. Bridge — strip direct-path orchestration

- [ ] 2.1 [BE] In `realtime_event_bridge.py` `_translate_event` handler for `response.function_call_arguments.done`, remove the `if action.department == "direct"` branch. Emit `model_router_action` for all departments
- [ ] 2.2 [BE] Add `fn_call_id` and `fn_item_id` to the `model_router_action` envelope payload (alongside `department` and `summary`)
- [ ] 2.3 [BE] Remove the `_pending_direct_audio` branch in the `response.done` handler. Also remove `_pending_direct_audio`, `_pending_fn_call_id`, `_pending_fn_item_id`, `_last_instructions` from `OpenAIRealtimeEventBridge.__init__`
- [ ] 2.4 [BE] Remove the caching of `instructions` in `send_voice_start` (no longer needed in Bridge)
- [ ] 2.5 [BE] Remove the now-unused `bridge_direct_response_via_tool`, `bridge_direct_fn_ack`, `bridge_direct_audio_followup` log calls and the helper code that drove them

## 3. Coordinator — add direct dispatch

- [ ] 3.1 [BE] Modify `Coordinator._on_audio_committed` (or wherever the original `response.create` is sent) to cache the assembled `instructions` in `state.cached_instructions[agent_generation_id]`
- [ ] 3.2 [BE] In `Coordinator._on_model_router_action`, branch on `payload["department"]`:
  - If `"direct"`: invoke new `_dispatch_direct(envelope)` method
  - Else: existing specialist flow
- [ ] 3.3 [BE] Implement `_dispatch_direct(envelope)`:
  - Transition AgentFSM `routing → speaking` via `agent_fsm.voice_started(envelope.ts)`
  - Send `conversation.item.create` with `type="function_call_output"`, `call_id=payload["fn_call_id"]`, `output='{"status":"ok"}'`
  - Build follow-up `response.create` with `output_modalities=["audio"]`, `instructions=state.cached_instructions[agent_generation_id]`, no `tools`
  - Emit `RealtimeVoiceStart` with the follow-up payload and `response_source="router"`
- [ ] 3.4 [BE] Move the `route_result(direct)` debug event emission from `_on_voice_completed` to the new `_dispatch_direct` (emitted on direct dispatch, parallel to how specialist emits `route_result(delegate)`)
- [ ] 3.5 [BE] In `_on_voice_completed`, remove the `elif self._agent_fsm.state == AgentState.ROUTING` branch that does `voice_started + voice_completed` together. The FSM should already be in `speaking` when `voice_generation_completed` arrives for any path
- [ ] 3.6 [BE] In `_on_voice_completed`, on `done` / `cancelled` / `error` transitions, clear `state.cached_instructions[agent_generation_id]` and `state.pending_function_calls[agent_generation_id]`

## 4. Unit tests — Bridge

- [ ] 4.1 [TEST] In `test_realtime_event_bridge.py`, replace the test "Function call with direct triggers no routing event" with a test asserting that `direct` now emits `model_router_action` with `fn_call_id` and `fn_item_id` in payload
- [ ] 4.2 [TEST] Remove tests that asserted Bridge sends `function_call_output` or follow-up `response.create` for direct (those behaviors no longer live in Bridge)
- [ ] 4.3 [TEST] Remove tests for `_pending_direct_audio`, `_pending_fn_call_id`, `_pending_fn_item_id`, `_last_instructions` Bridge state fields
- [ ] 4.4 [TEST] Add a test verifying Bridge does NOT emit `voice_generation_completed` for the initial classification response (only for follow-ups that actually generate audio)

## 5. Unit tests — Coordinator

- [ ] 5.1 [TEST] In `test_coordinator.py`, add test: `model_router_action(direct)` triggers AgentFSM `routing → speaking`
- [ ] 5.2 [TEST] Add test: on direct dispatch, Coordinator sends `function_call_output` with the `call_id` from the envelope payload
- [ ] 5.3 [TEST] Add test: on direct dispatch, Coordinator sends follow-up `response.create` with cached instructions, `output_modalities=["audio"]`, and no `tools`
- [ ] 5.4 [TEST] Add test: cached instructions are cleared on `voice_generation_completed`
- [ ] 5.5 [TEST] Add test: cached instructions are cleared on cancellation (e.g. via barge-in)
- [ ] 5.6 [TEST] Add test: `_on_voice_completed` does NOT call `voice_started` (asserts the workaround is gone)
- [ ] 5.7 [TEST] Add test: `route_result(direct)` debug event is emitted at direct dispatch time, not at `voice_generation_completed`

## 6. Integration / E2E

- [ ] 6.1 [E2E] In `backend/tests/e2e/test_event_pipeline.py` (or equivalent), add a barge-in test for the direct path: simulate `speech_started` arriving between `model_router_action(direct)` and `voice_generation_completed`; assert Coordinator emits `realtime_voice_cancel` and AgentFSM goes to `cancelled`
- [ ] 6.2 [E2E] Add an end-to-end direct turn test asserting the full sequence: `audio_committed` → `model_router_action(direct)` → `function_call_output` sent → follow-up `response.create` sent → `voice_generation_completed` → buffer updated with agent text

## 7. Documentation

- [ ] 7.1 [BE] Update `ai-specs/specs/architecture.md` direct-path section to show Coordinator as the dispatcher (remove Bridge short-circuit description)
- [ ] 7.2 [BE] Update `ai-specs/specs/architecture-diagram.md` to reflect the symmetric flow (both direct and specialist routed through Coordinator)
- [ ] 7.3 [BE] Update `backend/src/voice_runtime/realtime_event_bridge.py` module docstring to remove mentions of direct two-step handling
- [ ] 7.4 [BE] Update `backend/src/voice_runtime/coordinator.py` docstrings/comments to describe both direct and specialist dispatch in `_on_model_router_action`

## 8. Verification

- [ ] 8.1 [BE] Run `uv run pytest tests/unit/test_realtime_event_bridge.py tests/unit/test_coordinator.py tests/unit/test_agent_fsm.py` — all green
- [ ] 8.2 [BE] Run `uv run pytest tests/e2e/` — all green
- [ ] 8.3 [BE] Run `uv run ruff check src/voice_runtime/` and `uv run mypy src/voice_runtime/` — clean
- [ ] 8.4 [BE] Manual smoke test: deploy locally, make a direct-path call ("Hola"), verify response works and that logs show `model_router_action(direct)` followed by Coordinator-driven follow-up
- [ ] 8.5 [BE] Manual smoke test: make a specialist-path call, verify behavior unchanged
- [ ] 8.6 [BE] Manual smoke test: barge-in during direct response, verify cancellation works
