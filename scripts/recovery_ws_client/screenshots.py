from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pyautogui
from PIL import Image, ImageDraw


def capture_screenshot_bytes(save_dir: Path | None = None) -> bytes:
    image = pyautogui.screenshot()
    image = _draw_mouse_pointer(image)

    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    content = buffer.getvalue()

    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        out_file = save_dir / f"shot_{stamp}.jpg"
        _ = out_file.write_bytes(content)

    return content


def _draw_mouse_pointer(image: Image.Image) -> Image.Image:
    mouse_x, mouse_y = pyautogui.position()
    draw = ImageDraw.Draw(image)
    pointer = [
        (mouse_x, mouse_y),
        (mouse_x, mouse_y + 20),
        (mouse_x + 5, mouse_y + 15),
        (mouse_x + 10, mouse_y + 23),
        (mouse_x + 14, mouse_y + 21),
        (mouse_x + 9, mouse_y + 13),
        (mouse_x + 16, mouse_y + 13),
    ]
    draw.polygon(pointer, fill="white", outline="black", width=2)
    return image
