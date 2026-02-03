"""
Unit tests for authentication endpoints.

Tests cover:
- Login and logout functionality
- Admin operations (create, list, search, disable/enable, edit, delete users)
- User self-management operations
- Password management
- Authorization checks
- Edge cases (invalid credentials, disabled users, etc.)
"""

import uuid

import pytest
from fastapi import HTTPException, status

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
from database.auth.utils import hash_password, get_session_expiry
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
    session,
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


def create_test_admin(session) -> User:
    """Helper to create a test admin user."""
    return create_test_user(
        session,
        username="admin",
        password="admin123",
        role=UserRole.ADMINISTRATOR,
    )


# ---------------------------------------------------------------------------
# Login endpoint tests
# ---------------------------------------------------------------------------


def test_login_success(session):
    """Test successful user login."""
    # Create a user
    create_test_user(session, username="loginuser", password="pass123")
    
    # Try to login
    credentials = UserLogin(username="loginuser", password="pass123")
    result = login(credentials, session)
    
    assert "user" in result
    assert "session_token" in result
    assert "valid_until" in result
    assert result["user"].username == "loginuser"


def test_login_invalid_username(session):
    """Test login with invalid username."""
    credentials = UserLogin(username="nonexistent", password="pass123")
    
    with pytest.raises(HTTPException) as exc_info:
        login(credentials, session)
    
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid username or password" in exc_info.value.detail


def test_login_invalid_password(session):
    """Test login with invalid password."""
    create_test_user(session, username="user1", password="correct123")
    
    credentials = UserLogin(username="user1", password="wrong123")
    
    with pytest.raises(HTTPException) as exc_info:
        login(credentials, session)
    
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid username or password" in exc_info.value.detail


def test_login_disabled_user(session):
    """Test login with a disabled user account."""
    create_test_user(session, username="disabled", password="pass123", enabled=False)
    
    credentials = UserLogin(username="disabled", password="pass123")
    
    with pytest.raises(HTTPException) as exc_info:
        login(credentials, session)
    
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "disabled" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Logout endpoint tests
# ---------------------------------------------------------------------------


