**Repository Agents Guide**
- Purpose: onboarding and runbook for agentic coding assistants operating in this repository.
- Location: root of the repo — use `AGENTS.md` when automating tasks, CI, or running local checks.

1) Quick environment and tooling
- Python: `>=3.12` (see `pyproject.toml` and `.python-version`).
- Package/tool driver: `uv` is used in CI and pre-commit hooks (see `.github/workflows/unit-tests.yml` and `.pre-commit-config.yaml`).
- Virtual env (recommended): `python -m venv .venv` then activate before running `uv` or direct Python commands.

2) Build / install / sync
- Install project deps (reproducible env used in CI):
```
# sync all extras and frozen deps (same as CI)
uv sync --all-extras --frozen
```
- If you don't use `uv`, create and activate a venv and use pip as usual; prefer `uv` to match CI.

3) Lint / format / static checks
- The repo uses `ruff` for linting/formatting and `basedpyright` for type checks, plus `bandit` for security scanning. Pre-commit runs:
  - `ruff` (with `--fix`),
  - `ruff-format`,
  - `bandit` (with args from `pyproject.toml`),
  - `basedpyright` (via `uv run basedpyright -p pyproject.toml --level error`).

- Common commands (run locally to mimic CI/pre-commit):
```
# run ruff (format + lints)
uv run ruff . --fix

# just check (no fixes)
uv run ruff .

# run type checks (basedpyright)
uv run basedpyright -p pyproject.toml --level error

# run bandit security scan (pre-commit uses -c pyproject.toml)
uv run bandit -c pyproject.toml -r .
```

4) Tests
- Unit tests live under `tests/unit` (CI runs `uv run pytest tests/unit -q`). The project depends on `pytest`, `pytest-asyncio`, and `pytest-cov`.
- Run the whole unit test suite:
```
uv run pytest tests/unit -q
```
- Run a single test file:
```
uv run pytest tests/unit/path/to/test_file.py -q
```
- Run a single test function (explicit nodeid):
```
uv run pytest tests/unit/path/to/test_file.py::test_function_name -q
```
- Run tests matching a pattern (fast selection):
```
uv run pytest -k "substring_or_expr" -q
```
- Run async tests: same `pytest` invocation — async tests use `pytest-asyncio` fixtures.
- Run with coverage:
```
uv run pytest tests/unit --cov=your_package --cov-report=term-missing
```

5) Pre-commit & CI
- Install pre-commit hooks locally to match CI behavior:
```
pre-commit install
# or run them once
pre-commit run --all-files
```
- CI workflow ` .github/workflows/unit-tests.yml` sets up Python 3.12 with `uv` and runs `uv run pytest tests/unit -q` — agents should mirror this for reproducibility.

6) Running a single test from an agent
- Preferred (explicit nodeid and quiet):
```
uv run pytest tests/unit/<relative_path_to_file>::test_name -q
```
- If the agent cannot compute the exact file path, use `-k` with a short unique substring:
```
uv run pytest -k "unique_test_substring" -q
```

7) Code style and conventions
- Base style: follow PEP8 with repository-specific rules enforced by `ruff` and `basedpyright`. `ruff` is configured in the pre-commit hooks and should be the primary formatter/linter.

- Imports
  - Use absolute imports for project modules (e.g. `from gateway.agent import GatewayAgent`).
  - Group imports in three sections separated by a blank line: (1) standard library, (2) third-party, (3) local packages. Sort each group alphabetically.
  - Do not use wildcard imports (`from x import *`).
  - Avoid circular imports; prefer local imports inside functions for optional dependencies.

- Formatting
  - Let `ruff` manage formatting. If you need to format manually, run `uv run ruff . --fix`.
  - Use 4-space indentation, limit lines to 88/99 chars as needed for readability.
  - Prefer f-strings for interpolation.

