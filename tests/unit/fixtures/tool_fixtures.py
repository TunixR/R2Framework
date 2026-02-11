"""
Tool fixtures for unit tests.
"""

import uuid

import pytest
from sqlmodel import Session
from strands import tool

from database.tools.models import Tool


@tool
def _mock_tool_impl():  # pyright: ignore[reportUnusedFunction]
    """A simple mock implementation for a tool."""
    return "Mock tool response"


@pytest.fixture
def mock_tool(session: Session):
    """Create a mock tool for testing."""
    tool = Tool(
        id=uuid.uuid4(),
        name="Test Tool",
        description="A mock tool for testing.",
        fn_module="tests.unit.fixtures.tool_fixtures._mock_tool_impl",
    )
    session.add(tool)
    session.commit()
    session.refresh(tool)
    return tool
