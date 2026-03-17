## Why

The current `router_prompt.yaml` has overlapping sections that make it impossible to configure routing dynamically via API. `decision_rules` mixes tool-calling mechanics with routing logic and edge-case behavior that duplicates `guardrails`. The `departments` section repeats what's already in `decision_rules`. The specialist tool binding (department → function) is hardcoded across multiple files (`ROUTE_TOOL_DEFINITION` enum, coordinator's `f"specialist_{department}"`, `register_specialist_tools`). This coupling prevents loading routing configuration from an API call without touching code.

## What Changes

- **Restructure `router_prompt.yaml`** into 5 clearly separated layers:
  - `system_mechanic`: Fixed tool-calling mechanics (always call `route_to_specialist`, never vocalize function names). Never exposed via API.
  - `identity`: Tenant-configurable agent persona (warm, concise, telecom company).
  - `departments`: Structured department definitions with `description`, `triggers`, `fillers` (per-department filler messages), and `tool` (specialist endpoint config). Single source of truth for routing — replaces the current duplicated `decision_rules` + `departments` sections.
  - `guardrails`: Pure behavioral restrictions (no medical/legal/financial advice, stay calm). No routing logic.
  - `language_instruction`: Language matching rules.
- **Generate `ROUTE_TOOL_DEFINITION` dynamically** from the departments config instead of a hardcoded enum.
- **Generate `Department` enum dynamically** (or validate against YAML) instead of a static Python enum.
- **Update `RouterPromptTemplate`** and `RouterPromptBuilder` to consume the new structured YAML format and assemble the prompt from the new sections.
- **Update coordinator** to resolve the specialist tool name from the department config (`dept.tool`) instead of `f"specialist_{department}"`.
- **Per-department fillers**: Each department defines a list of filler messages. The coordinator picks a random filler from the routed department's list instead of the hardcoded `"Un momento, por favor."`. Fillers are configured per-department so they match the specialist context (e.g., billing fillers reference invoices, support fillers reference technical help).
- **Remove overlap**: `decision_rules` edge cases (inappropriate language, out of scope) that duplicate `guardrails` are consolidated into `guardrails` only.

## Capabilities

### New Capabilities

_None — this restructures existing capabilities._

### Modified Capabilities

- `model-router`: YAML structure changes from 5 flat text sections to structured format with typed departments. `ROUTE_TOOL_DEFINITION` and `Department` enum become dynamic. `RouterPromptTemplate` and `RouterPromptBuilder` change to match.
- `coordinator`: Specialist tool name resolution changes from hardcoded `f"specialist_{department}"` to reading `tool` field from department config. Filler emission changes from hardcoded string to random selection from department's `fillers` list.

## Impact

- **`backend/router_registry/v1/router_prompt.yaml`** — restructured format (breaking for anyone parsing the old format)
- **`backend/src/routing/model_router.py`** — `RouterPromptTemplate`, `RouterPromptBuilder`, `ROUTE_TOOL_DEFINITION`, `Department` enum, `load_router_prompt` all change
- **`backend/src/voice_runtime/coordinator.py`** — specialist tool name resolution (~line 687), filler selection (~line 670)
- **Tests** — `test_model_router.py`, `test_two_step_routing.py` need updating for new YAML structure and filler behavior
- **No API changes** — this is internal restructuring that enables future API-driven configuration
