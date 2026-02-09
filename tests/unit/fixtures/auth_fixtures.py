"""
Authentication fixtures for unit tests.

Provides mock user and admin objects for testing authentication and authorization.
"""

import uuid

import pytest
from sqlmodel import Session

from database.auth.models import User, UserRole


@pytest.fixture
def mock_user(session: Session):
    """Create a mock developer user for testing."""
    user = User(
        id=uuid.uuid4(),
        username="testuser",
        password="hashed_password",
        role=UserRole.DEVELOPER,
        enabled=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def mock_admin(session: Session):
    """Create a mock admin user for testing."""
    admin = User(
        id=uuid.uuid4(),
        username="admin",
        password="hashed_admin_password",
        role=UserRole.ADMINISTRATOR,
        enabled=True,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return admin
