## 1. Model Router — Prompt Template & Parser

- [x] 1.1 [BE] Create `router_registry/v1/router_prompt.yaml` with router system prompt template (identity, decision rules, departments, guardrails, language instruction)
- [x] 1.2 [BE] Create `src/routing/model_router.py` with `RouterPromptBuilder` class — builds `response.create` payload from template + conversation history
- [x] 1.3 [BE] Create `parse_model_action()` function in `model_router.py` — parses accumulated transcript into `ModelRouterAction` or `None` (direct voice)
- [x] 1.4 [BE] Create `ModelRouterAction` dataclass with `department` (validated enum) and `summary` fields
- [x] 1.5 [BE] Add `load_router_prompt()` function to load and validate `router_prompt.yaml` at startup
- [x] 1.6 [TEST] Unit tests for `RouterPromptBuilder` — first turn (empty history), subsequent turns (with history), history truncation
- [x] 1.7 [TEST] Unit tests for `parse_model_action` — valid JSON action, direct voice (non-JSON), malformed JSON, wrong schema, unknown department

## 2. Realtime Event Bridge — New Events & JSON Action Detection

- [x] 2.1 [BE] Add `input_audio_buffer.committed` → `audio_committed` event translation in `_translate_event()`
- [x] 2.2 [BE] Add `_response_transcript_buffer` field to Bridge, accumulate text from `response.audio_transcript.delta` events
- [x] 2.3 [BE] Reset `_response_transcript_buffer` on `response.created` event
- [x] 2.4 [BE] Modify `response.done` handling — check accumulated transcript via `parse_model_action()`, emit `model_router_action` or `voice_generation_completed` accordingly
- [x] 2.5 [BE] Add `silence_duration_ms` to the one-time `session.update` in `calls.py`, configurable via `VAD_SILENCE_DURATION_MS` env var (default 300)
- [x] 2.6 [TEST] Unit tests for `audio_committed` event translation
- [x] 2.7 [TEST] Unit tests for transcript accumulation and JSON action detection (valid action, direct voice, malformed JSON, buffer reset)

## 3. Turn Manager — Committed-Based Turn Finalization

- [x] 3.1 [BE] Add `handle_audio_committed()` method to TurnManager that finalizes the current open turn
- [x] 3.2 [BE] Modify `handle_transcript_final()` to store transcript text for logging only (no turn finalization)
- [x] 3.3 [TEST] Unit tests for committed-based turn lifecycle (speech_started → audio_committed → finalized)
- [x] 3.4 [TEST] Unit tests verifying `transcript_final` does NOT finalize turns

## 4. Agent FSM — Simplified State Transitions

- [x] 4.1 [BE] Replace FSM states: remove `thinking`, add `routing`, `speaking`. New states: `idle`, `routing`, `speaking`, `waiting_tools`, `done`, `cancelled`, `error`
- [x] 4.2 [BE] Update transition map: `idle→routing`, `routing→speaking`, `routing→waiting_tools`, `waiting_tools→speaking`, `speaking→done`, `*→cancelled`
- [x] 4.3 [BE] Remove `handle_turn()` with Route A/B classification logic. Replace with `start_routing()`, `voice_started()`, `specialist_action()`, `tool_result()`, `voice_completed()` methods
- [x] 4.4 [BE] Remove embedding classification imports (Router, language detection, lexicon, short utterance registry)
- [x] 4.5 [TEST] Unit tests for new FSM transitions (all valid paths + invalid transition rejection)

## 5. Coordinator — Model-as-Router Integration

- [x] 5.1 [BE] Add `_on_audio_committed()` handler — creates agent_generation_id, builds router prompt via `RouterPromptBuilder`, emits `realtime_voice_start`
- [x] 5.2 [BE] Add `_on_model_router_action()` handler — dispatches specialist tool execution, optionally emits filler, constructs specialist response on tool result
- [x] 5.3 [BE] Modify `_on_transcript_final()` — async logging only (persist text, append to buffer, emit debug event), no turn finalization or routing
- [x] 5.4 [BE] Add `audio_committed` and `model_router_action` to `handle_event()` dispatch match
- [x] 5.5 [BE] Remove embedding routing code from `_on_human_turn_finalized()` (Router.classify, RoutingContextBuilder, language detection, FSM handle_turn with classification)
- [x] 5.6 [BE] Update Coordinator `__init__` — replace `Router` dependency with `RouterPromptBuilder`, remove `routing_context_window`, `routing_short_text_chars`, `llm_context_window` params
- [x] 5.7 [TEST] Unit tests for `_on_audio_committed()` — router prompt construction, voice start emission, first turn vs. subsequent turns
- [x] 5.8 [TEST] Unit tests for `_on_model_router_action()` — specialist dispatch, filler strategy, tool result handling
- [x] 5.9 [TEST] Unit tests for async transcript logging — text persisted but no routing triggered

## 6. Routing Context — Simplify to History Formatter

- [x] 6.1 [BE] Simplify `RoutingContextBuilder` to a `format_history()` method that returns message pairs from ConversationBuffer
- [x] 6.2 [BE] Remove `enriched_text`, `llm_context`, `short_text_chars`, `context_window`, `llm_context_window` fields and methods
- [x] 6.3 [TEST] Unit tests for simplified `format_history()` — empty buffer, multiple turns, buffer limit respected

## 7. Wiring & Configuration

- [x] 7.1 [BE] Update `src/main.py` lifespan — load router prompt, wire `RouterPromptBuilder` into Coordinator instead of `Router`
- [x] 7.2 [BE] Update `src/api/routes/calls.py` — add `VAD_SILENCE_DURATION_MS` to session.update, wire new event types in WebSocket handler
- [x] 7.3 [BE] Add `VAD_SILENCE_DURATION_MS` to Settings with default 300
- [x] 7.4 [BE] Update `EventEnvelope` types or `EventSource` if needed for `audio_committed` and `model_router_action`

## 8. Cleanup

- [x] 8.1 [BE] Remove unused imports from Coordinator (Router, language detection, RoutingContextBuilder embedding methods)
- [x] 8.2 [BE] Remove or deprecate embedding-related Prometheus metrics (`ROUTE_A_CONFIDENCE`, `ROUTE_B_CONFIDENCE`) from hot path
- [x] 8.3 [BE] Update structured logging — replace `routing_decision` log with new model-router-based log format
