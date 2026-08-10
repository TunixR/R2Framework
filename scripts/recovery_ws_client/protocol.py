from __future__ import annotations

import json
from typing import Any


def parse_message(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Websocket message must be a JSON object")
    return data


def message_type(data: dict[str, Any]) -> str:
    msg_type = data.get("type")
    if not isinstance(msg_type, str):
        return ""
    return msg_type
