---
description: This document contains all development rules and guidelines for this project, applicable to Claude.
alwaysApply: true
---

## 1. Core Principles

- **Small tasks, one at a time**: Always work in baby steps, one at a time. Never go forward more than one step.
- **Test-Driven Development**: Start with failing tests for any new functionality (TDD), according to the task details.
- **Type Safety**: All code must be fully typed.
- **Clear Naming**: Use clear, descriptive names for all variables and functions.
- **Incremental Changes**: Prefer incremental, focused changes over large, complex modifications.
- **Question Assumptions**: Always question assumptions and inferences.
- **Pattern Detection**: Detect and highlight repeated code patterns.

## 2. Language Standards

- **English Only**: All technical artifacts must always use English, including:
    - Code (variables, functions, classes, comments, error messages, log messages)
    - Documentation (README, guides, API docs)
    - Tickets (titles, descriptions, comments)
    - Data schemas and database names
    - Configuration files and scripts
    - Git commit messages
    - Test names and descriptions

## 3. Authoritative Standards Location

All project standards and documentation live under:

`ai-specs/specs/`

These files are the single source of truth:

- `ai-specs/specs/backend-standards.mdc`
- `ai-specs/specs/frontend-standards.mdc`
- `ai-specs/specs/documentation-standards.mdc`
- `ai-specs/specs/data-model.md`
- `ai-specs/specs/api-spec.yml`
- `ai-specs/specs/development_guide.md`

Templates are located under:

`ai-specs/specs/templates/`

Templates define STRUCTURE ONLY (headings and section order).
Never copy template example content verbatim.

## 4. Missing Standards Policy (Blocking)

If any required standards file does not exist (for example:
`ai-specs/specs/backend-standards.mdc` or `ai-specs/specs/frontend-standards.mdc`),

STOP immediately. Do not continue implementation.

Standards must contain stack-specific content. If a standards file is missing OR effectively empty (e.g., only frontmatter/headings/placeholders with no concrete stack rules), treat it as invalid.

Instruct the user to run:

`/ai-specs:init-standards`

to generate (or regenerate) definitive standards from templates.

Do not guess stack details. Always collect them via init-standards.

## 5. Documentation Enforcement

- Always follow `documentation-standards.mdc` when modifying or creating documentation.
- If APIs are created or modified, `api-spec.yml` MUST be updated.
- If the data model changes, update `data-model.md`.
- If setup, workflows, or architecture change, update `development_guide.md`.

Documentation must always reflect the current state of the system.