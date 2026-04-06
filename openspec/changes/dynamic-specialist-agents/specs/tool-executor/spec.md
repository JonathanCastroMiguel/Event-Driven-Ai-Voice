## REMOVED Requirements

### Requirement: Mock specialist tools registration
**Reason**: Specialist tools are no longer registered as internal Python functions. Specialist dispatch is handled directly by the Coordinator based on `tool.type` from the JSON config (`http` or `internal`). The `register_specialist_tools` function and individual `specialist_*` tool functions are removed.
**Migration**: Remove the `register_specialist_tools()` call from `main.py`. The `ToolExecutor` is no longer involved in specialist routing. It remains available for non-specialist tools (if any are added in the future).

### Requirement: Mock specialist tool interface
**Reason**: The per-department specialist tool functions (`specialist_billing`, `specialist_sales`, etc.) are removed. Their triage prompts are preserved as data (system prompt strings) for the `internal` type flow, but they are no longer registered tools.
**Migration**: The internal triage flow uses `_call_text_model` directly with department system prompts. No tool registration needed.
