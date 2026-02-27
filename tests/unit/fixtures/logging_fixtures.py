"""Logging model fixtures for unit tests.

These keep router tests readable by centralizing common DB setup.
"""

from typing import Callable
from uuid import UUID

import pytest
from sqlmodel import Session

from database.agents.models import Agent
from database.keys.models import RobotKey
from database.logging.models import AgentTrace, GUITrace, RobotException, ToolTrace
from database.tools.models import Tool
from security.utils import robot_key_hash


@pytest.fixture
def make_robot_key(session: Session):
    def _make_robot_key(
        *,
        name: str = "Test Key",
        enabled: bool = True,
        key_raw: str | None = None,
    ) -> RobotKey:
        if key_raw is None:
            key_raw = f"test-key-{UUID().hex[:8]}"
        key = RobotKey(
            name=name,
            description=None,
            enabled=enabled,
            key_hash=robot_key_hash(key_raw),
            key_last4=key_raw[-4:],
        )
        session.add(key)
        session.commit()
        session.refresh(key)
        return key

    return _make_robot_key


@pytest.fixture
def make_robot_exception(session: Session):
    def _make_robot_exception(
        *,
        exception_details: dict[str, object] | None = None,
        robot_key_id: UUID | None = None,
    ) -> RobotException:
        rex = RobotException(
            exception_details=exception_details or {"msg": "boom"},
            robot_key_id=robot_key_id,
        )
        session.add(rex)
        session.commit()
        session.refresh(rex)
        return rex

    return _make_robot_exception


@pytest.fixture
def mock_robot_exception(
    make_robot_exception: Callable[..., RobotException],
) -> RobotException:
    return make_robot_exception()


@pytest.fixture
def make_agent_trace(session: Session):
    def _make_agent_trace(
        *,
        agent: Agent,
        inputs: dict[str, object] | None = None,
        robot_exception_id: UUID | None = None,
    ) -> AgentTrace:
        trace = AgentTrace(
            agent_id=agent.id,
            inputs=inputs or {},
            robot_exception_id=robot_exception_id,
        )
        session.add(trace)
        session.commit()
        session.refresh(trace)
        return trace

    return _make_agent_trace


@pytest.fixture
def mock_agent_trace(
    make_agent_trace: Callable[..., AgentTrace],
    mock_agent: Agent,
) -> AgentTrace:
    return make_agent_trace(agent=mock_agent)


@pytest.fixture
def make_gui_trace(session: Session):
    def _make_gui_trace(
        *,
        agent_trace: AgentTrace,
        action_type: str = "click",
        action_content: dict[str, object] | None = None,
        success: bool = True,
        screenshot_key: str = "screenshot-1",
    ) -> GUITrace:
        gui = GUITrace(
            agent_trace_id=agent_trace.id,
            action_type=action_type,
            action_content=action_content or {"content": "hi", "start_box": [0.1, 0.2]},
            success=success,
            screenshot_key=screenshot_key,
        )
        session.add(gui)
        session.commit()
        session.refresh(gui)
        return gui

    return _make_gui_trace


@pytest.fixture
def mock_gui_trace(
    make_gui_trace: Callable[..., GUITrace],
    mock_agent_trace: AgentTrace,
) -> GUITrace:
    return make_gui_trace(agent_trace=mock_agent_trace)


@pytest.fixture
def make_tool_trace(session: Session):
    def _make_tool_trace(
        *,
        agent_trace: AgentTrace,
        tool: Tool,
        input: dict[str, object] | None = None,
        output: str = "",
        success: bool = True,
    ) -> ToolTrace:
        ttrace = ToolTrace(
            agent_trace_id=agent_trace.id,
            tool_id=tool.id,
            input=input or {},
            output=output,
            success=success,
        )
        session.add(ttrace)
        session.commit()
        session.refresh(ttrace)
        return ttrace

    return _make_tool_trace


@pytest.fixture
def mock_tool_trace(
    make_tool_trace: Callable[..., ToolTrace],
    mock_agent_trace: AgentTrace,
    mock_tool: Tool,
) -> ToolTrace:
    return make_tool_trace(agent_trace=mock_agent_trace, tool=mock_tool)
