import uuid

import pytest
from fastapi import HTTPException, status
from sqlmodel import Session

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
from database.auth.utils import get_session_expiry, hash_password
from routers.auth import (
    change_own_password,
    change_user_password,
    create_user,
    delete_current_user,
    delete_user,
    disable_user,
    enable_user,
    get_current_user_info,
    get_user,
    list_users,
    login,
    logout,
    search_users,
    update_current_user,
    update_user,
)

# ---------------------------------------------------------------------------
# Helper functions for tests
# ---------------------------------------------------------------------------


def create_test_user(
    session: Session,
    username: str = "testuser",
    password: str = "password123",
    role: UserRole = UserRole.DEVELOPER,
    enabled: bool = True,
) -> User:
    """Helper to create a test user in the database."""
    user = User(
        username=username,
        password=hash_password(password),
        role=role,
        enabled=enabled,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Login endpoint tests
# ---------------------------------------------------------------------------


def test_login_success(session: Session):
    """Test successful user login."""
    # Create a user
    _ = create_test_user(session, username="loginuser", password="pass123")

    # Try to login
    credentials = UserLogin(username="loginuser", password="pass123")  # pyright: ignore[reportArgumentType]
    result = login(credentials, session)

    assert "user" in result
    assert "session_token" in result
    assert "valid_until" in result
    assert isinstance(result["user"], UserPublic)
    assert result["user"].username == "loginuser"


def test_login_invalid_username(session: Session):
    """Test login with invalid username."""
    credentials = UserLogin(username="nonexistent", password="pass123")  # pyright: ignore[reportArgumentType]

    with pytest.raises(HTTPException) as exc_info:
        _ = login(credentials, session)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid username or password" in exc_info.value.detail


def test_login_invalid_password(session: Session):
    """Test login with invalid password."""
    _ = create_test_user(session, username="user1", password="correct123")

    credentials = UserLogin(username="user1", password="wrong123")  # pyright: ignore[reportArgumentType]

    with pytest.raises(HTTPException) as exc_info:
        _ = login(credentials, session)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid username or password" in exc_info.value.detail


def test_login_disabled_user(session: Session):
    """Test login with a disabled user account."""
    _ = create_test_user(
        session, username="disabled", password="pass123", enabled=False
    )

    credentials = UserLogin(username="disabled", password="pass123")  # pyright: ignore[reportArgumentType]

    with pytest.raises(HTTPException) as exc_info:
        _ = login(credentials, session)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "disabled" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Logout endpoint tests
# ---------------------------------------------------------------------------


def test_logout_success(session: Session, mock_user: User):
    """Test successful logout."""
    # Create a session for the user
    user_session = UserSession(  # pyright: ignore[reportCallIssue]
        user=mock_user,
        valid_until=get_session_expiry(hours=24),
    )
    session.add(mock_user)
    session.add(user_session)
    session.commit()

    # Mock authorization header
    auth_header = f"Bearer {user_session.id}"

    # Logout should not raise
    logout(session, mock_user, auth_header)


# ---------------------------------------------------------------------------
# Create user endpoint tests
# ---------------------------------------------------------------------------


def test_create_user_success(session: Session, mock_admin: User):
    """Test creating a user as admin."""
    user_data = UserCreate(username="newuser", password="pass12345")  # pyright: ignore[reportArgumentType]

    result = create_user(user_data, session, mock_admin)

    assert isinstance(result, UserPublic)
    assert result.username == "newuser"
    assert result.role == UserRole.DEVELOPER


def test_create_user_duplicate_username(session: Session, mock_admin: User):
    """Test creating a user with a duplicate username."""
    _ = create_test_user(session, username="existing")

    user_data = UserCreate(username="existing", password="pass12345")  # pyright: ignore[reportArgumentType]

    with pytest.raises(HTTPException) as exc_info:
        _ = create_user(user_data, session, mock_admin)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "already exists" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# List users endpoint tests
# ---------------------------------------------------------------------------


def test_list_users_success(session: Session, mock_admin: User):
    """Test listing all users as admin."""
    _ = create_test_user(session, username="user1")
    _ = create_test_user(session, username="user2")

    result = list_users(session, mock_admin)

    assert len(result) >= 2
    assert all(isinstance(u, UserPublic) for u in result)


# ---------------------------------------------------------------------------
# Search users endpoint tests
# ---------------------------------------------------------------------------


def test_search_users_by_username(session: Session, mock_admin: User):
    """Test searching users by username."""
    _ = create_test_user(session, username="alice")
    _ = create_test_user(session, username="bob")

    result = search_users(username="ali", session=session, _current_user=mock_admin)

    assert len(result) >= 1
    assert any(u.username == "alice" for u in result)


def test_search_users_by_enabled(session: Session, mock_admin: User):
    """Test searching users by enabled status."""
    _ = create_test_user(session, username="enabled1", enabled=True)
    _ = create_test_user(session, username="disabled1", enabled=False)

    result = search_users(enabled=False, session=session, _current_user=mock_admin)

    assert all(not u.enabled for u in result)


# ---------------------------------------------------------------------------
# Get current user endpoint tests
# ---------------------------------------------------------------------------


def test_get_current_user_info_success(mock_user: User):
    """Test getting current user info."""
    result = get_current_user_info(mock_user)

    assert isinstance(result, UserPublic)
    assert result.username == mock_user.username


# ---------------------------------------------------------------------------
# Get user by ID endpoint tests
# ---------------------------------------------------------------------------


def test_get_user_success(session: Session, mock_admin: User):
    """Test getting user by ID as admin."""
    user = create_test_user(session, username="targetuser")

    result = get_user(user.id, session, mock_admin)

    assert isinstance(result, UserPublic)
    assert result.username == "targetuser"


def test_get_user_not_found(session: Session, mock_admin: User):
    """Test getting non-existent user."""
    fake_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        _ = get_user(fake_id, session, mock_admin)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Update user endpoint tests
# ---------------------------------------------------------------------------


def test_update_user_username(session: Session, mock_admin: User):
    """Test updating user username as admin."""
    user = create_test_user(session, username="oldname")

    update_data = UserUpdate(username="newname")
    result = update_user(user.id, update_data, session, mock_admin)

    assert result.username == "newname"


def test_update_user_to_duplicate_username(session: Session, mock_admin: User):
    """Test updating user to a username that already exists."""
    user1 = create_test_user(session, username="user1")
    _ = create_test_user(session, username="user2")

    update_data = UserUpdate(username="user2")

    with pytest.raises(HTTPException) as exc_info:
        _ = update_user(user1.id, update_data, session, mock_admin)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Update current user endpoint tests
# ---------------------------------------------------------------------------


def test_update_current_user_username(session: Session, mock_user: User):
    """Test updating current user's username."""
    session.add(mock_user)
    session.commit()

    update_data = UserUpdate(username="newusername")
    result = update_current_user(update_data, session, mock_user)

    assert result.username == "newusername"


def test_update_current_user_cannot_change_role(session: Session, mock_user: User):
    """Test that users cannot change their own role."""
    session.add(mock_user)
    session.commit()

    update_data = UserUpdate(role=UserRole.ADMINISTRATOR)  # pyright: ignore[reportCallIssue]

    with pytest.raises(HTTPException) as exc_info:
        _ = update_current_user(update_data, session, mock_user)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Delete user endpoint tests
# ---------------------------------------------------------------------------


def test_delete_user_success(session: Session, mock_admin: User):
    """Test deleting a user as admin."""
    user = create_test_user(session, username="todelete")
    user_id = user.id

    delete_user(user_id, session, mock_admin)

    # Verify user is deleted
    deleted_user = session.get(User, user_id)
    assert deleted_user is None


def test_delete_user_not_found(session: Session, mock_admin: User):
    """Test deleting non-existent user."""
    fake_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        delete_user(fake_id, session, mock_admin)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Delete current user endpoint tests
# ---------------------------------------------------------------------------


def test_delete_current_user_success(session: Session, mock_user: User):
    """Test deleting own account."""
    session.add(mock_user)
    session.commit()
    user_id = mock_user.id

    delete_current_user(session, mock_user)

    # Verify user is deleted
    deleted_user = session.get(User, user_id)
    assert deleted_user is None


# ---------------------------------------------------------------------------
# Change password endpoint tests
# ---------------------------------------------------------------------------


def test_change_user_password_as_admin(session: Session, mock_admin: User):
    """Test admin changing user password."""
    user = create_test_user(session, username="user", password="oldpass")

    password_data = UserPasswordChange(new_password="newpass123")  # pyright: ignore[reportCallIssue]
    change_user_password(user.id, password_data, session, mock_admin)

    # Verify password was changed (no exception means success)
    assert True


def test_change_own_password_success(session: Session, mock_user: User):
    """Test user changing own password."""
    # Set a known password
    mock_user.password = hash_password("oldpass123")
    session.add(mock_user)
    session.commit()

    password_data = UserPasswordChange(
        current_password="oldpass123",  # pyright: ignore[reportArgumentType]
        new_password="newpass123",  # pyright: ignore[reportArgumentType]
    )
    change_own_password(password_data, session, mock_user)

    # Verify password was changed (no exception means success)
    assert True


def test_change_own_password_wrong_current(session: Session, mock_user: User):
    """Test changing own password with wrong current password."""
    mock_user.password = hash_password("correctpass")
    session.add(mock_user)
    session.commit()

    password_data = UserPasswordChange(
        current_password="wrongpass",  # pyright: ignore[reportArgumentType]
        new_password="newpass123",  # pyright: ignore[reportArgumentType]
    )

    with pytest.raises(HTTPException) as exc_info:
        change_own_password(password_data, session, mock_user)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_change_own_password_missing_current(session: Session, mock_user: User):
    """Test changing own password without providing current password."""
    session.add(mock_user)
    session.commit()

    password_data = UserPasswordChange(new_password="newpass123")  # pyright: ignore[reportCallIssue]

    with pytest.raises(HTTPException) as exc_info:
        change_own_password(password_data, session, mock_user)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Enable/Disable user endpoint tests
# ---------------------------------------------------------------------------


def test_enable_user_success(session: Session, mock_admin: User):
    """Test enabling a user as admin."""
    user = create_test_user(session, username="user", enabled=False)

    result = enable_user(user.id, session, mock_admin)

    assert result.enabled is True


def test_disable_user_success(session: Session, mock_admin: User):
    """Test disabling a user as admin."""
    user = create_test_user(session, username="user", enabled=True)

    result = disable_user(user.id, session, mock_admin)

    assert result.enabled is False
