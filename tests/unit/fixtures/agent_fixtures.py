"""
Agent fixtures for unit tests.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlmodel import Session

from database.agents.models import Agent, AgentType
from database.provider.models import Router


@pytest.fixture
def make_agent(session: Session) -> Callable[..., Agent]:
    """Return a factory that persists an agent wired to the given router."""

    def _make_agent(
        *,
        router: Router,
        input_type: Agent.InputType = Agent.InputType.TEXT,
        name: str = "Test Agent",
        description: str = "A mock agent for testing.",
        prompt: str = "This is a test agent.",
        type: AgentType = AgentType.Agent,
        **overrides: Any,
    ) -> Agent:
        agent = Agent(
            id=uuid.uuid4(),
            name=name,
            prompt=prompt,
            input_type=input_type,
            description=description,
            router=router,
            router_id=router.id,
            enabled=True,
            type=type,
            **overrides,
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)
        return agent

    return _make_agent


@pytest.fixture
def mock_agent(make_agent: Callable[..., Agent], mock_router: Router) -> Agent:
    """Create a mock Agent record for testing."""
    return make_agent(router=mock_router)


@pytest.fixture
def gateway_agent(make_agent: Callable[..., Agent], mock_router: Router) -> Agent:
    """Create a Gateway Orchestrator agent for recovery websocket tests."""
    return make_agent(
        router=mock_router,
        name="Gateway Orchestrator",
        description="Routes recovery",
        prompt="prompt",
        response_model=None,
        type=AgentType.GatewayAgent,
    )
