# Tasks: multi-turn-context

scope: BE
design-linked: false

---

## Backend

### 1. ConversationBuffer core

- [x] 1.1 [BE] Create `TurnEntry` frozen dataclass in `backend/src/voice_runtime/conversation_buffer.py` with fields: `seq`, `user_text`, `route_a_label`, `policy_key`, `specialist`
- [x] 1.2 [BE] Create `ConversationBuffer` class with `__init__(max_turns, max_chars)` and empty entries list
- [x] 1.3 [BE] Implement `append(entry)` with sliding window pruning (drop oldest when `max_turns` exceeded)
- [x] 1.4 [BE] Implement character budget pruning in `append()` — drop oldest entries until total `user_text` chars fits within `max_chars`
- [x] 1.5 [BE] Handle edge case: single entry exceeding entire char budget (clear buffer, store entry as-is)
- [x] 1.6 [BE] Implement `format_messages()` returning `list[dict[str, str]]` with alternating user/assistant messages
- [x] 1.7 [BE] Implement assistant message format: `[{policy_key}] Guided response` for guided, `[{route_a_label}] Specialist: {specialist}` for specialist actions
- [x] 1.8 [BE] Add `entries` property (read-only) and `__len__` for buffer inspection

### 2. Configuration

- [x] 2.1 [BE] Add `max_history_turns: int = 10` and `max_history_chars: int = 2000` to `Settings` in `backend/src/config.py`

### 3. Coordinator integration

- [x] 3.1 [BE] Add `ConversationBuffer` as instance attribute on `Coordinator.__init__()`, created with settings values
- [x] 3.2 [BE] Modify `_on_request_guided_response()` to inject `buffer.format_messages()` between system messages and current user message in the prompt list
- [x] 3.3 [BE] Modify `_on_request_agent_action()` to inject `buffer.format_messages()` between system messages and current user content
- [x] 3.4 [BE] Append `TurnEntry` to buffer after successful `RealtimeVoiceStart` emission in `_on_request_guided_response()`
- [x] 3.5 [BE] Append `TurnEntry` to buffer after successful `RealtimeVoiceStart` emission in `_on_request_agent_action()`
- [x] 3.6 [BE] Verify cancelled turns are NOT appended (barge-in path returns before voice start, so no append happens)

---

## Tests

### 4. ConversationBuffer unit tests

- [x] 4.1 [TEST] Test empty buffer returns empty `format_messages()`
- [x] 4.2 [TEST] Test append and retrieve single entry
- [x] 4.3 [TEST] Test sliding window: append beyond `max_turns` drops oldest
- [x] 4.4 [TEST] Test character budget: append entry that pushes over `max_chars` drops oldest entries
- [x] 4.5 [TEST] Test single entry exceeding entire budget: clears buffer, stores entry
- [x] 4.6 [TEST] Test `format_messages()` produces correct alternating user/assistant structure
- [x] 4.7 [TEST] Test assistant message format for guided response (policy_key set, specialist None)
- [x] 4.8 [TEST] Test assistant message format for specialist action (specialist set)
- [x] 4.9 [TEST] Test combined max_turns + max_chars pruning (both limits active)

### 5. Coordinator unit tests (updated)

- [x] 5.1 [TEST] Test first turn (empty buffer) produces same prompt as before: `[system, policy, user]`
- [x] 5.2 [TEST] Test second turn includes history from buffer: `[system, policy, history..., user]`
- [x] 5.3 [TEST] Test barge-in interrupted turn is NOT in buffer (cancelled before voice start)
- [x] 5.4 [TEST] Test three consecutive turns accumulate correct history
- [x] 5.5 [TEST] Test buffer respects `max_history_turns` setting from config

### 6. E2E tests (updated)

- [x] 6.1 [E2E] Test multi-turn conversation: two turns, second prompt contains first turn's history
- [x] 6.2 [E2E] Test barge-in + new turn: cancelled turn absent from history, new turn prompt is clean
- [x] 6.3 [E2E] Test three turns with history accumulation and correct prompt structure
