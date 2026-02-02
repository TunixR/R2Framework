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
from sqlmodel import Session, create_engine
from sqlmodel.pool import StaticPool

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
# Import auth endpoints directly to avoid importing the full routers package
# which has dependencies we don't want to load for these tests
import sys
from pathlib import Path

# Add the parent directory to the path to import routers.auth
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

# Import only the auth router module
import importlib.util
auth_module_path = Path(__file__).resolve().parent.parent.parent.parent / 'routers' / 'auth.py'
spec = importlib.util.spec_from_file_location(
    "routers.auth",
    str(auth_module_path)
)
auth_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth_module)

# Import the functions we need
change_own_password = auth_module.change_own_password
change_user_password = auth_module.change_user_password
create_user = auth_module.create_user
delete_current_user = auth_module.delete_current_user
delete_user = auth_module.delete_user
disable_user = auth_module.disable_user
enable_user = auth_module.enable_user
get_current_user_info = auth_module.get_current_user_info
get_user = auth_module.get_user
list_users = auth_module.list_users
login = auth_module.login
logout = auth_module.logout
search_users = auth_module.search_users
update_current_user = auth_module.update_current_user
update_user = auth_module.update_user


@pytest.fixture(name="session")
def session_fixture():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import all models to register them with SQLModel
    from database.auth.models import User, UserSession  # noqa: F401
    from sqlmodel import SQLModel
    
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
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
        password="hashed_password",
        role=UserRole.ADMINISTRATOR,
        enabled=True,
    )


# ---------------------------------------------------------------------------
# Helper functions for tests
# ---------------------------------------------------------------------------


