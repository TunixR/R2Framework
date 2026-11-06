# R2Framework backend

R2Framework recovers failed RPA runs. When a software robot hits an exception, it opens a
WebSocket to this FastAPI backend and sends what it knows: the task, the UI log up to the failure,
the failed activity and the process variables. LLM agents built on
[Strands](https://strandsagents.com) analyse the failure and, when they can, take over the robot's
desktop through screenshots and UI actions to bring the process back to a state the robot can
continue from. The backend tells the robot where to resume, and records every agent, tool and GUI
step so a run can be inspected or exported afterwards.

## Quickstart

You need Docker, [uv](https://docs.astral.sh/uv/) and an OpenAI-compatible LLM endpoint
(OpenRouter, OpenAI, vLLM...).

1. Start Postgres, SeaweedFS (S3) and SigNoz (observability). Details: [`docker/README.md`](docker/README.md).

   ```bash
   cp docker/.env.example docker/.env   # fill in the passwords
   docker compose -f docker/compose.dev.yaml up -d --wait
   ```

2. Configure the framework. Use the same Postgres and S3 credentials as `docker/.env`, set
   `SECRET_KEY` and `ADMIN_USERNAME`/`ADMIN_PASSWORD`, and fill in the `PROVIDER_*` models and key.

   ```bash
   cp .env.example .env
   ```

3. Install dependencies, create the schema and seed the default agents, tools, provider routers and
   admin user.

   ```bash
   uv sync --all-extras --frozen
   uv run alembic upgrade head
   uv run python populate.py
   ```

4. Run the API and open the API reference at http://localhost:8000/scalar.

   ```bash
   uv run fastapi dev main.py
   ```

5. Try a recovery: log in as the admin (`POST /auth/login`), create a robot key (`POST /keys`),
   then run the desktop test client with it, see
   [`scripts/recovery_ws_client/README.md`](scripts/recovery_ws_client/README.md). It performs
   real mouse and keyboard actions on your desktop.

## Repository map

| Path | What lives there |
| --- | --- |
| `main.py` | FastAPI app: routers, `/health`, `/scalar`, observability setup |
| `settings.py`, `config.py` | Environment settings (see `.env.example`) and fixed limits |
| `routers/` | HTTP and WebSocket endpoints: recovery, evals, agents, tools, provider, keys, auth, logging |
| `database/` | SQLModel models and engine, grouped by concept (agents, tools, provider, keys, auth, logging) |
| `database/populators/` | Seed data (`agents.json`, `routers.json`) and the code that loads it; run by `populate.py` |
| `gateway/` | Tools for the gateway agent (human hand-off is a placeholder) |
| `agent_tools/` | Strands tools and hooks shared by agents: screenshots, tool limits, trace logging |
| `prompts/`, `templates/` | Agent prompts and the Pydantic models for recovery payloads and agent responses |
| `security/`, `middlewares/` | Password and robot-key hashing, JWT handling, auth dependencies |
| `s3/` | S3 client for screenshots |
| `observability/` | OpenTelemetry tracing, logging, redaction and domain spans (see [`OBSERVABILITY.md`](OBSERVABILITY.md)) |
| `evals/` | Offline evaluation runners and evaluators |
| `scripts/` | Developer tools, including the recovery WebSocket test client |
| `migrations/` | Alembic migrations |
| `docker/` | Compose stacks for development and production |
| `tests/` | `unit/` (SQLite, runs in CI) and `integration/` (needs the Docker stack) |
| `modules/` | Reserved for recovery modules; currently empty |

## Documentation

| Question | Read |
| --- | --- |
| What is this and how do I run it? | This file |
| How do the pieces fit together? | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| What is implemented and what is planned? | [`REQUIREMENTS.md`](REQUIREMENTS.md) |
| How do I work in the repo (lint, tests, migrations, code style)? | [`AGENTS.md`](AGENTS.md) |
| How do I name commits, branches, issues and PRs? How do labels work? | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Traces, logs and SigNoz | [`OBSERVABILITY.md`](OBSERVABILITY.md) |
| Docker services, ports, production | [`docker/README.md`](docker/README.md) |
| Endpoints and payload schemas | `/scalar` on a running server |
