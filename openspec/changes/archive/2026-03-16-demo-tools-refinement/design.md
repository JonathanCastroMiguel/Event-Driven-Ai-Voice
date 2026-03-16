## Context

`specialist_tools.py` currently uses a shared `_build_specialist_payload()` function with a `DEPARTMENTS` dict mapping English names to Spanish translations (`"sales" → "ventas"`). All four specialists share identical triage instructions. In testing, this caused: (1) the model using "ventas" literally in English conversations, and (2) the sales specialist skipping triage because the generic prompt lacked domain-specific guidance for short summaries like "plan upgrade".

## Goals / Non-Goals

**Goals:**
- Each specialist gets its own prompt builder with department-specific triage examples.
- Department names appear only in English in prompt text; the model translates dynamically.
- Triage examples are suggestive, not prescriptive — the model adapts to the actual request.

**Non-Goals:**
- No changes to function signatures, `ToolExecutor` integration, or `Coordinator` flow.
- No changes to the `response.create` payload structure.
- No real sub-agent implementation — these remain mock tools.

## Decisions

### Decision 1: Individual prompt functions, shared helper for common sections

Replace `_build_specialist_payload` with four functions (`_build_sales_prompt`, `_build_billing_prompt`, `_build_support_prompt`, `_build_retention_prompt`). Keep a small shared helper `_format_history_block(history)` and `_wrap_response_create(instructions)` for the common parts (history formatting, payload wrapping).

**Rationale**: Avoids duplicating boilerplate (history formatting, payload structure) while giving each department full control over its instructions text. Alternatives: (a) fully inline everything — too much duplication; (b) template with department-specific sections injected — still constrains prompt structure.

### Decision 2: English-only department references in prompts

Remove the `DEPARTMENTS` dict entirely. Prompts reference departments only in English (e.g., "You are a sales specialist"). Add an explicit instruction: "Always translate the department name to match the customer's language when speaking to them."

**Rationale**: The model reliably translates department names when told to, but unreliably avoids using hardcoded translations it sees in the prompt.

### Decision 3: Triage examples as soft guidance

Each prompt includes 2-3 example clarifying questions specific to the department, framed as "Examples of things you might ask" rather than a rigid checklist. This gives the model enough context to ask relevant questions without forcing irrelevant ones.

**Rationale**: In testing, the model with zero examples jumped to transfer. With rigid checklists it would ask all questions verbatim regardless of context. Soft examples balance guidance with adaptability.

## Risks / Trade-offs

- [Risk] Longer per-department prompts increase token usage slightly → Acceptable; these are short prompts (~200 tokens each) and execute once per specialist turn.
- [Risk] Model may still occasionally skip triage for very clear requests → Acceptable for demo; the examples make this much less likely.
