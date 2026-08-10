# Recovery WS Test Client

This repository now includes a standalone websocket test client for recovery flow development and verification.

It is not coupled to pytest and is intended for local desktop-driven E2E checks.

## What It Does

- Connects to `/recovery/robot_exception/ws` with `X-ROBOT-KEY`.
- Sends a predefined payload selected from `scripts/data/payloads.json`.
- Responds to `type: "screenshot"` messages using `pyautogui.screenshot()` bytes.
- Executes `type: "action"` messages automatically using `pyautogui`.
- Enforces a non-blocking minimum delay between actions (default 1 second).
- Writes optional transcript logs for run analysis.

## Payload Catalog

Payloads are stored in:

- `scripts/data/payloads.json`

Each entry has this shape:

```json
{
  "id": 1,
  "payload": {
    "task_name": "...",
    "platform": "...",
    "os": "...",
    "variables": {},
    "ui_log": [],
    "errored_act": {},
    "model": "..."
  }
}
```

Use `--payload-id` to choose which payload to send.

## Run

```bash
rtk uv run python -m scripts.recovery_ws_test_client \
  --ws-url ws://localhost:8000/recovery/robot_exception/ws \
  --robot-key "$X_ROBOT_KEY" \
  --payload-file scripts/data/payloads.json \
  --payload-id 1 \
  --action-delay-seconds 1 \
  --log-json tmp/recovery_ws_log.json
```

Optional flags:

- `--dry-run-actions`
- `--max-actions <n>`
- `--save-screenshots-dir <dir>`

## Safety Notes

- Actions are performed on your active desktop.
- Keep `pyautogui` fail-safe enabled (default in runner).
- Avoid running this on a machine with unrelated foreground activity.

## Verification Checklist

1. Valid payload id runs and reaches websocket session.
2. Invalid payload id fails fast before connect.
3. Bad robot key is rejected by server.
4. Screenshot requests are answered with image bytes.
5. Action results are sent with success/failure shape.
6. Action execution spacing is at least 1 second.
7. `done` finalizes run with exit code 0 and summary.
