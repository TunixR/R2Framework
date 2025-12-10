from datetime import datetime
from threading import Lock
from typing import Any, Dict, override
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlmodel import Session
from strands.hooks import (
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
    MessageAddedEvent,
)


class LimitToolCounts(HookProvider):
    """Limits the number of times tools can be called per agent invocation"""

    def __init__(self, max_tool_counts: dict[str, int]):
        """
        Initializer.

        Args:
            max_tool_counts: A dictionary mapping tool names to max call counts for
                tools. If a tool is not specified in it, the tool can be called as many
                times as desired
        """
        self.max_tool_counts = max_tool_counts
        self.tool_counts = {}
        self._lock = Lock()

    @override
    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeInvocationEvent, self.reset_counts)
        registry.add_callback(BeforeToolCallEvent, self.intercept_tool)
        registry.add_callback(AfterToolCallEvent, self.intercept_response)

    def reset_counts(self, event: BeforeInvocationEvent) -> None:
        with self._lock:
            self.tool_counts = {}

    def intercept_tool(self, event: BeforeToolCallEvent) -> None:
        tool_name = event.tool_use["name"]
        with self._lock:
            max_tool_count = self.max_tool_counts.get(tool_name)
            tool_count = self.tool_counts.get(tool_name, 0) + 1
            self.tool_counts[tool_name] = tool_count

        if max_tool_count and tool_count > max_tool_count:
            event.cancel_tool = (
                f"Tool '{tool_name}' has been invoked too many and is now being throttled. "
                f"DO NOT CALL THIS TOOL ANYMORE "
            )

    def intercept_response(self, event: AfterToolCallEvent):
        # Remove one call if validation exception happened
        tool_name = event.tool_use["name"]
        if (
            event.exception
            and isinstance(event.exception, ValidationError)
            or isinstance(event.exception, TypeError)
        ) or (
            event.result
            and event.result.get("status", "") == "error"
            and (
                "TypeError"
                in next(iter(event.result.get("content", [])), {}).get("text", "")
                or "ValidationError"
                in next(iter(event.result.get("content", [])), {}).get("text", "")
            )
        ):
            with self._lock:
                tool_count = self.tool_counts.get(tool_name, 0) - 1
                self.tool_counts[tool_name] = max(0, tool_count)


class ToolLoggingHook(HookProvider):
    agent_trace_id: UUID
    tools: dict[str, UUID]
    trace_id: UUID

    def __init__(self, agent_trace_id: UUID, tools: dict[str, UUID]):
        """Initializes the ToolLoggingHook.

        Args:
            agent_trace_id: The UUID of the agent trace.
            tools: A dictionary mapping tool names to be logged to their UUIDs.
        """
        self.agent_trace_id = agent_trace_id
        self.tools = tools

    @override
    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.log_tool_call)
        registry.add_callback(AfterToolCallEvent, self.log_tool_response)

    def log_tool_call(self, event: BeforeToolCallEvent) -> None:
        from ..database.general import general_engine
        from ..database.logging.models import ToolTrace

        tool_name = event.tool_use.get("name", "")
        if tool_name not in self.tools:
            return

        with Session(general_engine) as session:
            trace_id = uuid4()
            tool_trace = ToolTrace(
                id=trace_id,
                agent_trace_id=self.agent_trace_id,
                tool_id=self.tools[tool_name],
                input=event.tool_use.get("input", ""),
            )
            session.add(tool_trace)
            session.commit()
            self.trace_id = trace_id

    def log_tool_response(self, event: AfterToolCallEvent) -> None:
        from ..database.general import general_engine
        from ..database.logging.models import ToolTrace

        tool_name = event.tool_use.get("name", "")
        if tool_name not in self.tools:
            return

        with Session(general_engine) as session:
            tool_trace = session.get(ToolTrace, self.trace_id)

            if not tool_trace:
                raise RuntimeError(f"ToolTrace with id {self.trace_id} not found.")

            tool_trace.finished_at = datetime.now()

            if event.exception:
                tool_trace.output = str(event.exception)
                tool_trace.success = False
            else:
                tool_trace.output = next(iter(event.result.get("content", [])), {}).get(
                    "text", ""
                )  # FIXME: Support only text output for now
                tool_trace.success = True

            session.add(tool_trace)
            session.commit()


