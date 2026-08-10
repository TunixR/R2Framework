from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_payload_by_id(payload_file: Path, payload_id: int) -> dict[str, Any]:
    if not payload_file.exists():
        raise ValueError(f"Payload file not found: {payload_file}")

    try:
        raw = json.loads(payload_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in payload file: {payload_file}") from exc

    if not isinstance(raw, list):
        raise ValueError("Payload catalog must be a JSON array")

    seen_ids: set[int] = set()
    selected: dict[str, Any] | None = None

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError("Each payload catalog entry must be an object")
        if "id" not in item or "payload" not in item:
            if not all(key in item for key in ("task_name", "ui_log", "errored_act")):
                raise ValueError(
                    "Each entry must be either {'id': int, 'payload': {...}} or a payload object"
                )
            item_id = i + 1
            if item_id == payload_id:
                selected = item
                break
            continue

        item_id = item["id"]
        if not isinstance(item_id, int):
            raise ValueError("Payload entry 'id' must be an integer")
        if item_id in seen_ids:
            raise ValueError(f"Duplicate payload id found: {item_id}")
        seen_ids.add(item_id)

        payload = item["payload"]
        if not isinstance(payload, dict):
            raise ValueError("Payload entry 'payload' must be an object")

        if item_id == payload_id:
            selected = payload
            break

    if selected is None:
        raise ValueError(f"Payload id not found: {payload_id}")

    return selected