def create_test_user(
    session: Session,
    username: str = "testuser",
    password: str = "hashed_password",
    role: UserRole = UserRole.DEVELOPER,
    enabled: bool = True,
) -> User:
    """Helper to create a test user in the database."""
    user = User(
        username=username,
        password=password,
        role=role,
        enabled=enabled,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_test_admin(session: Session) -> User:
    """Helper to create a test admin user."""
    return create_test_user(
        session,
        username="admin",
        password="admin_password",
        role=UserRole.ADMINISTRATOR,
    )


# ---------------------------------------------------------------------------
# Login endpoint tests
# ---------------------------------------------------------------------------


def test_login_not_implemented(session: Session):
    """Test that login endpoint returns 501 Not Implemented."""
    credentials = UserLogin(username="testuser", password="password123")
    
    with pytest.raises(HTTPException) as exc_info:
        login(credentials, session)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Logout endpoint tests
# ---------------------------------------------------------------------------


def test_logout_not_implemented(mock_user):
    """Test that logout endpoint returns 501 Not Implemented."""
    # Using mock_user fixture
    
    with pytest.raises(HTTPException) as exc_info:
        logout(current_user=mock_user)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Create user endpoint tests
# ---------------------------------------------------------------------------


def test_create_user_not_implemented(session: Session, mock_admin):
    """Test that create_user endpoint returns 501 Not Implemented."""
    user_data = UserCreate(username="newuser", password="password123")
    # Using mock_admin fixture
    
    with pytest.raises(HTTPException) as exc_info:
        create_user(user_data, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# List users endpoint tests
# ---------------------------------------------------------------------------


def test_list_users_not_implemented(session: Session, mock_admin):
    """Test that list_users endpoint returns 501 Not Implemented."""
    # Using mock_admin fixture
    
    with pytest.raises(HTTPException) as exc_info:
        list_users(session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Search users endpoint tests
# ---------------------------------------------------------------------------


def test_search_users_not_implemented(session: Session, mock_admin):
    """Test that search_users endpoint returns 501 Not Implemented."""
    # Using mock_admin fixture
    
    with pytest.raises(HTTPException) as exc_info:
        search_users(username="test", session=session, current_user=mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Get current user endpoint tests
# ---------------------------------------------------------------------------


def test_get_current_user_info_not_implemented(mock_user):
    """Test that get_current_user_info endpoint returns 501 Not Implemented."""
    # Using mock_user fixture
    
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_info(mock_user)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Get user by ID endpoint tests
# ---------------------------------------------------------------------------


def test_get_user_not_implemented(session: Session):
    """Test that get_user endpoint returns 501 Not Implemented."""
    user_id = uuid.uuid4()
    # Using mock_admin fixture
    
    with pytest.raises(HTTPException) as exc_info:
        get_user(user_id, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Update user endpoint tests
# ---------------------------------------------------------------------------


def test_update_user_not_implemented(session: Session):
    """Test that update_user endpoint returns 501 Not Implemented."""
    user_id = uuid.uuid4()
    update_data = UserUpdate(username="updateduser")
    # Using mock_admin fixture
    
    with pytest.raises(HTTPException) as exc_info:
        update_user(user_id, update_data, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Update current user endpoint tests
# ---------------------------------------------------------------------------


def test_update_current_user_not_implemented(session: Session, mock_user):
    """Test that update_current_user endpoint returns 501 Not Implemented."""
    update_data = UserUpdate(username="updateduser")
    # Using mock_user fixture
    
    with pytest.raises(HTTPException) as exc_info:
        update_current_user(update_data, session, mock_user)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Delete user endpoint tests
# ---------------------------------------------------------------------------


def test_delete_user_not_implemented(session: Session):
    """Test that delete_user endpoint returns 501 Not Implemented."""
    user_id = uuid.uuid4()
    # Using mock_admin fixture
    
    with pytest.raises(HTTPException) as exc_info:
        delete_user(user_id, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Delete current user endpoint tests
# ---------------------------------------------------------------------------


def test_delete_current_user_not_implemented(session: Session, mock_user):
    """Test that delete_current_user endpoint returns 501 Not Implemented."""
    # Using mock_user fixture
    
    with pytest.raises(HTTPException) as exc_info:
        delete_current_user(session, mock_user)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Change password endpoint tests
# ---------------------------------------------------------------------------


def test_change_user_password_not_implemented(session: Session):
    """Test that change_user_password endpoint returns 501 Not Implemented."""
    user_id = uuid.uuid4()
    password_data = UserPasswordChange(new_password="newpassword123")
    # Using mock_admin fixture
    
    with pytest.raises(HTTPException) as exc_info:
        change_user_password(user_id, password_data, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


def test_change_own_password_not_implemented(session: Session, mock_user):
    """Test that change_own_password endpoint returns 501 Not Implemented."""
    password_data = UserPasswordChange(
        current_password="oldpassword", new_password="newpassword123"
    )
    # Using mock_user fixture
    
    with pytest.raises(HTTPException) as exc_info:
        change_own_password(password_data, session, mock_user)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Enable/Disable user endpoint tests
# ---------------------------------------------------------------------------


def test_enable_user_not_implemented(session: Session):
    """Test that enable_user endpoint returns 501 Not Implemented."""
    user_id = uuid.uuid4()
    # Using mock_admin fixture
    
    with pytest.raises(HTTPException) as exc_info:
        enable_user(user_id, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


def test_disable_user_not_implemented(session: Session):
    """Test that disable_user endpoint returns 501 Not Implemented."""
    user_id = uuid.uuid4()
    # Using mock_admin fixture
    
    with pytest.raises(HTTPException) as exc_info:
        disable_user(user_id, session, mock_admin)
    
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# Edge case tests - These will be filled in after implementation
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Implementation not yet complete")
def test_login_with_invalid_credentials(session: Session):
    """Test login with invalid credentials."""
    # Will implement after login is implemented
    pass


@pytest.mark.skip(reason="Implementation not yet complete")
def test_login_with_disabled_user(session: Session):
    """Test login with a disabled user account."""
    # Will implement after login is implemented
    pass


@pytest.mark.skip(reason="Implementation not yet complete")
def test_create_user_duplicate_username(session: Session):
    """Test creating a user with a duplicate username."""
    # Will implement after create_user is implemented
    pass


@pytest.mark.skip(reason="Implementation not yet complete")
def test_update_user_to_duplicate_username(session: Session):
    """Test updating a user to a username that already exists."""
    # Will implement after update_user is implemented
    pass


@pytest.mark.skip(reason="Implementation not yet complete")
def test_developer_cannot_access_admin_endpoints(session: Session):
    """Test that developers cannot access admin-only endpoints."""
    # Will implement after authorization is implemented
    pass


@pytest.mark.skip(reason="Implementation not yet complete")
def test_user_cannot_delete_other_users(session: Session):
    """Test that users cannot delete other users' accounts."""
    # Will implement after implementation
    pass


@pytest.mark.skip(reason="Implementation not yet complete")
def test_user_cannot_change_other_users_password(session: Session):
    """Test that users cannot change other users' passwords."""
    # Will implement after implementation
    pass


@pytest.mark.skip(reason="Implementation not yet complete")
def test_session_expires_after_valid_until(session: Session):
    """Test that expired sessions are invalid."""
    # Will implement after session management is implemented
    pass
