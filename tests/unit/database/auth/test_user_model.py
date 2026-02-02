"""
Unit tests for User and UserSession models.

Tests cover:
- User model creation and validation
- UserRole enum values
- UserPublic model (without password)
- UserSession model
- Edge cases and validation errors
"""

import uuid
from datetime import datetime, timedelta

import pytest

from database.auth.models import (
    User,
    UserCreate,
    UserLogin,
    UserPasswordChange,
    UserPublic,
    UserRole,
    UserSession,
    UserUpdate,
)


# ---------------------------------------------------------------------------
# UserRole tests
# ---------------------------------------------------------------------------


def test_user_role_enum_values():
    """Test that UserRole enum has expected values."""
    assert UserRole.DEVELOPER == "DEVELOPER"
    assert UserRole.ADMINISTRATOR == "ADMINISTRATOR"
    assert len(list(UserRole)) == 2


# ---------------------------------------------------------------------------
# User model tests
# ---------------------------------------------------------------------------


def test_user_creation():
    """Test creating a User model with valid data."""
    user = User(
        username="testuser",
        password="hashed_password",
        role=UserRole.DEVELOPER,
        enabled=True,
    )
    assert user.username == "testuser"
    assert user.password == "hashed_password"
    assert user.role == UserRole.DEVELOPER
    assert user.enabled is True
    assert isinstance(user.id, uuid.UUID)
    assert isinstance(user.created_at, datetime)
    assert isinstance(user.updated_at, datetime)


def test_user_defaults():
    """Test User model default values."""
    user = User(
        username="testuser",
        password="hashed_password",
        role=UserRole.DEVELOPER,
    )
    assert user.enabled is True  # Default should be True


def test_user_with_administrator_role():
    """Test creating a User with ADMINISTRATOR role."""
    user = User(
        username="admin",
        password="hashed_password",
        role=UserRole.ADMINISTRATOR,
        enabled=True,
    )
    assert user.role == UserRole.ADMINISTRATOR


def test_user_disabled():
    """Test creating a disabled User."""
    user = User(
        username="disabled_user",
        password="hashed_password",
        role=UserRole.DEVELOPER,
        enabled=False,
    )
    assert user.enabled is False


# ---------------------------------------------------------------------------
# UserPublic model tests
# ---------------------------------------------------------------------------


def test_user_public_model():
    """Test that UserPublic model can be created from User."""
    user = User(
        username="testuser",
        password="secret_password",
        role=UserRole.DEVELOPER,
        enabled=True,
    )
    
    # Create UserPublic from User
    user_public = UserPublic.model_validate(user)
    
    assert user_public.id == user.id
    assert user_public.username == user.username
    assert user_public.enabled == user.enabled
    assert user_public.role == user.role
    assert user_public.created_at == user.created_at
    assert user_public.updated_at == user.updated_at
    # Password should not be in UserPublic
    assert not hasattr(user_public, "password") or user_public.model_dump().get("password") is None


# ---------------------------------------------------------------------------
# UserSession model tests
# ---------------------------------------------------------------------------


def test_user_session_creation():
    """Test creating a UserSession model."""
    user = User(
        username="testuser",
        password="hashed_password",
        role=UserRole.DEVELOPER,
    )
    
    valid_until = datetime.now() + timedelta(hours=24)
    session = UserSession(
        user=user,
        valid_until=valid_until,
    )
    
    assert isinstance(session.id, uuid.UUID)
    assert session.user == user
    assert session.valid_until == valid_until
    assert isinstance(session.created_at, datetime)


def test_user_session_expiration():
    """Test UserSession with past expiration."""
    user = User(
        username="testuser",
        password="hashed_password",
        role=UserRole.DEVELOPER,
    )
    
    # Create a session that expired in the past
    valid_until = datetime.now() - timedelta(hours=1)
    session = UserSession(
        user=user,
        valid_until=valid_until,
    )
    
    assert session.valid_until < datetime.now()


# ---------------------------------------------------------------------------
# UserCreate schema tests
# ---------------------------------------------------------------------------


def test_user_create_schema():
    """Test UserCreate schema validation."""
    user_data = UserCreate(
        username="newuser",
        password="password123",
        role=UserRole.DEVELOPER,
    )
    
    assert user_data.username == "newuser"
    assert user_data.password == "password123"
    assert user_data.role == UserRole.DEVELOPER
    assert user_data.enabled is True


def test_user_create_schema_defaults():
    """Test UserCreate schema default values."""
    user_data = UserCreate(
        username="newuser",
        password="password123",
    )
    
    assert user_data.role == UserRole.DEVELOPER  # Default role
    assert user_data.enabled is True


def test_user_create_schema_validation_username_too_short():
    """Test UserCreate schema validation for short username."""
    with pytest.raises(Exception):  # ValidationError
        UserCreate(
            username="ab",  # Too short (min 3)
            password="password123",
        )


def test_user_create_schema_validation_password_too_short():
    """Test UserCreate schema validation for short password."""
    with pytest.raises(Exception):  # ValidationError
        UserCreate(
            username="validuser",
            password="short",  # Too short (min 8)
        )


# ---------------------------------------------------------------------------
# UserUpdate schema tests
# ---------------------------------------------------------------------------


def test_user_update_schema():
    """Test UserUpdate schema with all fields."""
    update_data = UserUpdate(
        username="updateduser",
        enabled=False,
        role=UserRole.ADMINISTRATOR,
    )
    
    assert update_data.username == "updateduser"
    assert update_data.enabled is False
    assert update_data.role == UserRole.ADMINISTRATOR


def test_user_update_schema_partial():
    """Test UserUpdate schema with partial fields."""
    update_data = UserUpdate(
        username="updateduser",
    )
    
    assert update_data.username == "updateduser"
    assert update_data.enabled is None
    assert update_data.role is None


def test_user_update_schema_empty():
    """Test UserUpdate schema with no fields."""
    update_data = UserUpdate()
    
    assert update_data.username is None
    assert update_data.enabled is None
    assert update_data.role is None


# ---------------------------------------------------------------------------
# UserPasswordChange schema tests
# ---------------------------------------------------------------------------


def test_user_password_change_schema():
    """Test UserPasswordChange schema."""
    password_data = UserPasswordChange(
        current_password="oldpassword",
        new_password="newpassword123",
    )
    
    assert password_data.current_password == "oldpassword"
    assert password_data.new_password == "newpassword123"


def test_user_password_change_schema_no_current():
    """Test UserPasswordChange schema without current password (admin use case)."""
    password_data = UserPasswordChange(
        new_password="newpassword123",
    )
    
    assert password_data.current_password is None
    assert password_data.new_password == "newpassword123"


def test_user_password_change_schema_validation():
    """Test UserPasswordChange schema validation for short password."""
    with pytest.raises(Exception):  # ValidationError
        UserPasswordChange(
            new_password="short",  # Too short (min 8)
        )


# ---------------------------------------------------------------------------
# UserLogin schema tests
# ---------------------------------------------------------------------------


def test_user_login_schema():
    """Test UserLogin schema."""
    login_data = UserLogin(
        username="testuser",
        password="password123",
    )
    
    assert login_data.username == "testuser"
    assert login_data.password == "password123"
