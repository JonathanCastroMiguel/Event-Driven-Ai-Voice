## Why

Specialist agent logic (billing, sales, support, retention) is hardcoded in `specialist_tools.py` — each department has its own Python function with a baked-in system prompt and triage framework. Adding, modifying, or replacing a specialist requires code changes and redeployment. The `router_prompt.json` already defines per-agent `tool` config with `type`, `name`, `url`, and `auth` fields, but `url` is unused (`null`). The goal is to make specialist agents fully dynamic: the JSON config points to an external agent endpoint (HTTP), and the coordinator calls it at runtime. No code changes needed to add or swap specialists.

## What Changes

- **External agent dispatch via HTTP**. When `tool.type == "http"` and `tool.url` is set in the JSON, the coordinator calls that URL with the customer summary, conversation history, and department context. The response text is vocalized literally (same "say exactly" flow as the text-model-specialist change).
- **Remove hardcoded specialist functions**. The four `specialist_*` functions and their baked-in system prompts are removed from `specialist_tools.py`. The `register_specialist_tools` function is also removed.
- **`internal` type preserved as fallback**. When `tool.type == "internal"`, the existing text-model call with the triage framework is used (current behavior). This serves as a built-in default for agents that don't have an external endpoint yet.
- **Agent config schema extended**. The `ToolConfig` model adds validation for `type: "http"` requiring a non-null `url`. The `auth` field supports a bearer token for authenticated endpoints.
- **Coordinator dispatch unified**. Instead of always calling the `ToolExecutor` (which looks up registered Python functions), the coordinator checks `tool.type` from the JSON config: `"http"` dispatches via `httpx`, `"internal"` uses the existing text-model flow. Fillers play in parallel regardless of type.

## Capabilities

### New Capabilities
- `http-agent-dispatch`: HTTP client for calling external specialist agent endpoints. Covers request/response contract, timeout handling, auth header injection, and error fallback.

### Modified Capabilities
- `coordinator`: Specialist dispatch changes from always using `ToolExecutor` to checking `tool.type` and dispatching accordingly (`http` → HTTP call, `internal` → text-model call).
- `tool-executor`: Specialist tools are no longer registered as internal tools. The `ToolExecutor` is simplified — specialist routing bypasses it entirely.
- `model-router`: `ToolConfig` schema validation updated — `type: "http"` requires `url` to be non-null.

## Impact

- **Backend code**: `specialist_tools.py` (remove hardcoded functions, keep `_call_text_model` and triage prompts for `internal` type), `coordinator.py` (dispatch logic), `model_router.py` (ToolConfig validation), `main.py` (remove `register_specialist_tools` call)
- **Config**: `router_prompt.json` — agents can now set `"type": "http"` with a `url` to point to an external agent
- **Dependencies**: No new dependencies — `httpx` already in use
- **APIs**: New HTTP contract for external agents (POST with JSON body, returns text response)
- **Breaking**: `register_specialist_tools` is removed. Any code calling it must be updated.
