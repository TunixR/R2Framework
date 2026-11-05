**Repository Agents Guide**

Purpose: onboarding/runbook for agentic coding assistants operating in this repo. Keep changes small, verifiable, and consistent with CI.

Domain overview (details in `ARCHITECTURE.md`):
- A FastAPI backend (`main.py`) that recovers failed RPA robot runs with LLM agents built on Strands.
- A robot opens `WS /recovery/robot_exception/ws` with its `X-ROBOT-KEY`, sends one recovery payload, and the exception plus its recovery context are saved (`routers/recovery.py`).
- The `GatewayAgent` is invoked and delegates to sub-agents exposed as tools: an error agent, then GUI agents that drive the robot's desktop through screenshot/action messages on the same socket.
- Agents, their prompts, tools, sub-agents, call limits and LLM provider routers are database rows (`database/agents/`, `database/provider/`), seeded from `database/populators/*.json` by `populate.py`.
- Every agent, tool and GUI step is traced per recovery in Postgres, with screenshots in S3 (`database/logging/`, `agent_tools/hooks.py`); OpenTelemetry goes to SigNoz (`OBSERVABILITY.md`).
- Robots authenticate with robot keys; users with JWT sessions and administrator/developer roles (`security/`, `middlewares/auth.py`).

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
- Integration tests, against the development stack (`docker compose -f docker/compose.dev.yaml up -d --wait`,
  with `.env` pointing at it, see `docker/README.md`). Each folder skips when its service is unreachable:
```
uv run pytest tests/integration -q
```
  - `postgres/`: version, schema vs. models, a rolled-back write, the read-only monitoring role.
  - `s3/`: object round trips through the SeaweedFS S3 gateway.
  - `observability/`: the framework's traces and logs in SigNoz (collector on `:4318`, ClickHouse via
    `docker exec r2framework-signoz-clickhouse-1` or `SIGNOZ_CLICKHOUSE_URL`); deletes the data it exports.
    See `OBSERVABILITY.md` → Tests.
  - `interoperability/`: calls to Postgres and S3 show up in SigNoz through the otel-agent (logs and
    metrics); waits up to one scrape interval (~2.5 min for the folder).

5) Local services (Docker)
- Postgres, SeaweedFS S3 and SigNoz run from `docker/compose.dev.yaml`; the framework runs on the
  host. Setup, ports, upgrades and production (`docker/compose.prod.yaml`): `docker/README.md`.

6) Database + migrations (Alembic)
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

7) “Full verification” (recommended before PR)
```
uv run ruff . --fix && uv run basedpyright -p pyproject.toml --level error && uv run bandit -c pyproject.toml -r . && uv run pytest tests/unit -q
```

8) Code style (repo conventions)
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

9) SQLModel / Alembic repo-specific patterns
- Model registration: `database/general.py` and `migrations/env.py` use `from ...models import *` so `SQLModel.metadata` sees all tables.
  - If you add a new model module, ensure it is imported in those aggregation points.
  - Keep the existing `# noqa: F403` annotations and add a short “why” if you introduce a new one.
- Unit tests use SQLite. If you introduce Postgres-only types, add a SQLite compile shim (see `tests/unit/fixtures/session_fixture.py` mapping `JSONB` -> `JSON`).

10) Testing conventions
- Tests should be deterministic and isolated.
- Prefer fixtures from `tests/unit/fixtures/*` via `tests/unit/conftest.py` (it uses `pytest_plugins`).
- When touching DB-related code, ensure tests don’t depend on external Postgres; unit tests use SQLite fixtures.

11) Security / secrets / env
- Do not commit secrets; `.env` is local-only; `.env.example` is the safe template.
- Treat these as sensitive: `SECRET_KEY`, `PROVIDER_API_KEY`, `FREE_PROVIDER_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
- `bandit` excludes `tests/` and `migrations/` (see `[tool.bandit]` in `pyproject.toml`).

12) Repo automation files (read before changing workflows)
- `pyproject.toml`: dependencies + tool configuration (bandit, basedpyright).
- `.pre-commit-config.yaml`: ruff, bandit, basedpyright, and unit tests.
- `.github/workflows/unit-tests.yml`: CI uses `uv sync --all-extras --frozen` then `uv run pytest tests/unit -q`.

13) Cursor / Copilot rules
- Cursor rules: no `.cursor/rules/` and no `.cursorrules` found at repo root.
- Copilot instructions: no `.github/copilot-instructions.md` found.

14) When blocked
- If a change impacts secrets, auth, production config, billing, or data retention: stop and ask a targeted question.
- If a check fails: rerun the exact failing command locally and report the minimal failing output needed to diagnose.

15) Agent workflow (practical default)
1. `uv sync --all-extras --frozen`
2. Make the smallest change that satisfies the request.
3. `uv run ruff . --fix`
4. `uv run basedpyright -p pyproject.toml --level error`
5. Run the narrowest relevant test(s) (`pytest` nodeid preferred).

If you see anything missing or a CI mismatch, update this document and add a short note in the PR describing why the agent workflow changed.

16) Documentation
Docs are conceptual and stable: they explain ideas and how they connect, then point to the code. Don't copy schemas, endpoint lists, DB diagrams or config values into markdown. A typical code change needs no doc edit.

Doc map:
| Question | File |
| --- | --- |
| What is it, how do I run it, where is what? | `README.md` |
| How do the pieces fit together? | `ARCHITECTURE.md` |
| What is implemented vs. planned? | `REQUIREMENTS.md` (the only place that tracks this) |
| How do I work in the repo? | `AGENTS.md` (this file) |
| Traces, logs, SigNoz | `OBSERVABILITY.md` |
| Docker services and production | `docker/README.md` |
| Endpoints, payloads, fields | the code and `/scalar` (OpenAPI) |

Read before changing: read `ARCHITECTURE.md` before touching the recovery flow, agents, auth or telemetry (and `OBSERVABILITY.md` for telemetry).

Update docs, in the same PR, only if the change:
- [ ] adds, removes or renames a top-level module or concept → README repo map, `ARCHITECTURE.md`;
- [ ] changes the recovery lifecycle, the auth model or an external interface such as the WS protocol or robot contract → `ARCHITECTURE.md` (and `scripts/recovery_ws_client/README.md` for the robot side);
- [ ] implements or drops a requirement → its checkbox in `REQUIREMENTS.md`;
- [ ] adds, removes or renames an env var → `.env.example` (and the table in `OBSERVABILITY.md` for observability settings);
- [ ] changes setup, test or lint commands → `AGENTS.md`, README quickstart;
- [ ] changes Docker services, ports or deployment → `docker/README.md`.

Don't update docs for: bug fixes, refactors inside a module, new fields or endpoints that follow existing patterns, new agents/tools/seed data, prompt tweaks. The code and `/scalar` are the source of truth for those.
