import asyncio
import base64
from io import BytesIO

import cv2
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from PIL import Image
from skimage.metrics import structural_similarity as ssim
from strands import ToolContext, tool

IMAGE_SIMILARITY_THRESHOLD = 0.95  # Threshold for image similarity (0 to 1)


@tool(description="Convert an image file to a base64-encoded string.")
def image_to_base64(image_path: str) -> str:
    """
    Convert an image file to a base64-encoded string.

    Args:
        image_path (str): Path to the image file to convert to base64

    Returns:
        base64 string or error message

        Success: Returns the base64-encoded JPEG image as text.
        Error: Returns information about what went wrong.
    """
    if not image_path:
        return "image_path is required"

    try:
        with open(image_path, "rb") as image_file:
            # convert to jpeg format
            pil_image = Image.open(image_file)
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            # Save the image to a bytes buffer
            buffer = BytesIO()
            pil_image.save(buffer, format="JPEG")

            encoded_string = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return encoded_string
    except Exception as e:
        return str(e)


@tool(
    description="Take a screenshot and return it as a base64-encoded string.",
    context=True,
)
async def take_screenshot(
    tool_context: ToolContext,
) -> list[dict[str, dict[str, str | dict[str, bytes]]]]:
    """
    Take a screenshot and return it as a base64-encoded string.

    Args:
        (no inputs required) - tool input can be empty

    Returns:
        Dictionary containing Image:
        {"image": {"format":"JPEG","source":{"bytes": b"..."}}}

        Success: Returns the screenshot bytes in the content as an image object.
        Error: Returns information about what went wrong.
    """

    assert "websocket" in tool_context.invocation_state, (
        "WebSocket connection is required in tool context for taking screenshot."
    )
    websocket = tool_context.invocation_state["websocket"]

    try:
        return [
            {
                "image": {
                    "format": "JPEG",
                    "source": {"bytes": await screenshot_bytes(websocket)},
                }
            }
        ]
    except WebSocketDisconnect as _:
        raise
    except Exception as e:
        raise Exception(f"Error taking screenshot: {str(e)}")


async def compare_images(
    before_image: bytes, expected_change: bool, websocket: WebSocket
) -> bool:
    """
    Compare two images and determine if they are identical.

    Args:
        before_image (bytes): The image bytes taken before the robot action. This one should be present in the chat history.
        expected_change (bool): Whether a change is expected between the two images.

    Returns:
        bool: True if the comparison matches the expectation, False otherwise.
    """
    try:
        after_image_cv2 = cv2.imdecode(
            np.frombuffer(await screenshot_bytes(websocket), np.uint8),
            cv2.IMREAD_GRAYSCALE,
        )
        before_image_cv2 = cv2.imdecode(
            np.frombuffer(before_image, np.uint8), cv2.IMREAD_GRAYSCALE
        )
        # assert before_image.shape == after_image_cv2.shape, (
        #     "Images must be the same size."
        # )

        # Compute SSIM between two images
        ssim_index = ssim(
            before_image_cv2,
            after_image_cv2,
            full=False,
            multichannel=True,
        )[0]

        return (ssim_index < IMAGE_SIMILARITY_THRESHOLD) == expected_change

    except WebSocketDisconnect as _:
        raise
    except Exception as _:
        raise ValueError(
            "Error comparing images. Use the take_screenshot() tool and judge the outcome yourself"
        )


async def request_remote_screenshot(
    websocket: WebSocket, timeout: float = 15.0
) -> bytes:
    """
    Send a request over the provided WebSocket and wait for the client to send back a screenshot.

    The client may respond in one of the following ways:
    - send bytes directly (use `await websocket.receive_bytes()`)
    - send a text message containing a base64-encoded image
    - send a JSON message containing an image under keys like `image` or `image_base64`

    Args:
        websocket (WebSocket): Active FastAPI WebSocket connection to the client.
        message (str): Message payload to send to the client asking for a screenshot.
        timeout (float): Seconds to wait for the client's response.

    Returns:
        bytes: Raw image bytes (JPEG/PNG) as received or decoded from base64.

    Raises:
        TimeoutError: If no response is received within `timeout` seconds.
        RuntimeError: For unexpected message formats or disconnections.
    """

    await websocket.send_json({"type": "screenshot", "content": ""})

    try:
        data = await asyncio.wait_for(websocket.receive_bytes(), timeout=timeout)
        return data
    except WebSocketDisconnect as _:
        raise
    except TimeoutError:
        raise TimeoutError("Timed out waiting for screenshot from client")
    except Exception as e:
        raise RuntimeError(f"Unable to interpret client response as image: {e}")


async def screenshot_bytes(websocket: WebSocket) -> bytes:
    """
    Take a screenshot and return it as bytes.

    Args:
        websocket (WebSocket): WebSocket connection to RPA robot

    Returns:
        bytes: Screenshot image data in bytes.

    Usage:
        screenshot_data = await screenshot_bytes(websocket)
    """
    return await request_remote_screenshot(websocket)
