## Why

The current `router_prompt.yaml` has overlapping sections that make it impossible to configure routing dynamically via API. `decision_rules` mixes tool-calling mechanics with routing logic and edge-case behavior that duplicates `guardrails`. The `departments` section repeats what's already in `decision_rules`. The specialist tool binding (department → function) is hardcoded across multiple files (`ROUTE_TOOL_DEFINITION` enum, coordinator's `f"specialist_{department}"`, `register_specialist_tools`). This coupling prevents loading routing configuration from an API call without touching code.

## What Changes

- **Replace `router_prompt.yaml` with `router_prompt.json`** using the exact target API payload structure. The local JSON file is the same shape the API will deliver in the future — zero runtime changes needed when switching to API source. The config has 4 sections (system_mechanic is NOT in the JSON, it's a code constant):
  - `identity`: Tenant-configurable agent persona (warm, concise, telecom company).
  - `departments`: Structured department definitions with `description`, `triggers`, `fillers` (per-department filler messages), and `tool` (specialist endpoint config). Single source of truth for routing — replaces the current duplicated `decision_rules` + `departments` sections.
  - `guardrails`: Pure behavioral restrictions (no medical/legal/financial advice, stay calm). No routing logic.
  - `language_instruction`: Language matching rules.
- **Generate `ROUTE_TOOL_DEFINITION` dynamically** from the departments config instead of a hardcoded enum.
- **Replace static `Department` enum** with runtime-validated set from config keys.
- **Update `RouterPromptTemplate`** and `RouterPromptBuilder` to consume the JSON config and assemble the prompt from structured sections.
- **Two loading paths**: `load_router_prompt()` reads local JSON file, `load_router_prompt_from_dict()` accepts a dict directly. Both produce the same `RouterPromptConfig`.
- **Update coordinator** to resolve the specialist tool name from the department config (`dept.tool`) instead of `f"specialist_{department}"`.
- **Per-department fillers**: Each department defines a list of filler messages. The coordinator picks a random filler from the routed department's list instead of the hardcoded `"Un momento, por favor."`. Fillers are configured per-department so they match the specialist context (e.g., billing fillers reference invoices, support fillers reference technical help).
- **Remove overlap**: `decision_rules` edge cases (inappropriate language, out of scope) that duplicate `guardrails` are consolidated into `guardrails` only.

## Capabilities

### New Capabilities

_None — this restructures existing capabilities._

### Modified Capabilities

- `model-router`: Config changes from YAML with 5 flat text sections to a JSON file with the target API payload structure. `ROUTE_TOOL_DEFINITION` and `Department` enum become dynamic. `RouterPromptTemplate` and `RouterPromptBuilder` change to match.
- `coordinator`: Specialist tool name resolution changes from hardcoded `f"specialist_{department}"` to reading `tool` field from department config. Filler emission changes from hardcoded string to random selection from department's `fillers` list.

## Impact

- **`backend/router_registry/v1/router_prompt.json`** — new file, replaces `router_prompt.yaml` (deleted)
- **`backend/src/routing/model_router.py`** — `RouterPromptTemplate`, `RouterPromptBuilder`, `ROUTE_TOOL_DEFINITION`, `Department` enum, `load_router_prompt` all change
- **`backend/src/voice_runtime/coordinator.py`** — specialist tool name resolution (~line 687), filler selection (~line 670)
- **Tests** — `test_model_router.py`, `test_two_step_routing.py` need updating for new JSON structure and filler behavior
- **No API changes** — this is internal restructuring that enables future API-driven configuration
