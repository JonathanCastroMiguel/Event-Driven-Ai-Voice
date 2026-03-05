# 🚀 OpenSpecs SDD System

### Spec-Driven Development + AI Governance Layer

This repository implements a customized OpenSpecs workflow enhanced with
an AI governance layer.

It enforces:

-   Explicit technical standards
-   Deterministic documentation structure
-   Controlled change lifecycle
-   Spec‑Driven Development (SDD)
-   AI‑governed architectural discipline

------------------------------------------------------------------------

# 🧠 What Is This?

This is not just an OpenSpecs setup.

It is a governed development environment composed of:

-   OpenSpecs (workflow orchestration)
-   Custom Claude commands
-   Explicit backend & frontend standards
-   Documentation enforcement rules
-   Structured templates
-   Blocking policies for incomplete work

The goal is to eliminate architectural drift and documentation entropy.

------------------------------------------------------------------------

# 📐 Development Model: Spec‑Driven Development (SDD)

Specifications are the source of truth.\
Code is an implementation artifact.

The order of operations:

1.  Define or update specs
2.  Apply change
3.  Verify artifacts & tasks
4.  Update documentation
5.  Archive change

No direct coding outside this flow.

------------------------------------------------------------------------

# 🏗 Project Architecture

- `.claude/commands/opsx/` → OpenSpecs workflow commands
- `.claude/commands/ai-specs/` → Governance & standards commands
- `ai-specs/` → Specs, templates, standards, docs
- `openspec/` → OpenSpecs CLI workflow

openspec/ → OpenSpecs CLI workflow

------------------------------------------------------------------------

# 🔄 Command Domains

Commands are organized by namespace.

## 🔄 /opsx:\* --- OpenSpecs Workflow

Lifecycle management commands:

-   /opsx:new --- Start a new change
-   /opsx:ff --- Fast‑forward creation of artifacts
-   /opsx:apply --- Implement change artifacts
-   /opsx:verify --- Verify implementation vs artifacts
-   /opsx:sync --- Sync delta specs into main specs
-   /opsx:continue --- Continue experimental workflow
-   /opsx:archive --- Archive completed change
-   /opsx:bulk-archive --- Archive multiple changes
-   /opsx:explore --- Investigation mode (no implementation)
-   /opsx:onboard --- Guided onboarding through workflow

These commands manage the change lifecycle only.

------------------------------------------------------------------------

## 🧠 /ai-specs:\* --- Governance & Execution Layer

These commands manage standards, documentation, planning, and execution.

-   /ai-specs:init-standards\
    Generate backend and frontend standards from templates using your
    tech stack.

-   /ai-specs:update-docs\
    Enforce documentation-standards.mdc (update API spec, data model,
    development guide).

-   /ai-specs:new-us\  
    Create a new structured user story aligned with SDD standards.

-   /ai-specs:enrich-us\
    Improve and refine user stories/tickets for clarity and
    completeness.

-   /ai-specs:handoff-us\
    Prepare a validated user story for implementation (technical-ready state).

-   /ai-specs:plan-backend-ticket\
    Generate an implementation plan for backend tickets.

-   /ai-specs:plan-frontend-ticket\
    Generate an implementation plan for frontend tickets.

-   /ai-specs:commit\  
    Structured commit (and optional PR) workflow with governance checks.

-   /ai-specs:explain\
    Deep conceptual explanation mode.

-   /ai-specs:meta-prompt\
    Improve and structure prompts for better AI execution.

------------------------------------------------------------------------

# 📘 Standards

All authoritative standards live under:

ai-specs/specs/

Standards may initially be empty in greenfield setups.

If backend-standards.mdc or frontend-standards.mdc do not exist, run:

/ai-specs:init-standards

This generates deterministic, stack‑specific standards from templates.

------------------------------------------------------------------------

# 📄 Templates

Templates live under:

ai-specs/specs/templates/

Templates define structure only (headings and section order).\
They are never copied verbatim.

Templates prevent:

-   Documentation drift
-   Structural inconsistency
-   AI output randomness

------------------------------------------------------------------------

# ⚡ QuickStart (Greenfield Setup)

1.  Clone the repository

    git clone `<repo>`{=html} cd `<repo>`{=html}

2.  Initialize standards

    /ai-specs:init-standards

    Provide:

    -   Backend stack
    -   Database & ORM
    -   API style
    -   Testing stack
    -   Frontend stack
    -   Tooling & CI

3.  Start a change

    /opsx:new

Follow the lifecycle strictly.

------------------------------------------------------------------------

# 🔁 Enhanced Archive Flow

Archive includes:

1.  Artifact verification
2.  Task verification
3.  Spec sync validation
4.  Documentation update
5.  API blocking rule
6.  Archive execution

This ensures no undocumented API changes and no architectural drift.

------------------------------------------------------------------------

# 🎯 Final Principle

Standards first.\
Specs first.\
Code second.

This repository is a controlled development environment, not just a
project scaffold.
