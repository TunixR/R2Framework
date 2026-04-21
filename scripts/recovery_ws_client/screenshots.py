from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pyautogui


def capture_screenshot_bytes(save_dir: Path | None = None) -> bytes:
    image = pyautogui.screenshot()
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    content = buffer.getvalue()

    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        out_file = save_dir / f"shot_{stamp}.jpg"
        out_file.write_bytes(content)

    return content