- Typing / types
  - Annotate public functions and methods with precise types. Use `typing` and `collections.abc` when appropriate.
  - Avoid unnecessary `Any`. When legacy `Any` is needed, add a `# type: ignore[override]` with a short justification.
  - Use `basedpyright` (`uv run basedpyright -p pyproject.toml`) as the primary type-checker; mirror its configuration from `pyproject.toml`.

- Naming
  - Modules / packages: short lowercase with underscores when necessary.
  - Classes: PascalCase (e.g. `GatewayAgent`).
  - Functions / variables: snake_case.
  - Constants: UPPER_SNAKE.
  - Tests: `test_` prefix on functions and files (e.g. `test_my_feature.py`, `def test_something():`).

- Async patterns
  - Use `async def` for IO-bound operations that call async libraries (FastAPI handlers, db calls, aioboto3, etc.).
  - Avoid blocking calls in async functions; if you must, run them in a thread executor.
  - Name coroutine functions clearly and `await` all coroutine calls.

- Error handling and logging
  - Do not use bare `except:`. Prefer `except SpecificError:` or `except Exception as exc:` and preserve context where appropriate.
  - Raise domain-specific exceptions (create small exception classes per module when useful) rather than overloading generic exceptions.
  - Log at appropriate levels (DEBUG for internals, INFO for important lifecycle events, WARNING for recoverable issues, ERROR for failures). Use structured messages when possible.
  - When re-raising, use `raise` to preserve the original traceback or `raise NewError(...) from exc` to keep chaining.

- Security & secrets
  - Do not commit secrets. `.env` exists but treat it as local-only; CI should use secrets in the environment.
  - Run `bandit` to surface common security issues: `uv run bandit -c pyproject.toml -r .`.

- Database / SQLModel patterns
  - Use `sqlmodel` models for typed DB models, keep DB access in `database` package and small repository-style helpers in `database/tools`.
  - Keep transaction boundaries explicit and short; prefer context managers for connections/sessions.

8) Tests style
- Tests live under `tests/unit` and should be small, focused, deterministic, and fast.
- Use fixtures (`conftest.py`) for reusable setups; prefer function scope for speed unless expensive setup is required.
- For async components use `pytest.mark.asyncio` and `pytest-asyncio` fixtures.

9) Project tooling files to be aware of
- `pyproject.toml` — dependency and tool configuration (type-checker settings, dev deps).
- `.pre-commit-config.yaml` — configured pre-commit hooks (ruff, bandit, basedpyright, pytest-unit hook for `tests/unit`).
- `.github/workflows/unit-tests.yml` — CI job that mirrors local `uv` usage for tests.

10) Cursor / Copilot rules
- Cursor rules: no ` .cursor/rules/` or `.cursorrules` files found in the repo — no extra Cursor rules to import.
- Copilot instructions: no `.github/copilot-instructions.md` file found. If such files are added, agents MUST read them and honor their guidance.

11) When you are blocked (agent guidance)
- If a change touches production configuration, secrets, or billing, ask exact questions and do not proceed.
- If a test or linter fails, run the exact failing command locally, collect stderr/stdout, and include the minimal failing stack / message in your report.

12) Recommended agent workflow
1. Sync environment: `uv sync --all-extras --frozen`.
2. Run `uv run ruff . --fix` and `uv run basedpyright -p pyproject.toml`.
3. Run unit tests for the affected area: `uv run pytest path/to/test -q`.
4. If pre-commit is used, run `pre-commit run --all-files` before opening PRs.

Appendix: helpful command examples
```
# install pre-commit hooks
pre-commit install

# run a single test function by nodeid
uv run pytest tests/unit/gateway/test_agent.py::test_agent_routes -q

# run linters and type checks
uv run ruff . --fix && uv run basedpyright -p pyproject.toml --level error

# full local verification (lint, type-check, security, tests)
uv run ruff . --fix && uv run basedpyright -p pyproject.toml --level error && uv run bandit -c pyproject.toml -r . && uv run pytest tests/unit -q
```

If you see anything missing or a CI mismatch, update this document and add a short note in the PR describing why the agent workflow changed.
