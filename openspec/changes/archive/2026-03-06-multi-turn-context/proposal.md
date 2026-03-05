## Why

Each turn is currently independent — the prompt sent to the voice agent contains only the base system prompt, policy instructions, and the single user utterance. There is no conversation history. If a caller says "tengo un problema con mi factura" and then "¿cuánto debo?", the second turn has zero context about the first. This breaks natural conversation flow and forces users to repeat themselves, degrading the call experience.

## What Changes

- Introduce a `ConversationBuffer` that accumulates turn summaries (user text + agent response type) within a single call, bounded by a configurable max-turns window
- Modify the Coordinator's prompt construction to inject conversation history between the system messages and the current user message
- Add a turn-history pruning strategy (sliding window with token budget) to prevent unbounded prompt growth
- Ensure barge-in and cancellation correctly handle partial turns (cancelled turns are excluded from history)

## Capabilities

### New Capabilities

- `conversation-buffer`: In-memory sliding-window buffer that tracks completed turns (user text, route taken, policy applied) per call, with configurable max entries and token budget

### Modified Capabilities

- `coordinator`: Prompt construction changes from single-turn `[system, policy, user]` to multi-turn `[system, policy, ...history, user]`. History injection, pruning on barge-in, and buffer lifecycle management

## Impact

- **Code**: `backend/src/voice_runtime/coordinator.py` (prompt construction), new `backend/src/voice_runtime/conversation_buffer.py`
- **Runtime state**: `CoordinatorRuntimeState` gains a reference to the conversation buffer
- **Configuration**: New config fields for `max_history_turns` and `max_history_tokens`
- **Tests**: New unit tests for buffer, updated coordinator tests for multi-turn prompts, updated E2E tests
- **No DB changes**: History is ephemeral (in-memory per call), not persisted
- **No API changes**: No new endpoints
