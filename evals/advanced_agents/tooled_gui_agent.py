"""Tool-based GUI recovery agent.

This module implements a GUI recovery agent that interacts with the UI through
structured tool calls instead of parsing free-form text output. Each action
(click, type, scroll, etc.) is a Strands tool that dispatches the action over
WebSocket, waits for the client result, records a GUI trace, and returns a
fresh screenshot for the model to reason about.

Coordinate system
-----------------
Tools accept ``start_box`` / ``end_box`` as lists of floats. Values may be
absolute pixel coordinates in smart-resized image space (> 1.0) or already
normalized to [0.0, 1.0]. ``_normalize_box`` converts absolute coords to
the normalized form expected by the WebSocket client.
"""

# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: Apache-2.0
import asyncio
import math
from io import BytesIO
from typing import Any

from fastapi import WebSocketDisconnect, WebSocket
from PIL import Image
from strands import Agent, ToolContext, tool
from strands.models.openai import OpenAIModel
from strands.types.content import ContentBlock, Messages
from strands.types.tools import ToolResult

from agent_tools.image import screenshot_bytes
from prompts.gui_agent import TOOLED_GUI_AGENT_PROMPT
from settings import (
    PROVIDER_API_BASE,
    PROVIDER_API_KEY,
    PROVIDER_GROUNDING_MODEL,
)

IMAGE_FACTOR = 28
MIN_PIXELS = 100 * 28 * 28
MAX_PIXELS = 16384 * 28 * 28
MAX_RATIO = 200


def round_by_factor(number: float, factor: int) -> int:
    """Returns the closest integer to 'number' that is divisible by 'factor'."""
    return round(number / factor) * factor


def ceil_by_factor(number: float, factor: int) -> int:
    """Returns the smallest integer greater than or equal to 'number' that is divisible by 'factor'."""
    return math.ceil(number / factor) * factor


def floor_by_factor(number: float, factor: int) -> int:
    """Returns the largest integer less than or equal to 'number' that is divisible by 'factor'."""
    return math.floor(number / factor) * factor


def smart_resize(
    height: int,
    width: int,
    factor: int = IMAGE_FACTOR,
    min_pixels: int = MIN_PIXELS,
    max_pixels: int = MAX_PIXELS,
) -> tuple[int, int]:
    """Rescale image dimensions so that:

    1. Both dimensions are divisible by *factor*.
    2. Total pixel count stays within [*min_pixels*, *max_pixels*].
    3. Aspect ratio is preserved as closely as possible.
    """
    if max(height, width) / min(height, width) > MAX_RATIO:
        raise ValueError(
            f"absolute aspect ratio must be smaller than {MAX_RATIO}, got {max(height, width) / min(height, width)}"
        )
    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = floor_by_factor(height / beta, factor)
        w_bar = floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
    return h_bar, w_bar


def _normalize_box(
    box: list[float], image_width: int, image_height: int
) -> list[float]:
    """Normalize bounding-box coordinates to [0.0, 1.0].

    If any value in *box* exceeds 1.0 the coordinates are treated as absolute
    pixel values in smart-resized image space and divided by the corresponding
    dimension (alternating x/y/x/y pattern). An already-normalized box is
    returned unchanged.
    """
    if not box:
        return box
    if max(box) > 1.0:
        return [
            coord / (image_width if i % 2 == 0 else image_height)
            for i, coord in enumerate(box)
        ]
    return box


async def _execute_gui_action(
    action_type: str,
    action_inputs: dict[str, Any],
    tool_context: ToolContext,
) -> ToolResult:
    """Dispatch one GUI action over WebSocket, record a trace, and return a fresh screenshot.

    Updates ``tool_context.invocation_state["current_image"]`` and
    ``tool_context.invocation_state["image_size"]`` in-place so subsequent
    tool calls see the latest screen dimensions.

    Raises:
        WebSocketDisconnect: propagated as-is when the client disconnects.
        RuntimeError: when the client reports action failure.
    """
    state = tool_context.invocation_state
    websocket = state["websocket"]
    # hook: AgentLoggingHook = state["hook"]
    # current_image: bytes = state["current_image"]

    # started_at = datetime.now()
    await websocket.send_json(
        {
            "type": "action",
            "content": {"action_type": action_type, "action_inputs": action_inputs},
        }
    )
    try:
        result = await websocket.receive_json()
    except WebSocketDisconnect:
        raise
    # finished_at = datetime.now()

    success = bool(result.get("success", False))
    # await hook.register_gui_trace(
    #     action_type, action_inputs, current_image, started_at, finished_at, success
    # )

    if not success:
        raise RuntimeError(
            f"Action '{action_type}' failed on client side. Inputs: {action_inputs}"
        )

    # Brief pause so the UI can settle before the next screenshot.
    await asyncio.sleep(0.5)

    new_image = await screenshot_bytes(websocket)
    new_w_px, new_h_px = Image.open(BytesIO(new_image)).size  # PIL: (width, height)
    smart_h, smart_w = smart_resize(new_h_px, new_w_px)

    state["current_image"] = new_image
    state["image_size"] = (smart_w, smart_h)

    return {
        "status": "success",
        "content": [{"image": {"format": "jpeg", "source": {"bytes": new_image}}}],
    }  # pyright:  ignore[reportReturnType]


