"""Logging model fixtures for unit tests.

These keep router tests readable by centralizing common DB setup.
"""

from typing import Callable
from uuid import UUID

import pytest
from sqlmodel import Session

from database.agents.models import Agent
from database.logging.models import AgentTrace, GUITrace, RobotException


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
