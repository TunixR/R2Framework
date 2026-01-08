import types
from typing import Any, Callable, List, Literal, Tuple

from pydantic import BaseModel, ValidationError
from strands.agent.agent import Agent
from strands.hooks import (
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    MessageAddedEvent,
)
from strands.types.content import ContentBlock
from strands.types.tools import ToolResult


class FakeRegistry:
    """
    Minimal stand-in for HookRegistry that records added callbacks.

    We don't rely on specific event classes from strands.hooks;
    we just store whatever is passed in by the hook provider.
    """

    def __init__(self):
        # Each entry: (event_type, callback)
        self.callbacks: List[Tuple[Any, Callable]] = []

    def add_callback(self, event_type: Any, callback: Callable):
        self.callbacks.append((event_type, callback))


class FakeBeforeInvocationEvent(BeforeInvocationEvent):
    """Fake event used to trigger hooks for the invocation start."""

    def __init__(self):
        self.agent = Agent()


class FakeBeforeToolCallEvent(BeforeToolCallEvent):
    """
    Fake event used to call intercept_tool.

    Attributes:
        tool_use: dict with tool 'name'
        cancel_tool: optional str message set by hook
    """

    def __init__(self, tool_name: str, input_value: Any = None):
        self.tool_use = {"name": tool_name, "input": input_value, "toolUseId": ""}
        self.cancel_tool = False


class FakeAfterToolCallEvent(AfterToolCallEvent):
    """
    Fake event used to call intercept_response.

    Attributes:
        tool_use: dict with tool 'name'
        exception: the exception raised in tool call (or None)
        result: dict representing a tool result payload
    """

    def __init__(
        self,
        tool_name: str,
        exception: Exception | None,
        result: ToolResult | None = None,
    ):
        self.tool_use = {"name": tool_name, "input": None, "toolUseId": ""}
        self.exception = exception
        self.result = result or {"status": "success", "content": [], "toolUseId": ""}


class FakeMessageAddedEvent(MessageAddedEvent):
    """
    Fake event used to call AgentLoggingHook.log_message.

    Attributes:
        message: dict with 'role' and 'content'
    """

    def __init__(
        self,
        role: Literal["user", "assistant"] = "assistant",
        content: list[ContentBlock] | None = None,
    ):
        self.message = {
            "role": role,
            "content": content or [],
        }


# Helpers to generate a ValidationError in a deterministic way


class SampleModel(BaseModel):
    value: int


def make_validation_error() -> ValidationError:
    try:
        # This will raise a ValidationError (value expects int, not str)
        SampleModel(value="not-an-int")  # type: ignore
    except ValidationError as e:
        return e
    raise AssertionError("Expected ValidationError was not raised")


def is_bound_method_of(obj: Any, fn: Callable) -> bool:
    """
    Utility to check a callback is a bound method of a given object instance.
    """
    return isinstance(fn, types.MethodType) and getattr(fn, "__self__", None) is obj
