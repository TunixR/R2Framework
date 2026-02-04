"""
Authentication fixtures for unit tests.

Provides mock user and admin objects for testing authentication and authorization.
"""

import uuid

import pytest

from database.auth.models import User, UserRole


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
