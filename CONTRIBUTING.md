# Contributing

How changes are named, described and labelled here. Repo setup,
commands and code style are in `AGENTS.md`.

The repo uses one vocabulary everywhere: a **type** (what kind of change) and an **area** (which
part of the system). The same words show up in branch names, commit messages, PR titles and labels.
Tooling enforces it, so don't rely on memory:

- the `commit-msg` hook (`pre-commit install`) checks every commit message;
- CI checks the PR title, which becomes the squash commit;
- labels are added automatically from PR titles, changed files, issue forms and issue text.

The vocabulary is defined in `.github/labeler.yml` (areas) and `.github/scripts/conventions.py`
(types). A unit test (`tests/unit/ci/test_conventions.py`) fails if the labels, issue forms or this
file drift from it.

## Types

| Type | Use for | Label |
| --- | --- | --- |
| `feat` | new behaviour, a requirement | `type: feature` |
| `fix` | a bug | `type: bug` |
| `refactor` | restructuring without behaviour change | `type: refactor` |
| `perf` | performance | `type: perf` |
| `test` | tests only | `type: test` |
| `docs` | documentation only | `type: docs` |
| `build`, `ci`, `chore`, `revert` | build, CI, tooling, dependencies, reverts | `type: chore` |

`type: security` is applied by hand to vulnerability fixes.

## Areas

An area is both a commit scope and an `area:` label. Leave the scope out when a change is truly
cross-cutting. The authoritative paths are the globs in `.github/labeler.yml`.

| Area / scope | Covers |
| --- | --- |
| `recovery` | recovery lifecycle and WS protocol: `routers/recovery.py`, `templates/recovery_payload.py` |
| `agents` | agent model, gateway, error agent, sub-agent wiring, prompts: `database/agents/`, `gateway/`, `prompts/`, `templates/` |
| `gui-agent` | GUI agents (Tooled GUI, UI-TARS loop) and their action set |
| `tools` | Strands tools, hooks, call limits: `agent_tools/`, `database/tools/` |
| `providers` | LLM provider routers and backbones: `database/provider/` |
| `auth` | users, roles, sessions, robot keys: `security/`, `middlewares/`, `database/auth/`, `database/keys/` |
| `tracing` | per-recovery trace logging and artifact export: `database/logging/`, `s3/` |
| `observability` | OpenTelemetry and SigNoz: `observability/`, `OBSERVABILITY.md` |
| `db` | engine, migrations, seed data: `database/general.py`, `migrations/`, `database/populators/`, `populate.py` |
| `api` | routers other than recovery: agents, tools, provider, keys, logging |
| `evals` | `evals/`, `experiment_files/` |
| `ws-client` | robot-side test client: `scripts/recovery_ws_client/` |
| `docker` | `docker/` |
| `ci` | `.github/`, `.pre-commit-config.yaml`, these conventions |
| `deps` | dependency bumps (`pyproject.toml`, `uv.lock`); labelled `dependencies` |

There are no `wip`, `telemetry` (use `observability`), `deps-dev` or `integration` scopes. A new
area goes into `.github/labeler.yml`, `.github/labels.yml`, the "Area" dropdown of the issue forms
and the table above, all in the same PR.

## Commits

```
<type>(<area>)!: <imperative, lowercase summary>

<body: why, not what>

BREAKING CHANGE: <what breaks and how to migrate>
Refs #123
```

- Write the summary in the imperative and start it lowercase (`add`, not `Added`), with no trailing
  period. Aim for 72 characters or fewer; the hard limit is 100.
- Mark breaking changes (WS protocol, robot contract, DB schema without a migration path, env var
  renames) with `!` and a `BREAKING CHANGE:` footer. The PR then gets the `breaking` label.
- Footers: `Refs #N`, `Closes #N`.
- Put work in progress in a draft PR, not under a `wip` scope.

## Branches

- `<type>/<issue>-<slug>`, e.g. `fix/207-report-result`, `feat/215-agent-polymorphism`. Use `feat/`,
  not `feature/`.
- Leave dependency-bot branches as the bot names them.
- `develop` is the integration branch: it is the default and every PR targets it. `master` only
  receives releases.

## Issues

Open issues through a form (bug, feature/requirement, refactor). Blank issues are disabled, and
security issues go to private reporting. The form applies the `type:` label. `area:` labels come
from the form's "Area" dropdown and from the repo paths the issue mentions (`routers/recovery.py`,
or a GitHub link to a file). Only the areas most of those paths point at are applied (at most three),
top-level docs such as `ARCHITECTURE.md` are ignored, and an issue that cites many areas equally
gets none. Automation only ever adds issue labels, never removes them.

- Write the title as a plain description, with no `Bug:` / `Docs:` prefix: type and area are labels.
- Give enough context to start work without asking: file references, current vs. expected
  behaviour, acceptance criteria. #207 and #215 are good models.
- Issues opened without a form (API, `gh issue create`) need their `type:` label added by hand.

## Pull requests

- Write the title as a Conventional Commit, checked in CI. It becomes the squash commit and sets
  the `type:` label. `breaking` comes from `!` or a `BREAKING CHANGE:` footer in the description,
  `dependencies` from the `deps` scope.
- `area:` labels follow the changed files and update on every push.
- Fill in the template: summary (what and why), `Closes #N`, how it was verified, checklist.
- Squash-merge by default. Rebase-merge only when every commit is a reviewable Conventional Commit.

## Labels

Labels are managed as code in `.github/labels.yml`. On push to `develop` they are synced to the
repository, and labels missing from the file are deleted. Labels other than `type:`, `area:`,
`breaking` and `dependencies` are applied by hand: `priority: high|low` (unlabelled = normal),
`status: blocked|needs-info|needs-design`, and the GitHub defaults (`good first issue`,
`help wanted`, `duplicate`, `invalid`, `wontfix`, `question`).

## Dependencies

Dependabot is the only dependency bot (`.github/dependabot.yml`). Minor and patch bumps arrive as
one grouped PR per week, majors one PR each, all titled `chore(deps): ...` and labelled
`dependencies`.
