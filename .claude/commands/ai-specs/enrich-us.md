---
name: "ai-specs: enrich-us"
description: Enrich a Base User Story into a deterministic, machine-parseable Enriched User Story and persist a canonical snapshot for handoff.
category: Command
tags: [ai-specs, enrich, user-story, snapshot, figma]
---

# ai-specs:enrich-us (Canonical Snapshot First)

You take a **Base User Story** as input and produce an **Enriched User Story**.

This command is the source of truth for the enriched content used by OpenSpecs.
Notion is *documentation only* and MUST be updated using the exact saved snapshot (handled by `ai-specs:new-us`).

## Core Output Contract (MANDATORY)

Your output MAY include the Base User Story for traceability, but you MUST also output a canonical enriched section wrapped with these **exact** markers:

<!-- BEGIN_ENRICHED_USER_STORY -->
# Enriched User Story

design-linked: <true|false>
scope:
  backend: <true|false>
  frontend: <true|false>
source: <Notion|Jira|Manual>
reference: <url-or-id>

... enriched content ...

<!-- END_ENRICHED_USER_STORY -->

Rules:
- `# Enriched User Story` MUST be an H1 immediately after the BEGIN marker.
- Booleans MUST be lowercase `true|false`.
- The YAML block MUST be valid (2-space indentation).
- Do NOT use brackets in headings (NO `## [Enriched User Story]`).

## Design URL Preservation (MANDATORY)

If `design-linked: true` AND the Base User Story contains any Figma URLs with `node-id=...`,
then the canonical enriched section MUST include:

## Design References

Figma File:
<figma file url>

Referenced Nodes:
- <FULL figma node url containing node-id=...>
- ...

IMPORTANT:
- Copy node URLs verbatim (do NOT replace with "Node 1:3" text).
- Do NOT omit, shorten, re-encode, or "pretty print" URLs.

If `design-linked: true` but there are zero `node-id=` URLs in the Base User Story, ask the user for at least one node URL.

## Persist Canonical Snapshot (MANDATORY)

After you have produced the canonical enriched section:

1) Create slug from the feature title (kebab-case).
2) Create timestamp: YYYYMMDD-HHMM.
3) Save ONLY the canonical enriched section (from `<!-- BEGIN... -->` to `<!-- END... -->`, inclusive) to:

drafts/enriched/<slug>-<timestamp>.md

No Base User Story. No formatting transformations.

## Notion Update

DO NOT update Notion in this command.
Notion MUST be updated by `ai-specs:new-us` by copying the saved draft file verbatim into a Notion code block.
