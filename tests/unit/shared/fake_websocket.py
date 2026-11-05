"""Robot websocket double for code that talks to the RPA client."""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any, Literal

from PIL import Image


def make_test_image_bytes(
    color: tuple[int, int, int] = (255, 0, 0),
    size: tuple[int, int] = (16, 16),
    fmt: Literal["JPEG", "PNG"] = "JPEG",
) -> bytes:
    """Create an in-memory image and return its encoded bytes."""
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class FakeWebSocket:
    """Minimal async fake of the FastAPI WebSocket the robot client is behind.

    - ``send_json`` records outbound messages as ``("json", data)``.
    - ``receive_bytes`` returns the queued screenshots in order, optionally delayed.
    - ``receive_json`` answers every action with ``{"success": action_success}``.
    """

    def __init__(
        self,
        responses: list[bytes],
        delay: float = 0.0,
        *,
        action_success: bool = True,
    ) -> None:
        self._responses = list(responses)
        self._delay = delay
        self.action_success = action_success
        self.sent_messages: list[Any] = []
        self.closed = False

    @property
    def actions(self) -> list[dict[str, Any]]:
        """Action messages sent to the robot, without screenshot requests."""
        return [
            data
            for _, data in self.sent_messages
            if isinstance(data, dict) and data.get("type") == "action"
        ]

    async def send_json(self, data: Any) -> None:
        if self.closed:
            raise RuntimeError("WebSocket is closed")
        self.sent_messages.append(("json", data))

    async def receive_bytes(self) -> bytes:
        if self.closed:
            raise RuntimeError("WebSocket is closed")
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        if not self._responses:
            # Simulate lack of response (would hang); raise to surface unexpected path
            raise RuntimeError("No response bytes available")
        return self._responses.pop(0)

    async def receive_json(self) -> dict[str, Any]:
        if self.closed:
            raise RuntimeError("WebSocket is closed")
        return {"success": self.action_success}

    async def close(self) -> None:
        self.closed = True
