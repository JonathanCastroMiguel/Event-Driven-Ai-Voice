

# Notion Integration (MCP)

## Recommended Database Structure

To enable deterministic status transitions and automated enrichment,
use a Notion database named:

Product Backlog

### Required properties

- Title (title)
- Status (Status type)
- Type (Select: Feature, Bug, Improvement)
- Area (Select: Backend, Frontend, Infra)
- Priority (Select)
- Owner (Person)

### Recommended Status Workflow

- Draft
- To refine
- Pending refinement validation
- Ready
- In progress
- Done

The ai-specs: enrich-us command will:

- Append [original] and [enhanced] sections
- Automatically move status from:
  "To refine" → "Pending refinement validation"
  (if a Status property exists)

If no Status property exists, enrichment still works,
but status transitions will be skipped.


# Jira Integration (MCP)

## Recommended Project Configuration

To ensure deterministic enrichment and workflow transitions,
use a consistent Jira project structure.

### Recommended Issue Type

User stories processed by `ai-specs: enrich-us` should use:

- Issue Type: Story (preferred)
- Or Task (if your workflow is simplified)

Avoid using Epics as direct input to enrichment.

---

## Recommended Fields

Ensure the following fields are used consistently:

- Summary (clear, concise title)
- Description (problem statement and context)
- Acceptance Criteria (explicit and testable)
- Labels (optional but useful for domain context)
- Components (recommended)

Avoid mixing meeting notes or unrelated discussions inside the description.

---

## Recommended Workflow States

To enable automatic status transitions:

Include at least the following statuses in your workflow:

- Draft
- To refine
- Pending refinement validation
- Ready
- In progress
- Done

### Automatic Status Transition

When running `ai-specs: enrich-us`:

If the issue status is:
- "To refine"

It will automatically transition to:
- "Pending refinement validation"

If the workflow does not contain this status,
the transition step will be skipped safely.

---

## Best Practices

- Keep one story per ticket.
- Avoid multi-feature tickets.
- Do not mix bug + feature in the same issue.
- Keep acceptance criteria atomic and testable.
- Use structured formatting in description (headings, bullet lists).

---

## What Happens During Enrichment

The command will:

- Append the enhanced version below the original.
- Add sections:
  - [original]
  - [enhanced]
- Improve clarity, completeness, and implementation detail.
- Optionally move the issue to the next refinement state.


# Figma Integration (MCP)

## Purpose

Figma integration is used to:

- Retrieve UI structure
- Extract component names
- Identify design system constraints
- Align frontend standards with actual design tokens

Figma is not used for status transitions.

---

## Recommended Structure

For best results:

- Maintain a dedicated Design System file.
- Use consistent component naming.
- Avoid deeply nested component hierarchies.
- Clearly label variants and states.

---

## Recommended File Organization

- Design System (separate file)
- Product Screens (separate file)
- Experiments / Explorations (optional)

Avoid mixing production components with draft explorations.

---

## Naming Conventions

Use predictable naming patterns:

- Button / Primary
- Button / Secondary
- Input / Text
- Modal / Confirmation
- Page / Dashboard

This allows the AI to infer structure more accurately.

---

## Best Practices

- Use Auto Layout consistently.
- Use shared styles for typography.
- Use color styles instead of hardcoded colors.
- Avoid detached instances.

---

## What Happens During Enrichment

When Figma is connected, the system may:

- Inspect the referenced file.
- Extract relevant component structure.
- Suggest API or UI layer changes aligned with the design.
- Infer frontend architectural constraints.

Figma content is never modified automatically.