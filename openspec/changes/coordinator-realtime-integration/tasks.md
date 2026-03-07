## 1. Model Router — Prompt Template & Parser

- [ ] 1.1 [BE] Create `router_registry/v1/router_prompt.yaml` with router system prompt template (identity, decision rules, departments, guardrails, language instruction)
- [ ] 1.2 [BE] Create `src/routing/model_router.py` with `RouterPromptBuilder` class — builds `response.create` payload from template + conversation history
- [ ] 1.3 [BE] Create `parse_model_action()` function in `model_router.py` — parses accumulated transcript into `ModelRouterAction` or `None` (direct voice)
- [ ] 1.4 [BE] Create `ModelRouterAction` dataclass with `department` (validated enum) and `summary` fields
- [ ] 1.5 [BE] Add `load_router_prompt()` function to load and validate `router_prompt.yaml` at startup
- [ ] 1.6 [TEST] Unit tests for `RouterPromptBuilder` — first turn (empty history), subsequent turns (with history), history truncation
- [ ] 1.7 [TEST] Unit tests for `parse_model_action` — valid JSON action, direct voice (non-JSON), malformed JSON, wrong schema, unknown department

## 2. Realtime Event Bridge — New Events & JSON Action Detection

- [ ] 2.1 [BE] Add `input_audio_buffer.committed` → `audio_committed` event translation in `_translate_event()`
- [ ] 2.2 [BE] Add `_response_transcript_buffer` field to Bridge, accumulate text from `response.audio_transcript.delta` events
- [ ] 2.3 [BE] Reset `_response_transcript_buffer` on `response.created` event
- [ ] 2.4 [BE] Modify `response.done` handling — check accumulated transcript via `parse_model_action()`, emit `model_router_action` or `voice_generation_completed` accordingly
- [ ] 2.5 [BE] Add `silence_duration_ms` to the one-time `session.update` in `calls.py`, configurable via `VAD_SILENCE_DURATION_MS` env var (default 500)
- [ ] 2.6 [TEST] Unit tests for `audio_committed` event translation
- [ ] 2.7 [TEST] Unit tests for transcript accumulation and JSON action detection (valid action, direct voice, malformed JSON, buffer reset)

## 3. Turn Manager — Committed-Based Turn Finalization

- [ ] 3.1 [BE] Add `handle_audio_committed()` method to TurnManager that finalizes the current open turn
- [ ] 3.2 [BE] Modify `handle_transcript_final()` to store transcript text for logging only (no turn finalization)
- [ ] 3.3 [TEST] Unit tests for committed-based turn lifecycle (speech_started → audio_committed → finalized)
- [ ] 3.4 [TEST] Unit tests verifying `transcript_final` does NOT finalize turns

## 4. Agent FSM — Simplified State Transitions

- [ ] 4.1 [BE] Replace FSM states: remove `thinking`, add `routing`, `speaking`. New states: `idle`, `routing`, `speaking`, `waiting_tools`, `done`, `cancelled`, `error`
- [ ] 4.2 [BE] Update transition map: `idle→routing`, `routing→speaking`, `routing→waiting_tools`, `waiting_tools→speaking`, `speaking→done`, `*→cancelled`
- [ ] 4.3 [BE] Remove `handle_turn()` with Route A/B classification logic. Replace with `start_routing()`, `voice_started()`, `specialist_action()`, `tool_result()`, `voice_completed()` methods
- [ ] 4.4 [BE] Remove embedding classification imports (Router, language detection, lexicon, short utterance registry)
- [ ] 4.5 [TEST] Unit tests for new FSM transitions (all valid paths + invalid transition rejection)

## 5. Coordinator — Model-as-Router Integration

- [ ] 5.1 [BE] Add `_on_audio_committed()` handler — creates agent_generation_id, builds router prompt via `RouterPromptBuilder`, emits `realtime_voice_start`
- [ ] 5.2 [BE] Add `_on_model_router_action()` handler — dispatches specialist tool execution, optionally emits filler, constructs specialist response on tool result
- [ ] 5.3 [BE] Modify `_on_transcript_final()` — async logging only (persist text, append to buffer, emit debug event), no turn finalization or routing
- [ ] 5.4 [BE] Add `audio_committed` and `model_router_action` to `handle_event()` dispatch match
- [ ] 5.5 [BE] Remove embedding routing code from `_on_human_turn_finalized()` (Router.classify, RoutingContextBuilder, language detection, FSM handle_turn with classification)
- [ ] 5.6 [BE] Update Coordinator `__init__` — replace `Router` dependency with `RouterPromptBuilder`, remove `routing_context_window`, `routing_short_text_chars`, `llm_context_window` params
- [ ] 5.7 [TEST] Unit tests for `_on_audio_committed()` — router prompt construction, voice start emission, first turn vs. subsequent turns
- [ ] 5.8 [TEST] Unit tests for `_on_model_router_action()` — specialist dispatch, filler strategy, tool result handling
- [ ] 5.9 [TEST] Unit tests for async transcript logging — text persisted but no routing triggered

## 6. Routing Context — Simplify to History Formatter

- [ ] 6.1 [BE] Simplify `RoutingContextBuilder` to a `format_history()` method that returns message pairs from ConversationBuffer
- [ ] 6.2 [BE] Remove `enriched_text`, `llm_context`, `short_text_chars`, `context_window`, `llm_context_window` fields and methods
- [ ] 6.3 [TEST] Unit tests for simplified `format_history()` — empty buffer, multiple turns, buffer limit respected

## 7. Wiring & Configuration

- [ ] 7.1 [BE] Update `src/main.py` lifespan — load router prompt, wire `RouterPromptBuilder` into Coordinator instead of `Router`
- [ ] 7.2 [BE] Update `src/api/routes/calls.py` — add `VAD_SILENCE_DURATION_MS` to session.update, wire new event types in WebSocket handler
- [ ] 7.3 [BE] Add `VAD_SILENCE_DURATION_MS` to Settings with default 500
- [ ] 7.4 [BE] Update `EventEnvelope` types or `EventSource` if needed for `audio_committed` and `model_router_action`

## 8. Cleanup

- [ ] 8.1 [BE] Remove unused imports from Coordinator (Router, language detection, RoutingContextBuilder embedding methods)
- [ ] 8.2 [BE] Remove or deprecate embedding-related Prometheus metrics (`ROUTE_A_CONFIDENCE`, `ROUTE_B_CONFIDENCE`) from hot path
- [ ] 8.3 [BE] Update structured logging — replace `routing_decision` log with new model-router-based log format
