## Context

The current routing uses `tool_choice: "auto"`, meaning the model can choose whether to call `route_to_specialist`. In practice, the model sometimes speaks about routing without calling the function, breaking specialist dispatch. Additionally, when the model does call the function, it speaks a filler simultaneously — but the Coordinator also has inline specialist prompt construction that doesn't belong there architecturally.

The code for this change is already implemented and deployed (uncommitted). This design documents the decisions behind what was built and the remaining work (mock specialist tools).

## Goals / Non-Goals

**Goals:**
- Guarantee every user message is classified via function call (no silent routing failures)
- Separate classification (call 1) from response generation (call 2) so each does one thing
- Move specialist prompt construction out of the Coordinator into specialist tools
- Prepare the tool interface for future LangGraph/LangChain sub-agents
- Keep latency impact minimal (the two-step adds one extra OpenAI round-trip only for direct responses)

**Non-Goals:**
- Implementing real sub-agents (LangGraph/LangChain) — that's a separate change
- Changing the frontend WebRTC pipeline
- Modifying the FSM state machine transitions
- Adding new departments or routing categories

## Decisions

### 1. `tool_choice: "required"` forces classification on every turn

**Choice:** Change `tool_choice` from `"auto"` to `"required"` in `RouterPromptBuilder.build_response_create()`.

**Why:** With `"auto"`, the model sometimes speaks about routing without calling the function (e.g., "Let me connect you to billing" without actually calling `route_to_specialist`). With `"required"`, the model MUST call the function — classification is guaranteed.

**Trade-off:** `tool_choice: "required"` suppresses audio output in the response. The model produces only a function call, no speech. This necessitates the two-step pattern.

**Alternatives considered:**
- Stronger prompt reinforcement with `"auto"` — tried, unreliable at ~85-90% compliance
- Post-hoc transcript parsing for routing keywords — fragile, adds latency

### 2. `Department.DIRECT` for self-handled messages

**Choice:** Add `"direct"` to the department enum and tool parameter. The model calls `route_to_specialist(department="direct", summary="...")` for greetings, small talk, guardrails, etc.

**Why:** With `tool_choice: "required"`, the model must always call a function. `"direct"` is the escape hatch for messages that don't need specialist routing. The Bridge differentiates `direct` from specialist departments to trigger different flows.

### 3. Two-step direct response: classify then speak

**Choice:** For `department="direct"`, the Bridge:
1. Sets `_pending_direct_audio = True` on function call received
2. On `response.done`, acknowledges the function call via `conversation.item.create` with `type: "function_call_output"`
3. Sends a second `response.create` WITHOUT tools (`modalities: ["text", "audio"]`) so the model generates the spoken reply

**Why:** OpenAI's Realtime API requires acknowledging a function call before the model can generate a new response. The second `response.create` omits tools so the model speaks freely without being forced into another function call loop.

**Latency impact:** One extra OpenAI round-trip (~50-150ms) for direct responses. Specialist responses are unaffected (they were already two-step via Coordinator tool execution).

### 4. Specialist `response.done` no longer emits `voice_generation_completed`

**Choice:** When `response.done` fires with `_function_call_received = True`, the Bridge does nothing (`pass`). The specialist's own `response.done` (from the second `response.create`) emits `voice_generation_completed` with the correct transcript.

**Why:** Previously, the router's `response.done` emitted `voice_generation_completed` with an empty or filler transcript, causing the Coordinator to store incorrect agent text. Now the specialist response is the one that completes the voice generation with the actual specialist transcript.

### 5. Mock specialist tools via ToolExecutor (pending implementation)

**Choice:** Register mock tools (`specialist_sales`, `specialist_billing`, `specialist_support`, `specialist_retention`) in the ToolExecutor. Each mock tool receives `summary` and `history` (conversation history), and returns a complete `response.create` payload with specialist instructions. The Coordinator forwards this payload to the voice agent without modification.

**Why:** This matches the architecture where the Coordinator orchestrates but doesn't build prompts. The tool interface is the same one that will be used for LangGraph/LangChain sub-agents — only the tool implementation changes.

**Tool interface:**
```python
async def specialist_retention(summary: str, history: list[dict]) -> dict:
    """Returns a response.create payload for the specialist."""
    return {
        "type": "response.create",
        "response": {
            "modalities": ["text", "audio"],
            "instructions": "... specialist prompt with triage steps ...",
            "temperature": 0.8,
        }
    }
```

**Coordinator change:** Remove inline prompt construction from `_on_model_router_action`. Instead, pass `summary` + `history` to the tool, receive the `response.create` payload, and forward it via `RealtimeVoiceStart`.

### 6. Router prompt rewrite for always-classify pattern

**Choice:** Rewrite `router_prompt.yaml` decision_rules to instruct the model to always call `route_to_specialist` with the appropriate department.

**Why:** The prompt must match the `tool_choice: "required"` constraint. The model needs clear instructions that every message results in a function call with either `"direct"` or a specialist department.

## Risks / Trade-offs

**[Risk] Extra latency for direct responses** → The two-step adds ~50-150ms for direct responses (greetings, small talk). Acceptable for a call center scenario where sub-second response is still good. Specialist responses are unaffected.

**[Risk] Function call acknowledgment timing** → The `function_call_output` must be sent before the second `response.create`. If the order is wrong, OpenAI rejects the response. The Bridge handles this sequentially in `response.done`.

**[Risk] Mock tools don't validate prompts** → The mock specialist tools return hardcoded prompt structures. If the prompt doesn't work well for triage, we'll need to iterate on the mock tool's instructions. This is by design — the tool is the place to iterate on specialist behavior.

**[Risk] History passing to tools** → Currently `_on_model_router_action` only passes `summary` to the tool. To support proper triage, the tool needs conversation history too. The `ToolExecutor.execute()` args need to include `history` from `ConversationBuffer.format_messages()`.
