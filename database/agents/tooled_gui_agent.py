"""Tool-based GUI recovery agent.

This module implements a GUI recovery agent that interacts with the UI through
structured tool calls instead of parsing free-form text output. Each action
(click, type, scroll, etc.) is a Strands tool that dispatches the action over
WebSocket, waits for the client result, records a GUI trace, and returns a
fresh screenshot for the model to reason about.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database.agents.models import Agent

import asyncio
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from fastapi import WebSocketDisconnect
from PIL import Image
from strands import Agent as StrandsAgent
from strands import ToolContext, tool
from strands.types.tools import ToolUse
from strands.types.content import ContentBlock, Messages
from strands.types.tools import ToolResult

from agent_tools.hooks import AgentLoggingHook, MaxGuiImagesHook
from agent_tools.image import screenshot_bytes


class TooledGuiAgent:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.relative_dim = agent.router.relative_dim
        self.original_coords = agent.router.original_coords

    def _box_to_coords(self, box: list[float]) -> tuple[float, float]:
        if len(box) == 2:
            return box[0], box[1]
        return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2

    async def _execute_gui_action(
        self,
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
        hook: AgentLoggingHook = state["hook"]
        current_image: bytes = state["current_image"]

        started_at = datetime.now(timezone.utc)
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
        finished_at = datetime.now(timezone.utc)

        success = bool(result.get("success", False))
        await hook.register_gui_trace(
            action_type, action_inputs, current_image, started_at, finished_at, success
        )

        if not success:
            raise RuntimeError(
                f"Action '{action_type}' failed on client side. Inputs: {action_inputs}"
            )

        # Brief pause so the UI can settle before the next screenshot.
        await asyncio.sleep(1.0)

        new_image = await screenshot_bytes(websocket)
        new_w_px, new_h_px = Image.open(BytesIO(new_image)).size  # PIL: (width, height)

        state["current_image"] = new_image
        state["image_size"] = (new_w_px, new_h_px)

        match self.agent.router.model_name:
            case model if "Holo" in model:
                response = {
                    "status": "success",
                    "content": [
                        {"text": "<observation>\n"},
                        {"image": {"format": "jpeg", "source": {"bytes": new_image}}},
                        {"text": "\n<observation>"},
                    ],
                }
            case _:
                response = {
                    "status": "success",
                    "content": [
                        {"image": {"format": "jpeg", "source": {"bytes": new_image}}}
                    ],
                }

        return response  # pyright:  ignore[reportReturnType]

    # ---------------------------------------------------------------------------
    # GUI action tools
    # ---------------------------------------------------------------------------

    @tool(name="click", description="Left-click on a UI element.", context=True)
    async def click(
        self,
        start_box: list[float],
        tool_context: ToolContext,
    ) -> ToolResult:
        """Left single click at the specified screen position.

        Args:
            start_box: Bounding box [x1, y1, x2, y2] or point [x, y]. May be
                absolute pixel coords (> 1.0) or normalized [0.0, 1.0].
        """
        image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
        box = self.original_coords(
            *self._box_to_coords(start_box), image_size[0], image_size[1]
        )
        return await self._execute_gui_action(
            "left_single", {"start_box": box}, tool_context
        )

    @tool(
        name="double_click",
        description="Double left-click on a UI element.",
        context=True,
    )
    async def double_click(
        self,
        start_box: list[float],
        tool_context: ToolContext,
    ) -> ToolResult:
        """Left double click at the specified screen position.

        Args:
            start_box: Bounding box [x1, y1, x2, y2] or point [x, y]. May be
                absolute pixel coords (> 1.0) or normalized [0.0, 1.0].
        """
        image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
        box = self.original_coords(
            *self._box_to_coords(start_box), image_size[0], image_size[1]
        )
        return await self._execute_gui_action(
            "left_double", {"start_box": box}, tool_context
        )

    @tool(name="right_click", description="Right-click on a UI element.", context=True)
    async def right_click(
        self,
        start_box: list[float],
        tool_context: ToolContext,
    ) -> ToolResult:
        """Right single click at the specified screen position.

        Args:
            start_box: Bounding box [x1, y1, x2, y2] or point [x, y]. May be
                absolute pixel coords (> 1.0) or normalized [0.0, 1.0].
        """
        image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
        box = self.original_coords(
            *self._box_to_coords(start_box), image_size[0], image_size[1]
        )
        return await self._execute_gui_action(
            "right_single", {"start_box": box}, tool_context
        )

    @tool(
        name="hover",
        description="Move the mouse cursor over a UI element without clicking.",
        context=True,
    )
    async def hover(
        self,
        start_box: list[float],
        tool_context: ToolContext,
    ) -> ToolResult:
        """Move the mouse to the specified screen position.

        Args:
            start_box: Bounding box [x1, y1, x2, y2] or point [x, y]. May be
                absolute pixel coords (> 1.0) or normalized [0.0, 1.0].
        """
        image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
        box = self.original_coords(
            *self._box_to_coords(start_box), image_size[0], image_size[1]
        )
        return await self._execute_gui_action("hover", {"start_box": box}, tool_context)

    @tool(
        name="type_text",
        description="Type text into the currently focused input field.",
        context=True,
    )
    async def type_text(
        self,
        content: str,
        tool_context: ToolContext,
    ) -> ToolResult:
        """Type text into the currently active input field.

        Args:
            content: Text to type. Use \\n at the end to submit (press Enter).
        """
        return await self._execute_gui_action(
            "type", {"content": content}, tool_context
        )

    @tool(
        name="hotkey",
        description="Press a keyboard shortcut (e.g. 'ctrl c', 'alt f4'). Split keys with a space, use lowercase, max 3 keys.",
        context=True,
    )
    async def hotkey(
        self,
        key: str,
        tool_context: ToolContext,
    ) -> ToolResult:
        """Press a keyboard shortcut.

        Args:
            key: Space-separated key names in lowercase, e.g. 'ctrl v' or 'ctrl shift s'.
        """
        return await self._execute_gui_action("hotkey", {"hotkey": key}, tool_context)

    @tool(name="key_down", description="Press and hold a keyboard key.", context=True)
    async def key_down(
        self,
        key: str,
        tool_context: ToolContext,
    ) -> ToolResult:
        """Hold a key down (keydown event).

        Args:
            key: Key name, e.g. 'shift', 'ctrl', 'alt'.
        """
        return await self._execute_gui_action("keydown", {"key": key}, tool_context)

    @tool(
        name="key_up",
        description="Release a keyboard key that was held down.",
        context=True,
    )
    async def key_up(
        self,
        key: str,
        tool_context: ToolContext,
    ) -> ToolResult:
        """Release a held key (keyup event).

        Args:
            key: Key name, e.g. 'shift', 'ctrl', 'alt'.
        """
        return await self._execute_gui_action("keyup", {"key": key}, tool_context)

    @tool(
        name="scroll",
        description="Scroll in the given direction ('up', 'down', 'left', 'right'), optionally at a screen location.",
        context=True,
    )
    async def scroll(
        self,
        direction: str,
        start_box: list[float],
        tool_context: ToolContext,
    ) -> ToolResult:
        """Scroll the mouse wheel.

        Args:
            direction: One of 'up', 'down', 'left', 'right'.
            start_box: Position [x1, y1, x2, y2] or [x, y]. Indicates the position of the scrollable area or scrollable element.
                It needs to be precise, within the bounds of what is to be scrolled, either page, list of elements, or specific element.
                May be absolute pixel coords
                (> 1.0) or normalized [0.0, 1.0].
        """
        action_inputs: dict[str, Any] = {"direction": direction}
        image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
        action_inputs["start_box"] = self.original_coords(
            *self._box_to_coords(start_box), image_size[0], image_size[1]
        )
        return await self._execute_gui_action("scroll", action_inputs, tool_context)

    @tool(
        name="drag",
        description="Click and drag from one screen location to another.",
        context=True,
    )
    async def drag(
        self,
        start_box: list[float],
        end_box: list[float],
        tool_context: ToolContext,
    ) -> ToolResult:
        """Click and drag between two screen positions.

        Args:
            start_box: Drag origin [x1, y1, x2, y2] or [x, y]. May be absolute (> 1.0) or normalized.
            end_box: Drag destination [x1, y1, x2, y2] or [x, y]. May be absolute (> 1.0) or normalized.
        """
        image_size: tuple[int, int] = tool_context.invocation_state["image_size"]
        s_box = self.original_coords(
            *self._box_to_coords(start_box), image_size[0], image_size[1]
        )
        e_box = self.original_coords(
            *self._box_to_coords(end_box), image_size[0], image_size[1]
        )
        return await self._execute_gui_action(
            "drag", {"start_box": s_box, "end_box": e_box}, tool_context
        )

    @tool(
        name="wait",
        description="Wait for a specified number of seconds.",
        context=True,
    )
    async def wait(
        self,
        seconds: float,
        tool_context: ToolContext,
    ) -> ToolResult:
        """Wait/pause for the specified duration.

        Args:
            seconds: Number of seconds to wait.
        """
        return await self._execute_gui_action(
            "wait", {"seconds": seconds}, tool_context
        )

    @tool(
        name="finished",
        description="Signal that the recovery task is complete.",
        context=True,
    )
    async def finished(
        self,
        content: str,
        tool_context: ToolContext,
    ) -> str:
        """Mark the task as complete and persist the final GUI trace.

        Args:
            content: Summary of what was accomplished.
        """
        state = tool_context.invocation_state
        hook: AgentLoggingHook = state["hook"]
        current_image: bytes = state["current_image"]
        now = datetime.now(timezone.utc)
        await hook.register_gui_trace(
            "finished", {"content": content}, current_image, now, now, success=True
        )
        tool_context.agent.cancel()
        return f"Task completed: {content}"

    def get_gui_tools(self, variables: dict[str, Any]):
        return [
            self.click,
            self.double_click,
            self.right_click,
            self.hover,
            self.type_text,
            self.hotkey,
            self.key_down,
            self.key_up,
            self.scroll,
            self.drag,
            self.wait,
            self.finished,
            self.create_alter_variable_tool(variables),
        ]

    def create_alter_variable_tool(self, variables: dict[str, Any]):
        @tool(
            name="alter_variable",
            description="Alter the value of a given variable. The value must be JSON serializable",
        )
        async def _alter_variable(
            name: str,
            value: Any,
        ) -> str:
            if name not in variables:
                return f"Error: Variable '{name}' not found."
            variables[name] = value
            return f"Variable '{name}' has been updated to '{value}'."

        return _alter_variable

    # ---------------------------------------------------------------------------
    # Outer tool consumed by the parent agent
    # ---------------------------------------------------------------------------

    @tool(
        name="tooled_guiagent",
        description="A element and action ground model for UI tasks.",
        context=True,
    )
    async def tooled_guiagent(
        self,
        task: str,
        variables: dict[str, Any],
        ui_log: list[Any],
        errored_act: dict[str, Any],
        model: str,
        override_invocation_state: dict[str, Any] | None = None,
        tool_context: ToolContext | None = None,
    ) -> tuple[list[list[ContentBlock]] | str, dict[str, Any]]:
        """Run the tool-based GUI recovery agent for a single recovery session.

        Args:
            task: Concise recovery objective and failure context.
            variables: Process variables and known runtime values.
            ui_log: Ordered UI execution history leading up to failure.
            errored_act: Structured details for the failed activity.
            model: Model-generated textual context for failure and recovery intent.
            override_invocation_state: Optional override for the invocation state.

        Returns:
            Ordered list of assistant message content blocks from the inner agent,
            or a plain error string when an unexpected exception occurs.
        """

        if tool_context is None:
            tool_context = ToolContext(
                tool_use=ToolUse(
                    input={
                        "task": task,
                        "variables": variables,
                        "ui_log": ui_log,
                        "errored_act": errored_act,
                        "model": model,
                    },
                    name="tooled_guiagent",
                    toolUseId="MANUAL",
                    reasoningSignature="",
                ),
                agent=None,
                invocation_state={
                    "inputs": {
                        "task": task,
                        "variables": variables,
                        "ui_log": ui_log,
                        "errored_act": errored_act,
                        "model": model,
                    },
                },
            )

        if override_invocation_state is not None:
            tool_context.invocation_state = override_invocation_state | dict(
                tool_context.invocation_state
            )

        if "websocket" not in tool_context.invocation_state:
            raise ValueError("WebSocket must be provided in tool context")

        instruction = f"""
    Task: {task}
    UI Log: {ui_log}
    Errored Activity: {errored_act}
    Variables: {variables}
    Model Context: {model}
    """

        websocket = tool_context.invocation_state["websocket"]
        image = await screenshot_bytes(websocket)
        w_px, h_px = Image.open(BytesIO(image)).size  # PIL returns (width, height)

        hook = AgentLoggingHook(
            agent_id=self.agent.id,
            invocation_state=tool_context.invocation_state,
            parent_trace_id=tool_context.invocation_state.get("parent_trace_id", None),
            is_gui_agent=True,
        )

        inner_state = dict(tool_context.invocation_state) | {
            "hook": hook,
            "current_image": image,
            "image_size": (w_px, h_px),
        }

        messages: Messages = [
            {
                "role": "user",
                "content": [
                    {"text": self.agent.prompt.format(instruction=instruction)},
                    {"image": {"format": "jpeg", "source": {"bytes": image}}},
                ],
            }
        ]

        agent_model = self.agent.router.get_model()

        agent = StrandsAgent(  # type: ignore
            model=agent_model,
            tools=self.get_gui_tools(variables),
            hooks=[hook, MaxGuiImagesHook()],
        )

        if tool_context.agent is None:
            tool_context.agent = agent

        try:
            _ = await agent.invoke_async(messages, invocation_state=inner_state)

            conversation_history = list(
                map(
                    lambda m: m["content"],
                    filter(lambda m: m["role"] == "assistant", agent.messages),
                )
            )
            return conversation_history, variables
        except WebSocketDisconnect:
            raise
        except RuntimeError:
            raise
        except Exception as e:
            return str(e), variables
        finally:
            hook.update_trace(finished=True, cost=-1.0)
