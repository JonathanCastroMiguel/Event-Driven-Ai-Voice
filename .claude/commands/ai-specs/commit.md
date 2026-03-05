---
category: Workflow
description: Create a structured commit and optionally open/update a PR
  following project standards
name: "AI-SPECS: Commit"
tags:
- git
- commit
- pr
---

Create a structured commit following project standards.

## Steps

1.  Review changes

    -   Run `git status`
    -   Run `git diff`
    -   Ensure only relevant files are included

2.  Write commit message

    -   Use clear, descriptive English
    -   Follow project language rules defined in `CLAUDE.md`
    -   Prefer small, focused commits
    -   Use conventional commit style if applicable

    Example:

    feat(auth): add JWT validation middleware

    -   Implement token verification
    -   Add unit tests
    -   Update api-spec.yml

3.  Create commit

    ``` bash
    git add <files>
    git commit -m "<message>"
    ```

4.  (Optional) Open or update Pull Request

    -   Use GitHub CLI (`gh`) when available:

    ``` bash
    gh pr create --fill
    ```

    or update existing PR:

    ``` bash
    gh pr status
    ```

## Guardrails

-   Do not include unrelated changes
-   Ensure documentation is up to date before committing
-   Keep commits atomic and reversible
-   Never reference non-existent standards files
