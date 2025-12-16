import asyncio
from io import BytesIO
from typing import Any, List

import pytest
from PIL import Image

# Import the functions under test
from agent_tools.image import (
    request_remote_screenshot,
    take_screenshot,
)

# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def make_test_image_bytes(color=(255, 0, 0), size=(16, 16), fmt="JPEG") -> bytes:
    """
    Create an in-memory image and return its encoded bytes.
    """
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class FakeWebSocket:
    """
    Minimal async fake of FastAPI WebSocket sufficient for testing screenshot tools.

    Behaviors implemented:
    - send_json: records outbound JSON messages
    - receive_bytes: returns queued byte responses, optionally delayed
    """

    def __init__(self, responses: List[bytes], delay: float = 0.0):
        self._responses = list(responses)
        self._delay = delay
        self.sent_messages: List[Any] = []
        self.closed = False

    async def send_json(self, data):
        # Simulate send latency negligible for tests
        if self.closed:
            raise RuntimeError("WebSocket is closed")
        self.sent_messages.append(("json", data))

    async def receive_bytes(self):
        if self.closed:
            raise RuntimeError("WebSocket is closed")
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        if not self._responses:
            # Simulate lack of response (would hang); raise to surface unexpected path
            raise RuntimeError("No response bytes available")
        return self._responses.pop(0)

    async def close(self):
        self.closed = True


class StubToolContext:
    """
    Minimal stub matching the attribute usage inside take_screenshot.
    """

    def __init__(self, websocket):
        self.invocation_state = {"websocket": websocket}


# ---------------------------------------------------------------------------
# Tests: request_remote_screenshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_remote_screenshot_success():
    img_bytes = make_test_image_bytes()
    ws = FakeWebSocket([img_bytes])

    received = await request_remote_screenshot(ws, timeout=0.5)  # type: ignore

    # Validate bytes integrity
    assert received == img_bytes
    # Validate JSON request was sent first
    assert ws.sent_messages, (
        "Expected a JSON request to be sent before receiving bytes."
    )
    msg_type, payload = ws.sent_messages[0]
    assert msg_type == "json"
    assert payload.get("type") == "screenshot"


@pytest.mark.asyncio
async def test_request_remote_screenshot_timeout():
    # Provide a delayed response longer than timeout to trigger TimeoutError
    img_bytes = make_test_image_bytes()
    ws = FakeWebSocket([img_bytes], delay=0.2)  # delay > timeout below

    with pytest.raises(TimeoutError) as e:
        await request_remote_screenshot(ws, timeout=0.05)  # type: ignore
    assert "Timed out" in str(e.value)


@pytest.mark.asyncio
async def test_request_remote_screenshot_unexpected_format():
    """
    Simulate websocket having no responses causing a runtime error pathway
    (not the timeout path).
    """
    ws = FakeWebSocket([])

    # The underlying implementation catches generic exceptions and raises RuntimeError.
    # We assert that a RuntimeError surfaces (not TimeoutError).
    with pytest.raises(RuntimeError) as e:
        # Use a generous timeout so underlying error is raised immediately
        await request_remote_screenshot(ws, timeout=0.2)  # type: ignore
    assert "Unable to interpret client response" in str(e.value)


# ---------------------------------------------------------------------------
# Tests: take_screenshot (wrapper around screenshot_bytes/request_remote_screenshot)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_take_screenshot_success_structure_and_content():
    img_bytes = make_test_image_bytes(color=(0, 128, 255))
    ws = FakeWebSocket([img_bytes])
    ctx = StubToolContext(ws)

    result = await take_screenshot(ctx)  # type: ignore

    # Expected list with single image dict
    assert isinstance(result, list) and len(result) == 1
    payload = result[0]
    assert "image" in payload
    image_obj = payload["image"]
    assert image_obj.get("format") == "JPEG"
    source = image_obj.get("source", {})
    returned_bytes = source.get("bytes")
    assert isinstance(returned_bytes, (bytes, bytearray))
    assert returned_bytes == img_bytes


# EDGE CASES. Invalid websocket


@pytest.mark.asyncio
async def test_take_screenshot_missing_websocket():
    class BadContext:
        def __init__(self):
            self.invocation_state = {}  # Missing websocket

    bad_ctx = BadContext()
    with pytest.raises(AssertionError) as e:
        await take_screenshot(bad_ctx)  # type: ignore
    assert "WebSocket connection is required" in str(e.value)


@pytest.mark.asyncio
async def test_take_screenshot_closed_websocket():
    ws = FakeWebSocket([])
    await ws.close()  # Close before use
    ctx = StubToolContext(ws)
    with pytest.raises(Exception) as e:
        await take_screenshot(ctx)  # type: ignore
    assert "Error taking screenshot: WebSocket is closed" in str(e.value)


@pytest.mark.asyncio
async def test_take_screenshot_error_propagation_runtime():
    """
    Force underlying request_remote_screenshot to raise RuntimeError and assert
    tool returns an error text response rather than image.
    """
    # FakeWebSocket with no responses triggers RuntimeError path
    ws = FakeWebSocket([])
    ctx = StubToolContext(ws)

    with pytest.raises(Exception) as e:
        await take_screenshot(ctx)  # type: ignore
    assert "Error taking screenshot" in str(e.value)
