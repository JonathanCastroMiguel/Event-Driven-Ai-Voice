---
name: "ai-specs: Init Standards"
description: Generate definitive backend and frontend standards from templates using the project's tech stack
category: Workflow
tags: [standards, templates, bootstrap]
---

Generate missing definitive standards files for this repository using the provided templates and the project's actual tech stack.

Goal:
Create (or update if empty) the following files:

- ai-specs/specs/backend-standards.mdc
- ai-specs/specs/frontend-standards.mdc

Templates:

- ai-specs/specs/templates/backend-standards-template.mdc
- ai-specs/specs/templates/frontend-standards-template.mdc

---

## Steps

---

### 0. Validate template availability

Check that both template files exist.

If any template is missing:

- FAIL immediately
- Show the missing path
- Do not continue

---

### 1. Optional Integrations (MCP)

This project includes support for external integrations via MCP (Model Context Protocol).

The following tools can be connected optionally:

- [ ] Notion (User stories / documentation)
- [ ] Jira (Issue management via Atlassian)
- [ ] Figma (Design system / UI components)

These integrations are not required.  
If none are authenticated, the project will continue operating in manual mode without disruption.

Authentication (per user):

1. Open Claude Code in this repository.
2. Run the command `/mcp`.
3. For each integration you want to enable, click **Authenticate**.
4. Complete the login process in your browser.

Quick Verification:

After authentication, test the connection:

- Notion → “List my databases” or “Search pages containing ‘Spec’”
- Jira → “Search issues assigned to me”
- Figma → “List recent team files”

If you choose not to connect any tools now, you may proceed with the workflow normally.

If any MCP integration is authenticated, you may use it to gather relevant project context before asking questions in Step 2.

- If Notion is connected, search for architecture, technical decisions, or existing specifications.
- If Jira is connected, identify project keys or recurring issue patterns.
- If Figma is connected, inspect the primary design system or UI constraints.

Use this information to reduce redundant questions.

### 2. Collect project stack information

Before asking questions, verify whether relevant information has already been retrieved from MCP integrations.

Use the AskUserQuestion tool to gather the necessary stack details.

Minimum required information:

Backend:
- Language
- Framework
- Architecture pattern
- Validation approach
- Authentication strategy
- Background jobs (if any)

Data:
- Database
- ORM / Query builder
- Migration strategy

API:
- REST or GraphQL
- OpenAPI version (if applicable)
- Error response format
- Versioning strategy

Testing:
- Unit testing framework
- Integration / e2e framework
- Coverage expectations

Frontend:
- Framework
- State management approach
- Routing
- Styling solution
- Component library (if any)

Tooling:
- Linting
- Formatting
- CI/CD
- Monorepo or single repo

If any answer is vague or missing, ask follow-up questions.

---

### 3. Generate backend standards

Create:

ai-specs/specs/backend-standards.mdc

Rules:

- Use the template for STRUCTURE ONLY (headings and section order).
- Do NOT copy template example content verbatim.
- Replace generic placeholders with stack-specific rules.
- Provide concrete conventions and commands.
- Do not invent tools not confirmed by the user.

Must include:

- Folder structure conventions
- API patterns
- Data access patterns
- Error handling conventions
- Authentication rules
- Logging conventions
- Testing rules
- Migration strategy
- Definition of Done for backend changes

---

### 4. Generate frontend standards

Create:

ai-specs/specs/frontend-standards.mdc

Rules:

- Use the template for STRUCTURE ONLY.
- Do NOT copy example content verbatim.
- Provide stack-specific conventions.

Must include:

- Component structure conventions
- State management patterns
- Styling conventions
- Accessibility baseline
- Testing strategy
- Definition of Done for frontend changes

---

### 5. Report results

Display a clear summary:

- Which files were created
- Which templates were used
- The confirmed stack assumptions

---

## Output On Success

## Standards Initialized

Created:
- ai-specs/specs/backend-standards.mdc
- ai-specs/specs/frontend-standards.mdc

Templates used:
- ai-specs/specs/templates/backend-standards-template.mdc
- ai-specs/specs/templates/frontend-standards-template.mdc

Stack configuration has been applied to both standards files.

---

## Output On Error (Missing Template)

## Init Standards Failed

Missing template:
- <path>

Add the template file and retry.

---

## Guardrails

- Templates define STRUCTURE ONLY (never copy example content).
- Never invent stack details — always confirm with the user.
- Keep standards concrete and actionable.
- Do not overwrite existing standards without explicit confirmation.
