---
name: "ai-specs: Handoff US"
description: Validate enriched draft and start OpenSpec change
category: Workflow
tags: [ai-specs, workflow, handoff]
---

Validate an enriched User Story draft and continue the delivery flow.

This command assumes an enriched canonical snapshot already exists in:
drafts/enriched/

It validates the snapshot, optionally confirms with the user, and then continues to /opsx:new.

---

## Steps

1. **Locate enriched snapshot**

   Look inside:
   drafts/enriched/

   If multiple snapshots exist:
   - Use AskUserQuestion to let the user select one.

   If none exist:
   - Inform the user and stop.

2. **Validate snapshot structure**

   Ensure the selected file:

   - Contains the YAML header:
     design-linked:
     scope:
     source:
     reference:

   - Is wrapped between:
     <!-- BEGIN_ENRICHED_USER_STORY -->
     ...
     <!-- END_ENRICHED_USER_STORY -->

   If validation fails:
   - Inform the user.
   - Do NOT continue.

3. **Confirm handoff**

   Use AskUserQuestion:

   Start OpenSpec change from this enriched snapshot?

   Options:
   - Yes, continue
   - Cancel

   If Cancel → stop.

4. **Update Notion Status to In Progress (MANDATORY)**

   If the snapshot contains a Notion reference URL:

   - Update the Notion page property Status to exactly:
     In Progress

   Rules:
   - Only update if property exists.
   - Do not invent status names.
   - If update fails, continue but report the error.

5. **Start OpenSpec change**

   Execute:
   /opsx:new

   Use the enriched snapshot as input.

6. **Archive snapshot locally**

   Move the used snapshot to:
   drafts/enriched/_archived/<snapshot>.md

   Create _archived folder if it does not exist.

---

## Guardrails

- Never modify the enriched snapshot content.
- Never regenerate enriched inside this command.
- Never rewrite canonical.
- Only validate and continue workflow.
- Status must move to In Progress before starting opsx:new.
