# 🚀 BOOTSTRAP GUIDE

## Using This Repository as a Greenfield Template

This repository is designed to be reused as a **governed development
starter kit**.

It provides:

-   OpenSpecs workflow (`/opsx:*`)
-   AI governance layer (`/ai-specs:*`)
-   Deterministic standards system
-   Documentation enforcement
-   Spec-Driven Development (SDD)

This guide explains how to bootstrap a new project using this template.

------------------------------------------------------------------------

# 1. Create a New Project from This Template

Option A (Recommended): - Mark this repository as a GitHub Template. -
Click **"Use this template"** to create a new repo.

Option B: - Clone this repository. - Remove its `.git` folder. -
Initialize a new Git repository.

------------------------------------------------------------------------

# 2. Clean Project-Specific Content

Keep:

-   `.claude/`
-   `ai-specs/`
-   `openspec/`
-   `CLAUDE.md`
-   `.gitignore`
-   `README.md`
-   `BOOTSTRAP.md`

Remove (if present):

-   Old project source code
-   Previous domain-specific models
-   Old CI config (if not reusable)
-   Example APIs or dummy data

The governance and workflow system must remain intact.

# ⚠️ IMPORTANT — DO NOT RUN `openspec init`

This repository is **already initialized**.

Running:

```bash
openspec init
```

inside this project may overwrite:

Custom /opsx:* commands
Custom /ai-specs:* commands

The curated OpenSpec structure

If you do this, commands may stop working.

In this repository, NEVER run openspec init.

------------------------------------------------------------------------

# 3. Minimum Requirements (New Machine)

Install the following:

Git

Node.js (if OpenSpec is installed via npm/pnpm)

(Optional) Python, if required by your backend stack

VS Code

The Claude Code VS Code extension (Anthropic)

# 4. Setup Steps

Clone the repository:

git clone <YOUR_REPO>
cd <YOUR_REPO>

Run the bootstrap script:

bash scripts/bootstrap.sh

The script will:

Verify you are in the correct project root

Verify custom Claude commands exist

Check if OpenSpec CLI is installed

Warn if openspec init was executed accidentally

Provide corrective guidance if something is missing

# 5. First-Time Project Usage

This is the actual minimal workflow.

Some commands exist but are not required in every scenario.

# 6. Initialize Standards (MANDATORY)

If these files do not exist:

-   `ai-specs/specs/backend-standards.mdc`
-   `ai-specs/specs/frontend-standards.mdc`

Run:

```bash
/ai-specs:init-standards
```

You will be prompted for:

-   Backend language & framework
-   Architecture pattern
-   Database & ORM
-   API style (REST / GraphQL)
-   Testing stack
-   Frontend framework
-   Tooling & CI strategy

This generates deterministic, stack-specific standards.

Without this step, development is blocked by design.

------------------------------------------------------------------------


# 7. Create User Stories (If using Notion MCP)

```bash
/ai-specs:new-us
```

This command internally calls:

/ai-specs:enrich-us

to ensure the story follows SDD structure.

Then the system ask you for POMode or Dev:

# 8.1 Product Owner Mode (PO Mode)

If working in refinement mode:

Iterate on the draft

When ready for implementation:

```bash
/ai-specs:handoff-us
```

This validates and upgrades the story to implementation-ready 
status.

# OR

# 8.2 Development Mode (Dev Mode)

Once the User Story is implementation-ready:

```bash
/opsx:new
```

Then continue working on the change:

```bash
/opsx:continue
```

# 9. Apply (When the 4 Artifacts Are Ready)

When all required artifacts are completed:

```bash
/opsx:apply
```

This step includes:

- Implementation
- Validation
- Verify execution (quality gate)

# 10. Archive

When everything passes validation:

```bash
/opsx:archive
```

# 11. Diagram

![SDD Workflow](/docs/workflow-diagram.png)

Versión mermaid
```mermaid
flowchart TD
  A[Init Standards<br/>/ai-specs:init-standards] --> B{Using Notion MCP?}
  B -- Yes --> C[/ai-specs:new-us<br/>(calls enrich-us)/]
  B -- No --> D[Create US manually<br/>using .md in Draft folder]

  C --> E{PO Mode or Dev Mode?}
  D --> E

  E -- PO Mode --> F[Refine draft]
  F --> G[/ai-specs:handoff-us<br/>(implementation-ready)/]
  G --> H[/opsx:new/]

  E -- Dev Mode --> H[/opsx:new/]
  H --> I[/opsx:continue/]

  I --> J{Are 4 artifacts complete?}
  J -- No --> I
  J -- Yes --> K[/opsx:apply<br/>(includes verify)/]
  K --> L{Verify OK?}
  L -- No --> I
  L -- Yes --> M[/opsx:archive/]

```

# 12 Troubleshooting
Claude commands not visible

If /opsx:* or /ai-specs:* commands are not detected:

Make sure VS Code opened the project root (where .claude/ exists)

Ensure Workspace Trust is enabled

Restart VS Code

Confirm you are using Claude Code, not Copilot Chat

Someone ran openspec init

If commands stopped working after running openspec init:

Run:

bash scripts/bootstrap.sh

Follow the repair instructions provided by the script.

------------------------------------------------------------------------

# 13. Documentation Rules

All documentation lives under:

ai-specs/specs/

Templates live under:

ai-specs/specs/templates/

Templates define structure only. Never copy template example content
verbatim.

Documentation is enforced automatically during:

/opsx:archive

------------------------------------------------------------------------

# 14. Optional Hardening

For stricter governance, consider:

-   Enforcing non-empty standards validation
-   Adding CI validation for api-spec.yml changes
-   Requiring archive before merge
-   Disallowing direct commits to main

------------------------------------------------------------------------

# Final Principle

This repository is not a code scaffold.

It is a governed development system.

Standards first. Specs first. Code second.