# ---------------------------------------------------------------------------
# GUI action tools
# ---------------------------------------------------------------------------


@tool(name="click", description="Left-click on a UI element.", context=True)
async def click(
    start_box: list[float],
    tool_context: ToolContext,
) -> ToolResult:
    """Left single click at the specified screen position.

    Args:
        start_box: Bounding box [x1, y1, x2, y2] or point [x, y]. May be
            absolute pixel coords (> 1.0) or normalized [0.0, 1.0].
    """
    image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
    box = _normalize_box(start_box, image_size[0], image_size[1])
    return await _execute_gui_action("left_single", {"start_box": box}, tool_context)


@tool(
    name="double_click", description="Double left-click on a UI element.", context=True
)
async def double_click(
    start_box: list[float],
    tool_context: ToolContext,
) -> ToolResult:
    """Left double click at the specified screen position.

    Args:
        start_box: Bounding box [x1, y1, x2, y2] or point [x, y]. May be
            absolute pixel coords (> 1.0) or normalized [0.0, 1.0].
    """
    image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
    box = _normalize_box(start_box, image_size[0], image_size[1])
    return await _execute_gui_action("left_double", {"start_box": box}, tool_context)


@tool(name="right_click", description="Right-click on a UI element.", context=True)
async def right_click(
    start_box: list[float],
    tool_context: ToolContext,
) -> ToolResult:
    """Right single click at the specified screen position.

    Args:
        start_box: Bounding box [x1, y1, x2, y2] or point [x, y]. May be
            absolute pixel coords (> 1.0) or normalized [0.0, 1.0].
    """
    image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
    box = _normalize_box(start_box, image_size[0], image_size[1])
    return await _execute_gui_action("right_single", {"start_box": box}, tool_context)


@tool(
    name="hover",
    description="Move the mouse cursor over a UI element without clicking.",
    context=True,
)
async def hover(
    start_box: list[float],
    tool_context: ToolContext,
) -> ToolResult:
    """Move the mouse to the specified screen position.

    Args:
        start_box: Bounding box [x1, y1, x2, y2] or point [x, y]. May be
            absolute pixel coords (> 1.0) or normalized [0.0, 1.0].
    """
    image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
    box = _normalize_box(start_box, image_size[0], image_size[1])
    return await _execute_gui_action("hover", {"start_box": box}, tool_context)


@tool(
    name="type_text",
    description="Type text into the currently focused input field.",
    context=True,
)
async def type_text(
    content: str,
    tool_context: ToolContext,
) -> ToolResult:
    """Type text into the currently active input field.

    Args:
        content: Text to type. Use \\n at the end to submit (press Enter).
    """
    return await _execute_gui_action("type", {"content": content}, tool_context)


@tool(
    name="hotkey",
    description="Press a keyboard shortcut (e.g. 'ctrl c', 'alt f4'). Split keys with a space, use lowercase, max 3 keys.",
    context=True,
)
async def hotkey(
    key: str,
    tool_context: ToolContext,
) -> ToolResult:
    """Press a keyboard shortcut.

    Args:
        key: Space-separated key names in lowercase, e.g. 'ctrl v' or 'ctrl shift s'.
    """
    return await _execute_gui_action("hotkey", {"hotkey": key}, tool_context)


@tool(name="key_down", description="Press and hold a keyboard key.", context=True)
async def key_down(
    key: str,
    tool_context: ToolContext,
) -> ToolResult:
    """Hold a key down (keydown event).

    Args:
        key: Key name, e.g. 'shift', 'ctrl', 'alt'.
    """
    return await _execute_gui_action("keydown", {"key": key}, tool_context)


@tool(
    name="key_up",
    description="Release a keyboard key that was held down.",
    context=True,
)
async def key_up(
    key: str,
    tool_context: ToolContext,
) -> ToolResult:
    """Release a held key (keyup event).

    Args:
        key: Key name, e.g. 'shift', 'ctrl', 'alt'.
    """
    return await _execute_gui_action("keyup", {"key": key}, tool_context)


@tool(
    name="scroll",
    description="Scroll in the given direction ('up', 'down', 'left', 'right'), optionally at a screen location.",
    context=True,
)
async def scroll(
    direction: str,
    start_box: list[float] | None,
    tool_context: ToolContext,
) -> ToolResult:
    """Scroll the mouse wheel.

    Args:
        direction: One of 'up', 'down', 'left', 'right'.
        start_box: Optional position [x1, y1, x2, y2] or [x, y]. Pass None to
            scroll at the current cursor position. May be absolute pixel coords
            (> 1.0) or normalized [0.0, 1.0].
    """
    action_inputs: dict[str, Any] = {"direction": direction}
    if start_box is not None:
        image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
        action_inputs["start_box"] = _normalize_box(
            start_box, image_size[0], image_size[1]
        )
    return await _execute_gui_action("scroll", action_inputs, tool_context)


