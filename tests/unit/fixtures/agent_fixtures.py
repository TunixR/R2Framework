"""
Agent fixtures for unit tests.
"""

import uuid

import pytest
from sqlmodel import Session

from database.agents.models import Agent, AgentType
from database.provider.models import Router


@pytest.fixture
def mock_agent(session: Session, mock_router: Router):
    """Create a mock Agent record for testing."""
    agent = Agent(
        id=uuid.uuid4(),
        name="Test Agent",
        prompt="This is a test agent.",
        input_type=Agent.InputType.TEXT,
        description="A mock agent for testing.",
        router_id=mock_router.id,
        enabled=True,
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent


@pytest.fixture
def gateway_agent(session: Session, mock_router: Router) -> Agent:
    """Create a Gateway Orchestrator agent for recovery websocket tests."""
    agent = Agent(
        name="Gateway Orchestrator",
        description="Routes recovery",
        prompt="prompt",
        response_model=None,
        input_type=Agent.InputType.TEXT,
        enabled=True,
        router_id=mock_router.id,
        type=AgentType.GatewayAgent,
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent
