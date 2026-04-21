# Contributing

Thanks for your interest in contributing! This repository follows a
**Spec-Driven Development (SDD)** workflow — specifications are the source of
truth and code is an implementation artifact.

## Ground Rules

- **All artifacts in English**: code, comments, docs, commit messages, tests.
- **Baby steps + TDD**: one task at a time, starting from failing tests.
- **Type safety**: all code must be fully typed (strict `mypy` on backend,
  strict TypeScript on frontend).
- **Incremental changes**: prefer small, focused PRs over large ones.
- **Standards first**: never bypass the OpenSpec lifecycle.

## Workflow

1. **Open an issue** describing the change (bug, feature, or refactor).
2. **Start a new change** via `/opsx:new` — this creates the spec artifacts.
3. **Implement** via `/opsx:apply`, respecting the generated tasks.
4. **Verify** with `/opsx:verify` to ensure implementation matches the spec.
5. **Sync & archive** with `/opsx:sync` and `/opsx:archive`.
6. **Update documentation** (`api-spec.yml`, `data-model.md`,
   `development_guide.md`, `architecture.md`) whenever behavior changes.
7. **Open a pull request** against `main`.

## Local Development

### Backend (Python 3.12)

```bash
cd backend
uv sync
uv run pytest
uv run ruff check .
uv run mypy .
```

### Frontend (Next.js 15)

```bash
cd frontend
pnpm install
pnpm dev
pnpm test
```

### Full stack (Docker)

```bash
docker compose up -d
```

After any frontend change, rebuild the image:

```bash
docker compose build frontend && docker compose up -d frontend
```

## Commit Style

- Short, imperative subject (`feat: add X`, `fix: handle Y`, `docs: ...`).
- Reference the related change / issue when relevant.
- Keep commits focused — one logical change per commit.

## Pull Requests

- Keep PRs small and focused on a single concern.
- Ensure tests pass (`pytest`, `vitest`, `playwright` as applicable).
- Ensure lint/type checks pass (`ruff`, `mypy`, `eslint`, `tsc`).
- Update any documentation impacted by the change.
- Link the related OpenSpec change in the PR description.

## Code of Conduct

By participating in this project you agree to abide by the
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing you agree that your contributions will be licensed under the
[MIT License](LICENSE).
