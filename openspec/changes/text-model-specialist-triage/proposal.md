## Why

Specialist agents (billing, sales, support, retention) currently receive triage instructions via a `response.create` payload, but the **Realtime voice model** interprets and generates audio from those instructions. The voice model consistently ignores the triage framework (ask a clarifying question before transferring) and instead transfers the customer immediately. This defeats the purpose of the multi-step triage flow.

The fix: use a **text model** (e.g., `gpt-4o`) to generate the specialist's response text, then pass that exact text to the Realtime model to vocalize. The text model follows structured prompts reliably. While the text model processes, the system plays a **filler message** (already implemented but needs wiring to this new flow) so the customer hears natural hold phrases instead of silence.

## What Changes

- **Specialist tools call a text model** instead of returning raw instructions. Each specialist tool (`specialist_billing`, etc.) will call `gpt-4o` (or configurable model) with the triage prompt + conversation history, receive a text response, and return that text as a literal vocalization instruction.
- **Filler messages play during text model call**. The coordinator already emits fillers in parallel with specialist tool execution. This flow is preserved — the only change is that the specialist tool now takes longer (text model latency ~500-1500ms) making the filler actually useful.
- **Specialist response is vocalized literally**. Instead of `response.create` with `instructions` (which the voice model interprets freely), the specialist tool returns the exact text to speak. The coordinator sends this as a direct vocalization to the Realtime API.

## Capabilities

### New Capabilities
- `text-model-specialist`: Text model integration for specialist triage responses. Covers the async HTTP call to a text model, prompt construction, response parsing, and error handling/fallback.

### Modified Capabilities
- `coordinator`: The specialist dispatch flow changes — instead of forwarding a `response.create` with instructions, the coordinator forwards a literal text vocalization from the text model result.

## Impact

- **Backend code**: `specialist_tools.py` (text model calls), `coordinator.py` (response handling), `config.py` (new model settings)
- **Dependencies**: `httpx` async client for text model API calls (already in project deps)
- **APIs**: No external API changes. Internal specialist tool interface changes from returning `response.create` dict to returning literal text.
- **Latency**: Adds ~500-1500ms for text model call, but this is masked by the filler message playing in parallel.
- **Cost**: Additional text model API calls per specialist routing (~1 call per routed turn).