def test_logout_success(session, mock_user):
    """Test successful logout."""
    # Create a session for the user
    user_session = UserSession(
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


def test_create_user_success(session, mock_admin):
    """Test creating a user as admin."""
    user_data = UserCreate(username="newuser", password="pass12345")
    
    result = create_user(user_data, session, mock_admin)
    
    assert isinstance(result, UserPublic)
    assert result.username == "newuser"
    assert result.role == UserRole.DEVELOPER


def test_create_user_duplicate_username(session, mock_admin):
    """Test creating a user with a duplicate username."""
    create_test_user(session, username="existing")
    
    user_data = UserCreate(username="existing", password="pass12345")
    
    with pytest.raises(HTTPException) as exc_info:
        create_user(user_data, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "already exists" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# List users endpoint tests
# ---------------------------------------------------------------------------


def test_list_users_success(session, mock_admin):
    """Test listing all users as admin."""
    create_test_user(session, username="user1")
    create_test_user(session, username="user2")
    
    result = list_users(session, mock_admin)
    
    assert len(result) >= 2
    assert all(isinstance(u, UserPublic) for u in result)


# ---------------------------------------------------------------------------
# Search users endpoint tests
# ---------------------------------------------------------------------------


def test_search_users_by_username(session, mock_admin):
    """Test searching users by username."""
    create_test_user(session, username="alice")
    create_test_user(session, username="bob")
    
    result = search_users(username="ali", session=session, current_user=mock_admin)
    
    assert len(result) >= 1
    assert any(u.username == "alice" for u in result)


def test_search_users_by_enabled(session, mock_admin):
    """Test searching users by enabled status."""
    create_test_user(session, username="enabled1", enabled=True)
    create_test_user(session, username="disabled1", enabled=False)
    
    result = search_users(enabled=False, session=session, current_user=mock_admin)
    
    assert all(not u.enabled for u in result)


# ---------------------------------------------------------------------------
# Get current user endpoint tests
# ---------------------------------------------------------------------------


def test_get_current_user_info_success(mock_user):
    """Test getting current user info."""
    result = get_current_user_info(mock_user)
    
    assert isinstance(result, UserPublic)
    assert result.username == mock_user.username


# ---------------------------------------------------------------------------
# Get user by ID endpoint tests
# ---------------------------------------------------------------------------


def test_get_user_success(session, mock_admin):
    """Test getting user by ID as admin."""
    user = create_test_user(session, username="targetuser")
    
    result = get_user(user.id, session, mock_admin)
    
    assert isinstance(result, UserPublic)
    assert result.username == "targetuser"


def test_get_user_not_found(session, mock_admin):
    """Test getting non-existent user."""
    fake_id = uuid.uuid4()
    
    with pytest.raises(HTTPException) as exc_info:
        get_user(fake_id, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Update user endpoint tests
# ---------------------------------------------------------------------------


def test_update_user_username(session, mock_admin):
    """Test updating user username as admin."""
    user = create_test_user(session, username="oldname")
    
    update_data = UserUpdate(username="newname")
    result = update_user(user.id, update_data, session, mock_admin)
    
    assert result.username == "newname"


def test_update_user_to_duplicate_username(session, mock_admin):
    """Test updating user to a username that already exists."""
    user1 = create_test_user(session, username="user1")
    create_test_user(session, username="user2")
    
    update_data = UserUpdate(username="user2")
    
    with pytest.raises(HTTPException) as exc_info:
        update_user(user1.id, update_data, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Update current user endpoint tests
# ---------------------------------------------------------------------------


def test_update_current_user_username(session, mock_user):
    """Test updating current user's username."""
    session.add(mock_user)
    session.commit()
    
    update_data = UserUpdate(username="newusername")
    result = update_current_user(update_data, session, mock_user)
    
    assert result.username == "newusername"


def test_update_current_user_cannot_change_role(session, mock_user):
    """Test that users cannot change their own role."""
    session.add(mock_user)
    session.commit()
    
    update_data = UserUpdate(role=UserRole.ADMINISTRATOR)
    
    with pytest.raises(HTTPException) as exc_info:
        update_current_user(update_data, session, mock_user)
    
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Delete user endpoint tests
# ---------------------------------------------------------------------------


def test_delete_user_success(session, mock_admin):
    """Test deleting a user as admin."""
    user = create_test_user(session, username="todelete")
    user_id = user.id
    
    delete_user(user_id, session, mock_admin)
    
    # Verify user is deleted
    deleted_user = session.get(User, user_id)
    assert deleted_user is None


def test_delete_user_not_found(session, mock_admin):
    """Test deleting non-existent user."""
    fake_id = uuid.uuid4()
    
    with pytest.raises(HTTPException) as exc_info:
        delete_user(fake_id, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Delete current user endpoint tests
# ---------------------------------------------------------------------------


def test_delete_current_user_success(session, mock_user):
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


def test_change_user_password_as_admin(session, mock_admin):
    """Test admin changing user password."""
    user = create_test_user(session, username="user", password="oldpass")
    
    password_data = UserPasswordChange(new_password="newpass123")
    change_user_password(user.id, password_data, session, mock_admin)
    
    # Verify password was changed (no exception means success)
    assert True


def test_change_own_password_success(session, mock_user):
    """Test user changing own password."""
    # Set a known password
    mock_user.password = hash_password("oldpass123")
    session.add(mock_user)
    session.commit()
    
    password_data = UserPasswordChange(
        current_password="oldpass123",
        new_password="newpass123"
    )
    change_own_password(password_data, session, mock_user)
    
    # Verify password was changed (no exception means success)
    assert True


def test_change_own_password_wrong_current(session, mock_user):
    """Test changing own password with wrong current password."""
    mock_user.password = hash_password("correctpass")
    session.add(mock_user)
    session.commit()
    
    password_data = UserPasswordChange(
        current_password="wrongpass",
        new_password="newpass123"
    )
    
    with pytest.raises(HTTPException) as exc_info:
        change_own_password(password_data, session, mock_user)
    
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_change_own_password_missing_current(session, mock_user):
    """Test changing own password without providing current password."""
    session.add(mock_user)
    session.commit()
    
    password_data = UserPasswordChange(new_password="newpass123")
    
    with pytest.raises(HTTPException) as exc_info:
        change_own_password(password_data, session, mock_user)
    
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Enable/Disable user endpoint tests
# ---------------------------------------------------------------------------


def test_enable_user_success(session, mock_admin):
    """Test enabling a user as admin."""
    user = create_test_user(session, username="user", enabled=False)
    
    result = enable_user(user.id, session, mock_admin)
    
    assert result.enabled is True


def test_disable_user_success(session, mock_admin):
    """Test disabling a user as admin."""
    user = create_test_user(session, username="user", enabled=True)
    
    result = disable_user(user.id, session, mock_admin)
    
    assert result.enabled is False
