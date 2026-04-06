## Context

Specialist agents are currently hardcoded as Python functions in `specialist_tools.py`. Each function builds a triage prompt and calls a text model (`gpt-4o`) to generate a response. The `router_prompt.json` already has a `tool` object per agent with `type`, `name`, `url`, and `auth` — but only `type: "internal"` and `name` are used. The `url` and `auth` fields are `null`.

The coordinator dispatches specialist work through `ToolExecutor`, which looks up registered Python functions by name. This couples specialist logic to the codebase.

## Goals / Non-Goals

**Goals:**
- External specialist agents are callable via HTTP using the `url` from the JSON config
- Adding a new specialist agent requires only a JSON config change (no code, no redeployment)
- The `internal` type continues to work as-is (text-model triage) for agents without an external endpoint
- Fillers play during both HTTP and internal specialist calls
- Failed HTTP calls fall back gracefully (apology message)

**Non-Goals:**
- Streaming responses from external agents (batch is sufficient)
- WebSocket or gRPC agent protocols (HTTP POST only for MVP)
- Agent discovery or service registry (URLs are static in JSON)
- Changing the filler mechanism or the router prompt structure
- Frontend changes

## Decisions

### D1: HTTP contract for external agents

**Decision**: External agents receive a POST request with JSON body and return a plain text response.

**Request body:**
```json
{
  "department": "billing",
  "summary": "Customer requesting a refund",
  "history": [
    {"role": "user", "text": "Tengo un problema con mi factura"},
    {"role": "assistant", "text": "¡Hola! ¿Cómo te puedo ayudar hoy?"}
  ],
  "language": "es"
}
```

**Response**: Plain text (the triage response to vocalize). HTTP 200 with `Content-Type: text/plain` or JSON with a `text` field.

**Why**: Simple, stateless contract. The external agent is responsible for its own triage logic, prompt engineering, and model calls. The coordinator just sends context and gets text back.

### D2: Dispatch in coordinator, not ToolExecutor

**Decision**: The coordinator checks `tool.type` directly and dispatches accordingly, bypassing `ToolExecutor` for specialist routing entirely.

**Why**: `ToolExecutor` was designed for registered Python functions with caching and timeout wrappers. HTTP agent calls have their own timeout (httpx) and don't benefit from ToolExecutor's cache. Keeping dispatch in the coordinator is simpler and avoids coupling HTTP calls to the tool registry.

**Flow**:
1. `_on_model_router_action` receives department
2. Resolve `tool_config = router_prompt_builder.get_department_tool(department)`
3. If `tool_config.type == "http"`: call `_dispatch_http_agent(url, auth, summary, history)`
4. If `tool_config.type == "internal"`: call `_dispatch_internal_agent(department, summary, history)` (current text-model flow)
5. If `tool_config is None` (direct): skip specialist, follow direct response flow

### D3: Shared httpx client reused from specialist_tools

**Decision**: Reuse the existing `httpx.AsyncClient` from `specialist_tools.py` (created by `configure()`) for both internal text-model calls and external HTTP agent calls. Expose it via a module-level getter.

**Why**: Connection pooling, single lifecycle management, no new client needed.

### D4: Auth via Bearer token

**Decision**: If `tool.auth` is set in the JSON, it's sent as `Authorization: Bearer <auth>` header on the HTTP request to the external agent.

**Why**: Simple, standard auth mechanism. Sufficient for MVP. More complex auth (OAuth, API keys in custom headers) can be added later by extending `ToolConfig`.

### D5: `internal` type uses existing text-model flow

**Decision**: When `tool.type == "internal"`, the coordinator calls `_call_text_model` with the department's system prompt and triage framework — exactly as implemented in the `text-model-specialist-triage` change. The hardcoded `specialist_*` functions are removed but the system prompts and `_call_text_model` stay.

**Why**: `internal` is the built-in default. It doesn't require an external endpoint. The triage prompts are still hardcoded per department, but they're now just data (system prompt strings), not registered tool functions.

### D6: Language detection from conversation history

**Decision**: The coordinator extracts the customer's language from the last user message in the conversation history (or defaults to the session language) and passes it in the HTTP request body as `language`. This lets external agents respond in the correct language.

**Why**: External agents need to know the customer's language but don't have access to the Realtime session context.

## Risks / Trade-offs

- **[Latency]** External HTTP agents add network round-trip on top of their own processing time → **Mitigated** by fillers playing in parallel. Timeout set to `specialist_timeout_s` (default 5s).
- **[Availability]** External agent endpoint could be down → **Mitigated** by fallback to apology message. Logged as warning for monitoring.
- **[Security]** Agent URLs and auth tokens in JSON config → Acceptable for MVP. Secrets can be moved to env vars or secrets manager later. Auth tokens should not be committed to git.
- **[Contract drift]** External agents must conform to the request/response contract → Document the contract clearly. No versioning for MVP.