@tool(
    name="drag",
    description="Click and drag from one screen location to another.",
    context=True,
)
async def drag(
    start_box: list[float],
    end_box: list[float],
    tool_context: ToolContext,
) -> ToolResult:
    """Click and drag between two screen positions.

    Args:
        start_box: Drag origin [x1, y1, x2, y2]. May be absolute (> 1.0) or normalized.
        end_box: Drag destination [x1, y1, x2, y2]. May be absolute (> 1.0) or normalized.
    """
    image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
    s_box = _normalize_box(start_box, image_size[0], image_size[1])
    e_box = _normalize_box(end_box, image_size[0], image_size[1])
    return await _execute_gui_action(
        "drag", {"start_box": s_box, "end_box": e_box}, tool_context
    )


@tool(
    name="finished",
    description="Signal that the recovery task is complete.",
    context=True,
)
async def finished(
    content: str,
    tool_context: ToolContext,
) -> str:
    """Mark the task as complete and persist the final GUI trace.

    Args:
        content: Summary of what was accomplished.
    """
    # state = tool_context.invocation_state
    # hook: AgentLoggingHook = state["hook"]
    # current_image: bytes = state["current_image"]
    # now = datetime.now()
    # await hook.register_gui_trace(
    #     "finished", {"content": content}, current_image, now, now, success=True
    # )
    return f"Task completed: {content}. You may stop talking right now. Please do not respond further, just stop generating any further text and finish your turn."


GUI_TOOLS = [
    click,
    double_click,
    right_click,
    hover,
    type_text,
    hotkey,
    key_down,
    key_up,
    scroll,
    drag,
    finished,
]


# ---------------------------------------------------------------------------
# Outer tool consumed by the parent agent
# ---------------------------------------------------------------------------


# @tool(
#     name="standalone_tooled_guiagent",
#     description="A element and action ground model for UI tasks.",
#     context=True,
# )
async def standalone_tooled_guiagent(
    task: str,
    variables: dict[str, Any],
    ui_log: list[Any],
    errored_act: dict[str, Any],
    model: str,
    # tool_context: ToolContext,
    websocket: WebSocket,
) -> list[list[ContentBlock]] | str:
    """Run the tool-based GUI recovery agent for a single recovery session.

    Args:
        task: Concise recovery objective and failure context.
        variables: Process variables and known runtime values.
        ui_log: Ordered UI execution history leading up to failure.
        errored_act: Structured details for the failed activity.
        model: Model-generated textual context for failure and recovery intent.

    Returns:
        Ordered list of assistant message content blocks from the inner agent,
        or a plain error string when an unexpected exception occurs.
    """
    # if "websocket" not in tool_context.invocation_state:
    #     raise ValueError("WebSocket must be provided in tool context")

    instruction = f"""
Task: {task}
UI Log: {ui_log}
Errored Activity: {errored_act}
Variables: {variables}
Model Context: {model}
"""

    # websocket = tool_context.invocation_state["websocket"]
    image = await screenshot_bytes(websocket)
    w_px, h_px = Image.open(BytesIO(image)).size  # PIL returns (width, height)
    smart_h, smart_w = smart_resize(h_px, w_px)

    # hook = AgentLoggingHook(
    #     agent_id=uuid.UUID("2bd92474-5486-4caa-b59e-dde1aa739b88"),
    #     invocation_state=tool_context.invocation_state,
    #     parent_trace_id=tool_context.invocation_state.get("parent_trace_id", None),
    #     is_gui_agent=True,
    # )

    inner_state = {
        "websocket": websocket,
        "current_image": image,
        "image_size": (smart_w, smart_h),
    }
    # inner_state = dict(tool_context.invocation_state) | {
    #     "hook": hook,
    #     "current_image": image,
    #     "image_size": (smart_w, smart_h),
    # }

    messages: Messages = [
        {
            "role": "user",
            "content": [
                {"text": TOOLED_GUI_AGENT_PROMPT.format(instruction=instruction)},
                {"image": {"format": "jpeg", "source": {"bytes": image}}},
            ],
        }
    ]

    agent_model = OpenAIModel(
        client_args={"api_key": PROVIDER_API_KEY, "base_url": PROVIDER_API_BASE},
        model_id=PROVIDER_GROUNDING_MODEL,
    )

    agent = Agent(model=agent_model, messages=messages, tools=GUI_TOOLS)  # type: ignore

    try:
        _ = await agent.invoke_async("", invocation_state=inner_state)

        conversation_history = list(
            map(
                lambda m: m["content"],
                filter(lambda m: m["role"] == "assistant", agent.messages),
            )
        )
        return conversation_history
    except WebSocketDisconnect:
        raise
    except RuntimeError:
        raise
    except Exception as e:
        return str(e)
    # finally:
    #     hook.update_trace(finished=True, cost=-1.0)
