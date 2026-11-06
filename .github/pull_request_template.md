<!--
Title: a Conventional Commit, `<type>(<area>)!: <lowercase summary>`; it becomes the squash commit
and sets the `type:` label (CONTRIBUTING.md). `area:` labels are added from the changed files.
-->

## Summary

<!-- What changes and why. Not a file-by-file narration of the diff. -->

Closes #

## How it was verified

<!-- Tests added or run, manual checks (recovery run, SigNoz trace, ...). -->

## Checklist

- [ ] `pre-commit run --all-files` passes (ruff, basedpyright, bandit, unit tests)
- [ ] Alembic migration included if models changed
- [ ] Breaking change (WS protocol, robot contract, DB schema, env vars) marked with `!` and a `BREAKING CHANGE:` footer
- [ ] Docs updated if required by `AGENTS.md` §16: `ARCHITECTURE.md`, `REQUIREMENTS.md` checkbox, `.env.example`, `docker/README.md`, `scripts/recovery_ws_client/README.md` (protocol)
