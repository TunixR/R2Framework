**Repository Agents Guide**

Purpose: onboarding/runbook for agentic coding assistants operating in this repo. Keep changes small, verifiable, and consistent with CI.

1) Environment
- Python: project requires `>=3.12` (`pyproject.toml`); CI uses Python `3.12` (`.github/workflows/unit-tests.yml`).
- Note: `.python-version` currently pins `3.13`; when reproducing CI issues, prefer Python `3.12`.
- Tooling: `uv` is the expected runner for installs, lint, type-check, and tests.

2) Install / sync (matches CI)
```
uv sync --all-extras --frozen
```

3) Lint / format / type-check / security
Pre-commit and CI expect these tools:
- Lint + auto-fix + format (ruff):
```
uv run ruff . --fix
```
- Type-check (basedpyright):
```
uv run basedpyright -p pyproject.toml --level error
```
- Security scan (bandit):
```
uv run bandit -c pyproject.toml -r .
```
- Run the full pre-commit suite locally:
```
pre-commit run --all-files
```
- Install the git hooks locally:
```
pre-commit install
```

4) Tests
CI runs unit tests only:
```
uv run pytest tests/unit -q
```

Running a single test (preferred patterns):
- Single file:
```
uv run pytest tests/unit/path/to/test_file.py -q
```
- Single test by nodeid:
```
uv run pytest tests/unit/path/to/test_file.py::test_name -q
```
- Quick selection by substring/expression:
```
uv run pytest -k "unique_substring" -q
```

Optional (not in CI):
- Integration tests (exist under `tests/integration`):
```
uv run pytest tests/integration -q
```

5) Database + migrations (Alembic)
- Config: `alembic.ini`, migration env: `migrations/env.py`.
- Common commands:
```
uv run alembic current
uv run alembic history
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic revision --autogenerate -m "your message"
```
Note: `migrations/env.py` imports models via wildcard to register tables with `SQLModel.metadata`.

6) “Full verification” (recommended before PR)
```
uv run ruff . --fix && uv run basedpyright -p pyproject.toml --level error && uv run bandit -c pyproject.toml -r . && uv run pytest tests/unit -q
```

7) Code style (repo conventions)
- Formatting: let `ruff-format` handle layout; don’t hand-align or fight the formatter.
- Line length: follow ruff defaults/config; keep long expressions readable.
- Imports:
  - Use 3 groups separated by a blank line: stdlib, third-party, local.
  - Prefer absolute imports within the repo.
  - Avoid wildcard imports, except for the SQLModel “model registration” pattern noted below.
  - Avoid circular imports; use local imports inside functions for optional/late-bound deps.
- Naming:
  - Modules/packages: `lower_snake_case`.
  - Classes: `PascalCase`.
  - Functions/vars: `snake_case`.
  - Constants: `UPPER_SNAKE_CASE`.
  - Tests: `tests/unit/.../test_*.py` and `def test_*()`.
- Types:
  - Add precise types on public functions/methods and data models.
  - Prefer `collections.abc` (`Sequence`, `Iterable`, etc.) over `typing` legacy aliases.
  - Avoid `Any` unless required by a third-party API; when unavoidable, keep the `Any` local.
  - Type-checker is `basedpyright`; follow existing patterns like `# pyright: ignore[...]` with a short justification.
  - Prefer `str | None` over `Optional[str]` (Python 3.12+).
- Errors:
  - No bare `except:`; catch specific exceptions or `Exception as exc`.
  - Preserve tracebacks: `raise` or `raise NewError(...) from exc`.
  - For FastAPI endpoints, use `raise HTTPException` with appropriate status codes.
- Logging:
  - Prefer opentelemetry span loggers and structured, actionable messages.
  - Don’t log secrets (API keys, tokens, passwords) or entire request bodies by default.
- Async:
  - Use `async def` for IO-bound code; don’t block the event loop (use executors for blocking work).
  - Always `await` coroutines; keep lifespans/startup logic minimal.

Repo layout conventions (as seen in this codebase):
- HTTP endpoints live in `routers/*` and are included from `main.py`.
- DB models live under `database/*/models.py` using SQLModel.
- Cross-cutting auth lives in `middlewares/auth.py` and `security/*`.

8) SQLModel / Alembic repo-specific patterns
- Model registration: `database/general.py` and `migrations/env.py` use `from ...models import *` so `SQLModel.metadata` sees all tables.
  - If you add a new model module, ensure it is imported in those aggregation points.
  - Keep the existing `# noqa: F403` annotations and add a short “why” if you introduce a new one.
- Unit tests use SQLite. If you introduce Postgres-only types, add a SQLite compile shim (see `tests/unit/fixtures/session_fixture.py` mapping `JSONB` -> `JSON`).

9) Testing conventions
- Tests should be deterministic and isolated.
- Prefer fixtures from `tests/unit/fixtures/*` via `tests/unit/conftest.py` (it uses `pytest_plugins`).
- When touching DB-related code, ensure tests don’t depend on external Postgres; unit tests use SQLite fixtures.

10) Security / secrets / env
- Do not commit secrets; `.env` is local-only; `.env.example` is the safe template.
- Treat these as sensitive: `SECRET_KEY`, `PROVIDER_API_KEY`, `FREE_PROVIDER_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
- `bandit` excludes `tests/` and `migrations/` (see `[tool.bandit]` in `pyproject.toml`).

11) Repo automation files (read before changing workflows)
- `pyproject.toml`: dependencies + tool configuration (bandit, basedpyright).
- `.pre-commit-config.yaml`: ruff, bandit, basedpyright, and unit tests.
- `.github/workflows/unit-tests.yml`: CI uses `uv sync --all-extras --frozen` then `uv run pytest tests/unit -q`.

12) Cursor / Copilot rules
- Cursor rules: no `.cursor/rules/` and no `.cursorrules` found at repo root.
- Copilot instructions: no `.github/copilot-instructions.md` found.

13) When blocked
- If a change impacts secrets, auth, production config, billing, or data retention: stop and ask a targeted question.
- If a check fails: rerun the exact failing command locally and report the minimal failing output needed to diagnose.

14) Agent workflow (practical default)
1. `uv sync --all-extras --frozen`
2. Make the smallest change that satisfies the request.
3. `uv run ruff . --fix`
4. `uv run basedpyright -p pyproject.toml --level error`
5. Run the narrowest relevant test(s) (`pytest` nodeid preferred).

If you see anything missing or a CI mismatch, update this document and add a short note in the PR describing why the agent workflow changed.
