## Why

The original routing design used `tool_choice: "auto"`, which meant the model could choose not to call `route_to_specialist` — leading to unreliable classification and missed specialist routing. By switching to `tool_choice: "required"`, the model always calls the function, but this suppresses audio output in the first response. A two-step pattern is needed: the first response classifies (function call only), the second response speaks (audio). This also prepares the architecture for specialist tools that will become LangGraph/LangChain sub-agents.

## What Changes

- Router prompt rewritten: model ALWAYS calls `route_to_specialist` with `department="direct"` for self-handled messages or a specialist department for routing
- `tool_choice` changed from `"auto"` to `"required"` in `RouterPromptBuilder`
- `Department.DIRECT` added to the routing enum
- Bridge implements two-step direct response: first response produces function call only (no audio), bridge acknowledges the function call via `function_call_output`, then sends a second `response.create` without tools so the model speaks
- Bridge fix for specialist flow: `response.done` with `function_call_received=True` no longer emits `voice_generation_completed` — the specialist's own `response.done` handles it with the correct transcript
- Coordinator specialist prompt construction to be replaced by mock specialist tools (preparing for LangGraph sub-agents)

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `model-router`: `Department.DIRECT` added, `tool_choice` changed to `"required"`, tool description updated to cover classification of all messages
- `realtime-event-bridge`: Two-step direct response flow (fn_ack + second `response.create`), specialist `response.done` handling changed
- `router-registry`: Router prompt rewritten for always-classify pattern
- `coordinator`: Specialist prompt construction removed from inline code, delegated to specialist mock tools via `ToolExecutor`
- `tool-executor`: Mock specialist tools registered for each department (sales, billing, support, retention)

## Impact

- **Backend routing** (`model_router.py`): New enum value, tool definition change, `tool_choice` change
- **Backend bridge** (`realtime_event_bridge.py`): New state flags (`_pending_direct_audio`, `_pending_fn_call_id`), two-step flow logic, specialist response.done fix
- **Backend coordinator** (`coordinator.py`): Specialist prompt inline construction to be removed, replaced by tool result forwarding
- **Backend router registry** (`router_prompt.yaml`): Prompt rewritten
- **No frontend changes**
- **No API changes**
