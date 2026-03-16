## Why

The current specialist tools share a single prompt template (`_build_specialist_payload`) with hardcoded Spanish department labels (e.g., `"ventas"`, `"facturación"`). This causes two problems observed in production testing:

1. **Language leakage**: The model sees `"ventas"` in the prompt and uses it verbatim in English conversations instead of translating dynamically.
2. **Weak triage behavior**: The generic triage instructions lack department-specific context, causing the model to skip clarifying questions and jump straight to transfer (observed with sales — "plan upgrade" was deemed sufficient without asking details).

Splitting each specialist into its own prompt with tailored triage examples will improve demo quality without changing any runtime architecture.

## What Changes

- Remove the shared `_build_specialist_payload` function and `DEPARTMENTS` dict with hardcoded Spanish labels.
- Create individual prompt builders per specialist (`sales`, `billing`, `support`, `retention`), each with:
  - Department-specific triage examples (2-3 per department) to guide the model on what clarifying questions to ask.
  - Dynamic language handling — department names referenced only in English in the prompt; the model translates based on conversation language.
- Keep the same function signatures (`summary: str`, `history: list`) and `response.create` payload structure — no changes to ToolExecutor integration or Coordinator.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `tool-executor`: Update the "Mock specialist tool interface" requirement to reflect per-department prompts with tailored triage examples instead of a shared template. Department names must not be hardcoded in non-English languages.

## Impact

- **Code**: `backend/src/voice_runtime/specialist_tools.py` — rewrite prompt construction per department.
- **Tests**: Update existing specialist tool tests to verify per-department prompt differences and absence of hardcoded translations.
- **APIs**: No API changes.
- **Dependencies**: None.
