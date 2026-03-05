---
name: "OPSX: Continue"
description: Continue working on a change - create the next artifact (Experimental). Uses scope/design metadata (backend/frontend/design-linked) when present to generate deterministic tasks.
category: Workflow
tags: [workflow, artifacts, experimental]
---

Continue working on a change by creating the next artifact.

**Input**: Optionally specify a change name after `/opsx:continue` (e.g., `/opsx:continue add-auth`). If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

---

## Steps

### 1. If no change name provided, prompt for selection

Run `openspec list --json` to get available changes sorted by most recently modified. Then use the **AskUserQuestion tool** to let the user select which change to work on.

Present the top 3-4 most recently modified changes as options, showing:
- Change name
- Schema (from `schema` field if present, otherwise "spec-driven")
- Status (e.g., "0/5 tasks", "complete", "no tasks")
- How recently it was modified (from `lastModified` field)

Mark the most recently modified change as "(Recommended)".

**IMPORTANT**: Do NOT guess or auto-select a change. Always let the user choose.

---

### 2. Check current status

```bash
openspec status --change "<name>" --json
```

Parse the JSON to understand current state. The response includes:
- `schemaName`: The workflow schema being used (e.g., "spec-driven")
- `artifacts`: Array of artifacts with their status ("done", "ready", "blocked")
- `isComplete`: Boolean indicating if all artifacts are complete

---

### 3. If all artifacts are complete

If `isComplete: true`:
- Congratulate the user
- Show final status including the schema used
- Suggest: "All artifacts created! You can now implement this change with `/opsx:apply` or archive it with `/opsx:archive`."
- STOP

---

### 4. If artifacts are ready to create

If status shows artifacts with `status: "ready"`:

1) Pick the FIRST artifact with `status: "ready"` from the status output.

2) Get its instructions:

```bash
openspec instructions <artifact-id> --change "<name>" --json
```

Parse the JSON. Key fields:
- `context`: Project background (constraints for you - do NOT include in output)
- `rules`: Artifact-specific rules (constraints for you - do NOT include in output)
- `template`: The structure to use for your output file
- `instruction`: Schema-specific guidance
- `outputPath`: Where to write the artifact
- `dependencies`: Completed artifacts to read for context

3) Read any completed dependency files for context.

4) Extract scope/design metadata (best-effort)

#### 4.0 Enriched Section Extraction (ENTERPRISE HARDENING)

Before scanning for metadata/design references, attempt to extract ONLY the enriched section.
If the context contains the markers:

<!-- BEGIN_ENRICHED_USER_STORY -->
...
<!-- END_ENRICHED_USER_STORY -->

Then:
- Restrict ALL metadata parsing and design reference parsing to the text between those markers.
- Ignore any "Base User Story" content outside the markers.

If markers are missing:
- Fall back to scanning the full context (best-effort).


Scan the dependency artifacts (and any available context files) for:

- `design-linked: true|false`
- A `scope:` block containing:
  - `backend: true|false`
  - `frontend: true|false`
- A `## Design References` section containing Figma node URLs (node-id)

Initialize defaults:
- scope.backend = true
- scope.frontend = true
- designLinked = false

Rules:
- If scope is found, use it as truth.
- If scope is not found, keep defaults (both true) unless the user explicitly says otherwise.
- If design-linked is found, use it as truth.
- If design-linked is not found but `## Design References` or any Figma URL is present, set designLinked = true.

You MUST NOT invent Figma node-ids. If designLinked is true and no node-id URLs exist, note it and keep going (tasks can still be created, but apply may later ask for node-id).


#### 4.1 Metadata Tolerance (MANDATORY)

Downstream commands prefer strict metadata blocks, but continue MUST be resilient.
In addition to strict parsing, also detect:

1) Inline metadata lines, e.g.:
   - `design-linked: true | source: Notion | scope: FE + BE`
   Parse rules:
   - designLinked = value after `design-linked:`
   - If `scope:` text contains `FE` => scope.frontend = true
   - If `scope:` text contains `BE` => scope.backend = true

2) Alternate scope phrases anywhere:
   - `scope: FE + BE`, `scope: BE`, `scope: FE`, `scope: frontend`, `scope: backend`

If strict metadata exists, it ALWAYS wins over tolerant parsing.

#### 4.2 Design Reference Tolerance (MANDATORY)

