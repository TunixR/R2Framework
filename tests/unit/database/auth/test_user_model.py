import pytest
from pydantic import ValidationError

from database.auth.models import (
    User,
    UserCreate,
    UserPasswordChange,
    UserPublic,
    UserRole,
)

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
    assert (
        not hasattr(user_public, "password")
        or user_public.model_dump().get("password") is None
    )


# ---------------------------------------------------------------------------
# UserCreate schema tests
# ---------------------------------------------------------------------------


def test_user_create_schema():
    """Test UserCreate schema validation."""
    user_data = UserCreate(
        username="newuser",
        password="password123",  # pyright: ignore[reportArgumentType]
        role=UserRole.DEVELOPER,
    )

    assert user_data.username == "newuser"
    assert user_data.password.get_secret_value() == "password123"
    assert user_data.role == UserRole.DEVELOPER
    assert user_data.enabled is True


def test_user_create_schema_validation_username_too_short():
    """Test UserCreate schema validation for short username."""
    with pytest.raises(ValidationError):
        _ = UserCreate(
            username="ab",  # Too short (min 3)
            password="password123",  # pyright: ignore[reportArgumentType]
        )


def test_user_create_schema_validation_password_too_short():
    """Test UserCreate schema validation for short password."""
    with pytest.raises(ValidationError):
        _ = UserCreate(
            username="validuser",
            password="short",  # Too short (min 8) # pyright: ignore[reportArgumentType]
        )


# ---------------------------------------------------------------------------
# UserPasswordChange schema tests
# ---------------------------------------------------------------------------


def test_user_password_change_schema_validation():
    """Test UserPasswordChange schema validation for short password."""
    with pytest.raises(ValidationError):
        _ = UserPasswordChange(
            current_password="currentpass",  # pyright: ignore[reportArgumentType]
            new_password="short",  # Too short (min 8) # pyright: ignore[reportArgumentType]
        )
