---
name: "ai-specs: new-us"
description: Start from Jira, Notion, or manual input. Enrich the user story, persist a canonical snapshot, optionally update Notion, and optionally create an OpenSpecs change.
category: Command
tags: [ai-specs, opsx, enrich, mcp]
---

# ai-specs:new-us (Draft-first, Deterministic Handoff)

Create a new User Story from Jira, Notion, or manual input.
Normalize it into a **Base User Story**.
Run `ai-specs:enrich-us` to generate a **canonical** Enriched User Story and save it to `drafts/enriched/...`.

**Priority order**
1) The saved draft file is the single source of truth (used for opsx:new and for Notion documentation).
2) Notion is updated by copying the draft verbatim (no rewriting).

---

## Steps

### 0. Detect available MCP integrations
Determine which integrations are authenticated:
- Atlassian (Jira)
- Notion

Rules:
- Only offer sources that are authenticated.
- If none are authenticated, default to Manual input.

---

### 1. Choose input source
Ask the user whether to start from Jira, Notion, or Manual.

---

### 2. Collect and normalize into Base User Story
Retrieve the relevant content for the chosen source.

---

### 3. Normalize into required format
Produce exactly one markdown block:

# Base User Story
Source: <Jira|Notion|Manual>
Reference: <issue key/url or notion url/id or "N/A">

## Title
<short title>

## Problem / Context
<what is happening and why it matters>

## Desired Outcome
<what success looks like>

## Acceptance Criteria (raw)
- ...

#### Design References

Figma File: (URLs)

Node(s): 
- (URL)
- ...

## Constraints / Notes
- ...

---

### 4. Enrich the User Story (creates draft snapshot)
Execute:

ai-specs:enrich-us

Input:
The Base User Story markdown block.

Rules:
- The output MUST include a canonical enriched section wrapped in BEGIN/END markers.
- The command MUST save the canonical enriched section to:
  drafts/enriched/<slug>-<timestamp>.md
- Capture the printed path from the enrich step:
  "Saved enriched draft: drafts/enriched/<slug>-<timestamp>.md"

IMPORTANT:
- After `ai-specs:enrich-us` completes, DO NOT stop or “return control”.
- Continue immediately to Step 5 (Notion update) in the same run.

---

### 5. Update Notion (CANONICAL ONLY, VERBATIM)

If the source is Notion OR a Notion reference exists, update the Notion page as documentation.

Rules (MANDATORY):
- Read the saved draft file from Step 4.
- ALWAYS append blocks to the end of the page using the Notion API "append block children" style operation (i.e., append new blocks as children at the end of the page).
- NEVER use pattern matching, anchor matching, content replacement, or full-page replace operations (including any "replace_content" fallback).
- Append ONLY:
  1) A heading block with the exact text: `ENRICHED (CANONICAL — DO NOT EDIT)`
  2) A single Notion CODE BLOCK whose content is EXACTLY the draft file contents (verbatim).
- DO NOT rewrite, summarize, or reformat the draft content.
- The Notion code block MUST match the draft file 1:1.

If Notion is not available, skip this step.

Status update (MANDATORY):
- After appending the canonical code block, update the Notion page property **Status** to exactly:
  `Pending refinement validation`

Rules:
- Only do this if a Notion page reference exists and the property is present on the page/database.
- Do not invent other status names.

---

### 6. Decide Next Action
Ask the user:

- Stop here (PO mode). Use the saved draft for handoff later.
- Continue and create an OpenSpecs change (run opsx:new)

Default to Stop here if unclear.

If stopping:
- Print the saved draft path and recommend:
  /ai-specs:handoff-us <slug>-<timestamp>

---

### 7. Start OpenSpecs Change (Delivery Mode)

Status update (MANDATORY):
- Immediately BEFORE running `opsx:new`, update the Notion page property **Status** to exactly:
  `In Progress`

Rules:
- Only do this if a Notion page reference exists and the property is present.

If continuing, execute:

opsx:new

Input:
The FULL CONTENTS of the saved draft file (from Step 4), verbatim.

Rules:
- Do not modify the draft content before passing it.
- Follow opsx:new instructions exactly.

---

### 8. Report
Display:
- Selected source
- Draft path saved
- Whether Notion was updated (and that it was copied verbatim from draft)
- Whether an OpenSpecs change was created
- Next recommended action
