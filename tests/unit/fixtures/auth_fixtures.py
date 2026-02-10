"""
Authentication fixtures for unit tests.

Provides mock user and admin objects for testing authentication and authorization.
"""

import uuid

import pytest
from sqlmodel import Session

from database.auth.models import User, UserRole
from security.utils import hash_password


@pytest.fixture
def mock_user(session: Session):
    """Create a mock developer user for testing."""
    user = User(
        id=uuid.uuid4(),
        username="testuser",
        password=hash_password("password123"),
        role=UserRole.DEVELOPER,
        enabled=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def mock_user_disabled(session: Session):
    """Create a mock developer user for testing."""
    user = User(
        id=uuid.uuid4(),
        username="testuser_disabled",
        password=hash_password("password123"),
        role=UserRole.DEVELOPER,
        enabled=False,
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
        password=hash_password("adminpass123"),
        role=UserRole.ADMINISTRATOR,
        enabled=True,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return admin
