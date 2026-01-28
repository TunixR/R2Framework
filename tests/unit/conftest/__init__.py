"""
Pytest configuration and fixtures for an isolated in-memory test database.

This file provides:
- An in-memory SQLite engine (instead of Postgres) for fast, ephemeral tests.
- Automatic model import so SQLModel metadata is complete.
- Database creation & teardown around each test function for isolation.
- Session fixture returning a live SQLModel Session bound to the test engine.
- Optional population of core data (tools, routers, agents) to exercise functionality.

Usage in tests:
    def test_example(db_session):
        # db_session is a sqlmodel.Session
        result = db_session.exec(select(Agent)).all()
        assert result == [...]

You can disable auto-population by marking a test with:
    @pytest.mark.no_populate

If you need only schema without data:
    @pytest.mark.schema_only

Environment:
The real code loads settings from environment. For tests we inject minimal
fake settings to allow routers & agents to be created without external calls.

Note:
Dynamic imports in Tool / Agent models will execute; ensure any referenced
modules exist in the test environment. All referenced modules are part of
the repository so this should succeed.

"""

from __future__ import annotations

import os

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from database.agents.models import *  # noqa: F401,F403
from database.agents.models import Agent  # Explicit import for type hints
from database.auth.models import *  # noqa: F401,F403
from database.populators.agents import populate_agents
from database.populators.routers import populate_routers

# Populators (optional)
from database.populators.tools import populate_tools
from database.provider.models import *  # noqa: F401,F403
from database.tools.models import *  # noqa: F401,F403
from database.tools.models import Tool  # Explicit import for type hints

# Import all models so metadata is populated
from modules.models import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Test configuration constants
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite://"
# Using a pure in-memory SQLite database. Each connection is distinct,
# so we keep a single engine instance for the test session.

# Fake provider values to satisfy populator expectations
FAKE_API_KEY = "test-key"
FAKE_FREE_API_KEY = "test-free-key"
FAKE_API_BASE = "https://fake-provider.test/v1"
FAKE_MODEL = "gpt-4o-mini"
FAKE_VISION_MODEL = "gpt-4o-vision-mini"
FAKE_VISION_TOOL_MODEL = "gpt-4o-vision-tool"
FAKE_GROUNDING_MODEL = "gpt-4o-grounding"


def _inject_test_env():
    """
    Inject environment variables expected by settings / populators.
    """
    os.environ.setdefault("PROVIDER_API_KEY", FAKE_API_KEY)
    os.environ.setdefault("FREE_PROVIDER_API_KEY", FAKE_FREE_API_KEY)
    os.environ.setdefault("PROVIDER_API_BASE", FAKE_API_BASE)
    os.environ.setdefault("PROVIDER_MODEL", FAKE_MODEL)
    os.environ.setdefault("PROVIDER_VISION_MODEL", FAKE_VISION_MODEL)
    os.environ.setdefault("PROVIDER_VISION_TOOL_MODEL", FAKE_VISION_TOOL_MODEL)
    os.environ.setdefault("PROVIDER_GROUNDING_MODEL", FAKE_GROUNDING_MODEL)
    # Scenario toggles
    os.environ.setdefault("UI_ERROR_PLANNING", "true")
    os.environ.setdefault("UI_MID_AGENT", "false")


@pytest.fixture(scope="session")
def engine():
    """
    Provide a shared in-memory SQLite engine for the entire test session.
    """
    _inject_test_env()
    engine = create_engine(
        TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    return engine


@pytest.fixture(autouse=True)
def _setup_db_per_test(request, engine):
    """
    Automatically create all tables before each test and drop them afterward.

    Honors markers:
        @pytest.mark.no_populate -> Skip data population
        @pytest.mark.schema_only -> Create schema only (no data)
    """
    # Create schema
    SQLModel.metadata.create_all(engine)

    populate = True
    if request.node.get_closest_marker("no_populate"):
        populate = False
    if request.node.get_closest_marker("schema_only"):
        populate = False

    if populate:
        # Run selective populators
        populate_tools(engine)
        populate_routers(engine)
        populate_agents(engine)

    yield

    # Teardown
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def db_session(engine) -> Session:
    """
    Return a SQLModel Session bound to the test engine.
    """
    with Session(engine) as session:
        return session


# ---------------------------------------------------------------------------
# Convenience fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def gateway_agent(db_session) -> Agent:
    """
    Return the persisted Gateway Orchestrator agent (if present).
    """
    agent = db_session.exec(
        select(Agent).where(Agent.name == "Gateway Orchestrator")
    ).first()
    assert agent, "Gateway Orchestrator agent not found. Was population skipped?"
    return agent


@pytest.fixture
def ui_exception_handler_agent(db_session) -> Agent:
    """
    Return the persisted UI Exception Handler agent.
    """
    agent = db_session.exec(
        select(Agent).where(Agent.name == "UI Exception Handler")
    ).first()
    assert agent, "UI Exception Handler agent not found. Was population skipped?"
    return agent


@pytest.fixture
def all_tools(db_session) -> list[Tool]:
    """
    Return all registered tools.
    """
    return db_session.exec(select(Tool)).all()
