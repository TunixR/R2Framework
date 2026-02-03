"""
Global pytest fixtures for unit tests.

This module provides shared fixtures for database sessions and test users.
"""

import uuid

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from database.auth.models import User, UserRole, UserSession


@pytest.fixture(name="session")
def session_fixture():
    """
    Create an in-memory SQLite database for testing.
    
    This fixture provides a clean database session for each test.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def mock_user():
    """Create a mock developer user for testing."""
    return User(
        id=uuid.uuid4(),
        username="testuser",
        password="hashed_password",
        role=UserRole.DEVELOPER,
        enabled=True,
    )


@pytest.fixture
def mock_admin():
    """Create a mock admin user for testing."""
    return User(
        id=uuid.uuid4(),
        username="admin",
        password="hashed_admin_password",
        role=UserRole.ADMINISTRATOR,
        enabled=True,
    )
