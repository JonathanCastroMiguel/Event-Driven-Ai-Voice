## 1. [BE] Model Router — History in instructions

- [x] 1.1 Refactor `RouterPromptBuilder.build_response_create()` to embed history in `instructions` field instead of `response.input`
- [x] 1.2 Update Coordinator fallback prompt path to use instructions-based history (same pattern)
- [x] 1.3 Update router_prompt.yaml `language_instruction` to respond in the customer's language dynamically

## 2. [BE] Whisper Multilingual Support

- [x] 2.1 Remove `"language": "es"` from Whisper config in session creation (POST to OpenAI)
- [x] 2.2 Remove `"language": "es"` from Whisper config in session.update (WebSocket)

## 3. [BE] Coordinator Timing Instrumentation

- [x] 3.1 Add `turn_speech_started_ms` and `turn_audio_committed_ms` fields to CallSession state
- [x] 3.2 Add ms-level timing logs at `_on_speech_started`, `_on_audio_committed`, `_on_transcript_final`
- [x] 3.3 Add ms-level timing logs at `model_router_dispatched`, `_on_model_router_action`, `_on_voice_completed`
- [x] 3.4 Add FSM state transition logs (`fsm_transition idle→routing`, etc.)

## 4. [BE] Realtime Event Bridge Timing

- [x] 4.1 Add `_response_create_sent_ms` and `_response_created_ms` tracking fields
- [x] 4.2 Log `send_to_created_ms` on `response.created` event
- [x] 4.3 Log `created_to_done_ms` and `total_response_ms` on `response.done` event
- [x] 4.4 Include transcript in `voice_generation_completed` event payload
- [x] 4.5 Log `has_history` and `instructions_len` for dict prompts in `send_voice_start`

## 5. [BE] Conversation Buffer Refactor

- [x] 5.1 Create TurnEntry dataclass with `user_text` and `agent_text` fields
- [x] 5.2 Refactor ConversationBuffer to use TurnEntry-based storage
- [x] 5.3 Add `set_agent_text()` method for async agent transcript population
- [x] 5.4 Update `format_messages()` to include both user and assistant messages

## 6. [TEST] Unit Tests

- [x] 6.1 Update `test_build_with_history` to assert history in instructions (no `response.input`)
- [x] 6.2 Update `test_build_with_multi_turn_history` for instructions-based history
- [x] 6.3 Update `test_history_truncation_handled_by_buffer` for instructions-based history
- [x] 6.4 Update `test_second_turn_includes_history` in coordinator tests
- [x] 6.5 Update conversation buffer tests for TurnEntry model
