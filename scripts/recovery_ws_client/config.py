from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ClientConfig:
    ws_url: str
    robot_key: str
    payload_file: Path
    payload_id: int
    action_delay_seconds: float = 1.0
    max_actions: int | None = None
    dry_run_actions: bool = False
    log_json: Path | None = None
    save_screenshots_dir: Path | None = None
