## 1. Model Router — Department.DIRECT + tool_choice required (DONE)

- [x] 1.1 [BE] Add `DIRECT = "direct"` to `Department` enum in `model_router.py`
- [x] 1.2 [BE] Update `ROUTE_TOOL_DEFINITION`: add `"direct"` to department enum, update description to cover classification of all messages
- [x] 1.3 [BE] Change `tool_choice` from `"auto"` to `"required"` in `RouterPromptBuilder.build_response_create()`

## 2. Router Prompt — Always-Classify Pattern (DONE)

- [x] 2.1 [BE] Rewrite `decision_rules` in `router_prompt.yaml` to instruct model to always call `route_to_specialist` with `department="direct"` or a specialist department
- [x] 2.2 [BE] Add examples mapping common inputs to department + function call

## 3. Bridge — Two-Step Direct Flow (DONE)

- [x] 3.1 [BE] Add `_pending_direct_audio`, `_last_instructions`, `_pending_fn_call_id`, `_pending_fn_item_id` state fields to `OpenAIRealtimeEventBridge`
- [x] 3.2 [BE] In `response.function_call_arguments.done` handler: differentiate `Department.DIRECT` (set `_pending_direct_audio`) from specialist (emit `model_router_action`)
- [x] 3.3 [BE] Cache `instructions` from `response.create` payload in `_last_instructions` on `send_voice_start`
- [x] 3.4 [BE] In `response.done` handler: when `_pending_direct_audio`, send `function_call_output` acknowledgment then second `response.create` without tools
- [x] 3.5 [BE] Reset `_response_transcript_buffer` between two-step classification and audio follow-up

## 4. Bridge — Specialist response.done Fix (DONE)

- [x] 4.1 [BE] In `response.done` handler: when `_function_call_received` is True, do NOT emit `voice_generation_completed` — let the specialist's response.done handle it

## 5. Mock Specialist Tools (DONE)

- [x] 5.1 [BE] Create `backend/src/voice_runtime/specialist_tools.py` with mock tool functions: `specialist_sales`, `specialist_billing`, `specialist_support`, `specialist_retention`
- [x] 5.2 [BE] Each mock tool accepts `summary: str` and `history: list[dict]`, returns a `response.create` payload dict with specialist instructions, triage steps, conversation history, and language instruction
- [x] 5.3 [BE] Register all mock specialist tools in `ToolExecutor` at call creation time (in the call setup code that creates the Coordinator)

## 6. Coordinator — Delegate to Specialist Tools (DONE)

- [x] 6.1 [BE] In `_on_model_router_action`, pass `history` from `ConversationBuffer.format_messages()` to `tool_executor.execute()` args alongside `summary`
- [x] 6.2 [BE] Remove inline specialist prompt construction (department_labels, instructions_parts, specialist_prompt dict) from `_on_model_router_action`
- [x] 6.3 [BE] After tool result, use `tool_result.payload` directly as the `prompt` field in `RealtimeVoiceStart` instead of building a prompt inline
- [x] 6.4 [BE] Add fallback: if `tool_result.ok` is False, construct a generic apology `response.create` and emit it

## 7. Testing

- [x] 7.1 [TEST] Unit test: `parse_function_call_action` correctly parses `department="direct"`
- [x] 7.2 [TEST] Unit test: mock specialist tool returns valid `response.create` payload with history embedded
- [x] 7.3 [TEST] Unit test: Coordinator passes history to tool executor args
- [x] 7.4 [TEST] Manual test: direct response flow works (greeting → two-step → spoken reply)
- [x] 7.5 [TEST] Manual test: specialist flow works (billing request → tool → triage questions)