Prefer `## Design References` + `Referenced Nodes:` with full URLs.
If missing, attempt a safe reconstruction WITHOUT inventing node-ids:

Inputs you may use:
- Any `Figma File:` URL, or any `https://www.figma.com/design/...` URL in context
- Any node tokens found in text like:
  - `(1:549)`, `(1-549)`, `node-id=1:549`, `node-id=1-549`
  - Lines like: `main (1:549): ...`

Reconstruction rules:
- Extract a base Figma design URL (the first `https://www.figma.com/design/<FILEKEY>/...` you see).
- For each node token:
  - Normalize `1-549` -> `1:549`
  - URL-encode `:` as `%3A` when building `node-id` query values
  - Construct full node URL: `<base-figma-url>?node-id=<ENCODED>`
- Do NOT guess FILEKEY or node tokens. Only transform what exists.

If designLinked == true and you still have zero node URLs after reconstruction:
- Add a visible note in tasks: "Missing Figma node-id URLs; /opsx:apply will request them."

---

### 5. Create the artifact file

- Use `template` as the structure - fill in its sections.
- Apply `context` and `rules` as constraints when writing - but do NOT copy them into the file.
- Write to the output path specified in instructions.

STOP after creating ONE artifact.

---

## Artifact Creation Guidelines (spec-driven)

These are additive guidelines; always follow the CLI `instruction` first.

### A) proposal.md

- Use the template structure.
- In the "Capabilities" section, keep capabilities aligned with scope:
  - If scope.backend == true: include backend capability(ies) (e.g., API, persistence, domain logic)
  - If scope.frontend == true: include frontend capability(ies) (e.g., views, UI components)
  - Do not include capabilities outside the declared scope.
- If designLinked == true and scope.frontend == true:
  - Add a short note that UI must follow Figma and that node-id links are referenced in `Design References`.

### B) specs/*

- Create one spec per capability from proposal.
- Keep each spec within scope (backend vs frontend).
- If scope.frontend == true and designLinked == true:
  - Include a brief "Design References" note pointing to the same node-id links (do not duplicate structural extraction).

### C) design.md

- Document technical decisions.
- If scope.frontend == true and designLinked == true:
  - Include a brief "Live Design Mode" note: implementation must consult Figma MCP at apply time.
- If scope.backend == true:
  - Include data model/persistence decisions and API contracts.

### D) tasks.md (MOST IMPORTANT for determinism)

When generating tasks, ALWAYS tag each task with a prefix:

- `[BE]` for backend tasks
- `[FE]` for frontend tasks
- `[TEST]` for tests (unit/component/integration)
- `[E2E]` for end-to-end tests (if project standards require it)

Rules:
- Generate tasks grouped by scope in this order:
  1) Backend (only if scope.backend == true)
  2) Frontend (only if scope.frontend == true)
  3) Tests (governed by project standards; include as appropriate)
  4) E2E (governed by project standards; include as appropriate)

- If scope.backend == false: DO NOT generate any `[BE]` tasks.
- If scope.frontend == false: DO NOT generate any `[FE]` tasks.
- If designLinked == true and scope.frontend == true:
  - The FIRST `[FE]` task should be a "Design sync" task referencing Figma nodes, e.g.:
    - `[FE] Sync layout/components from Figma nodes (node-id links)`
  - Subsequent FE tasks should reference that the UI must match Figma and will be implemented using Live Design Mode in `/opsx:apply`.

- Keep tasks small and checkable (1–4 hours each ideally).
- Avoid mega-tasks like "Build everything". Split by deliverable slices.

---

### 6. After creating an artifact, show progress

```bash
openspec status --change "<name>"
```

Show:
- Which artifact was created
- Schema workflow being used
- Current progress (N/M complete)
- What artifacts are now unlocked
- Prompt: "Run `/opsx:continue` to create the next artifact"

---

## Guardrails

- Create ONE artifact per invocation
- Always read dependency artifacts before creating a new one
- Never skip artifacts or create out of order
- If context is unclear, ask the user before creating
- Verify the artifact file exists after writing before marking progress
- Use the schema's artifact sequence, don't assume specific artifact names
- `context` and `rules` are constraints for YOU, not content for the file
  - Do NOT copy `<context>`, `<rules>`, `<project_context>` blocks into the artifact
  - These guide what you write, but should never appear in the output