class AgentLoggingHook(HookProvider):
    parent_agent_id: UUID | None
    agent_id: UUID
    agent_trace_id: UUID
    invocation_state: dict
    messages: list[dict] = []
    is_gui_agent: bool = False

    def __init__(
        self,
        agent_id: UUID,
        invocation_state: dict,
        parent_agent_id: UUID | None = None,
        is_gui_agent: bool = False,
    ):
        """Initializes the AgentLoggingHook.

        Args:
            agent_id: The UUID of the agent.
            invocation_state: The state of the agent invocation.
            parent_agent_id: The UUID of the parent agent, if any.
            is_gui_agent: Whether the agent is a GUI agent.
        """
        self.parent_agent_id = parent_agent_id
        self.agent_id = agent_id
        self.invocation_state = invocation_state
        self.is_gui_agent = is_gui_agent
        # We generate here the id for the agent trace so we can reference it outside
        self.agent_trace_id = uuid4()

    @override
    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeInvocationEvent, self.log_start)
        registry.add_callback(MessageAddedEvent, self.log_message)

    def log_start(self, event: BeforeInvocationEvent) -> None:
        from ..database.general import general_engine
        from ..database.logging.models import AgentTrace, SubAgentTrace

        with Session(general_engine) as session:
            # We first register the agent trace here
            trace = AgentTrace(
                id=self.agent_trace_id,
                agent_id=self.agent_id,
                robot_exception_id=self.invocation_state.get(
                    "robot_exception_id", None
                ),
                inputs=self.invocation_state.get("inputs", {}),
            )
            session.add(trace)

            if self.parent_agent_id:
                sub_trace = SubAgentTrace(
                    session=session,
                    parent_trace_id=self.parent_trace_id,
                    child_trace_id=self.agent_trace_id,
                )
                session.add(sub_trace)

            session.commit()

    def log_message(self, event: MessageAddedEvent) -> None:
        message = {
            "role": event.message.get("role", "unknown"),
            "content": event.message.get(
                "content", []
            ),  # Includes text, toolcalls, images, etc. # TODO: Figure out what to do with this
            "timestamp": datetime.now().isoformat(),
        }

        self.messages.append(message)
        self.update_trace()

    def update_trace(self, finished: bool = False):
        from ..database.general import general_engine
        from ..database.logging.models import AgentTrace

        with Session(general_engine) as session:
            trace = session.get(AgentTrace, self.agent_trace_id)
            if not trace:
                raise RuntimeError(
                    f"AgentTrace with id {self.agent_trace_id} not found."
                )

            text: str = "\n".join(
                map(
                    lambda c: c.get("text", ""),
                    filter(
                        lambda m: m.get("role") == "assistant",
                        self.messages,
                    ),
                )
            )
            trace.output = text
            if finished:
                trace.finished_at = datetime.now()

            session.add(trace)
            session.commit()

    def register_gui_trace(
        self,
        action_type: str,
        action_content: Dict[str, Any],
        screenshot_bytes: bytes,
        success: bool = True,
    ):
        if not self.is_gui_agent:
            raise RuntimeError("Cannot register GUI trace for non-GUI agent.")

        from ..database.general import general_engine
        from ..database.logging.models import GUITrace

        with Session(general_engine) as session:
            screenshot_id = uuid4()
            # TODO: Upload screenshot_bytes to storage with id as name

            gui_trace = GUITrace(
                agent_trace_id=self.agent_trace_id,
                screenshot_id=screenshot_id,
                action_type=action_type,
                action_content=action_content,
                success=success,
            )
            session.add(gui_trace)
            session.commit()
