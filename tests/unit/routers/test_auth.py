import uuid
from functools import lru_cache

from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from database.auth.models import (
    User,
    UserCreate,
    UserPasswordChange,
    UserPublic,
    UserRole,
    UserSession,
    UserUpdate,
)
from security.utils import hash_password
from tests.unit.shared.auth_helpers import make_auth_headers, make_user_session


@lru_cache(maxsize=None)
def _hash_password_cached(password: str) -> str:
    return hash_password(password)


DEFAULT_TEST_PASSWORD = "password123"
DEFAULT_HASHED_PASSWORD = _hash_password_cached(DEFAULT_TEST_PASSWORD)

# ---------------------------------------------------------------------------
# Helper functions for tests
# ---------------------------------------------------------------------------


def create_test_user(
    session: Session,
    username: str = "testuser",
    password: str = DEFAULT_TEST_PASSWORD,
    role: UserRole = UserRole.DEVELOPER,
    enabled: bool = True,
    *,
    hash_password_value: bool = False,
) -> User:
    """Helper to create a test user in the database."""
    user = User(
        username=username,
        password=(
            _hash_password_cached(password)
            if hash_password_value
            else DEFAULT_HASHED_PASSWORD
        ),
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


def test_login_success(session: Session, client: TestClient):
    """Test successful user login."""
    _ = create_test_user(
        session,
        username="loginuser",
        password="pass123",
        hash_password_value=True,
    )

    response = client.post(
        "/auth/login",
        data={"username": "loginuser", "password": "pass123"},
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]


def test_login_invalid_username(client: TestClient):
    """Test login with invalid username."""
    response = client.post(
        "/auth/login",
        data={"username": "nonexistent", "password": "pass123"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "invalid username or password" in response.json()["detail"].lower()


def test_login_invalid_password(session: Session, client: TestClient):
    """Test login with invalid password."""
    _ = create_test_user(
        session,
        username="user1",
        password="correct123",
        hash_password_value=True,
    )

    response = client.post(
        "/auth/login",
        data={"username": "user1", "password": "wrong123"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "invalid username or password" in response.json()["detail"].lower()


def test_login_disabled_user(session: Session, client: TestClient):
    """Test login with a disabled user account."""
    _ = create_test_user(
        session,
        username="disabled",
        password="pass123",
        enabled=False,
        hash_password_value=True,
    )

    response = client.post(
        "/auth/login",
        data={"username": "disabled", "password": "pass123"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "disabled" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Logout endpoint tests
# ---------------------------------------------------------------------------


def test_logout_success(session: Session, mock_user: User, client: TestClient):
    """Test successful logout."""
    login_response = client.post(
        "/auth/login",
        data={"username": mock_user.username, "password": "password123"},
    )
    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["access_token"]

    response = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    sessions = session.exec(
        select(UserSession).where(UserSession.user_id == mock_user.id)
    ).all()
    assert sessions == []


# ---------------------------------------------------------------------------
# Create user endpoint tests
# ---------------------------------------------------------------------------


def test_create_user_success(session: Session, mock_admin: User, client: TestClient):
    """Test creating a user as admin."""
    headers = make_auth_headers(mock_admin, session)

    payload = UserCreate(username="newuser", password="pass12345")
    response = client.post(
        "/auth/users",
        json=payload.model_dump(mode="json"),
        headers=headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    result = UserPublic.model_validate_json(response.content)
    assert result.username == "newuser"
    assert result.role == UserRole.DEVELOPER


def test_create_user_duplicate_username(
    session: Session, mock_admin: User, client: TestClient
):
    """Test creating a user with a duplicate username."""
    _ = create_test_user(session, username="existing")

    headers = make_auth_headers(mock_admin, session)
    payload = UserCreate(username="existing", password="pass12345")
    response = client.post(
        "/auth/users",
        json=payload.model_dump(mode="json"),
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already exists" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# List users endpoint tests
# ---------------------------------------------------------------------------


def test_list_users_success(session: Session, mock_admin: User, client: TestClient):
    """Test listing all users as admin."""
    _ = create_test_user(session, username="user1")
    _ = create_test_user(session, username="user2")

    headers = make_auth_headers(mock_admin, session)
    response = client.get("/auth/users", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    users = [UserPublic.model_validate(u) for u in response.json()]
    assert len(users) >= 2


# ---------------------------------------------------------------------------
# Search users endpoint tests
# ---------------------------------------------------------------------------


def test_search_users_by_username(
    session: Session, mock_admin: User, client: TestClient
):
    """Test searching users by username."""
    _ = create_test_user(session, username="alice")
    _ = create_test_user(session, username="bob")

    headers = make_auth_headers(mock_admin, session)
    response = client.get(
        "/auth/users/search", params={"username": "ali"}, headers=headers
    )

    assert response.status_code == status.HTTP_200_OK
    users = [UserPublic.model_validate(u) for u in response.json()]
    assert any(u.username == "alice" for u in users)


def test_search_users_by_enabled(
    session: Session, mock_admin: User, client: TestClient
):
    """Test searching users by enabled status."""
    _ = create_test_user(session, username="enabled1", enabled=True)
    _ = create_test_user(session, username="disabled1", enabled=False)

    headers = make_auth_headers(mock_admin, session)
    response = client.get(
        "/auth/users/search", params={"enabled": "false"}, headers=headers
    )

    assert response.status_code == status.HTTP_200_OK
    users = [UserPublic.model_validate(u) for u in response.json()]
    assert all(not u.enabled for u in users)


# ---------------------------------------------------------------------------
# Get current user endpoint tests
# ---------------------------------------------------------------------------


def test_get_current_user_info_success(
    session: Session, mock_user: User, client: TestClient
):
    """Test getting current user info."""
    headers = make_auth_headers(mock_user, session)
    response = client.get("/auth/users/me", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    result = UserPublic.model_validate_json(response.content)
    assert result.username == mock_user.username


# ---------------------------------------------------------------------------
# Get user by ID endpoint tests
# ---------------------------------------------------------------------------


def test_get_user_success(session: Session, mock_admin: User, client: TestClient):
    """Test getting user by ID as admin."""
    user = create_test_user(session, username="targetuser")

    headers = make_auth_headers(mock_admin, session)
    response = client.get(f"/auth/users/{user.id}", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    result = UserPublic.model_validate_json(response.content)
    assert result.username == "targetuser"


def test_get_user_not_found(session: Session, mock_admin: User, client: TestClient):
    """Test getting non-existent user."""
    fake_id = uuid.uuid4()

    headers = make_auth_headers(mock_admin, session)
    response = client.get(f"/auth/users/{fake_id}", headers=headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Update user endpoint tests
# ---------------------------------------------------------------------------


def test_update_user_username(session: Session, mock_admin: User, client: TestClient):
    """Test updating user username as admin."""
    user = create_test_user(session, username="oldname")

    headers = make_auth_headers(mock_admin, session)
    update_data = UserUpdate(username="newname")
    response = client.patch(
        f"/auth/users/{user.id}",
        json=update_data.model_dump(exclude_unset=True, mode="json"),
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    result = UserPublic.model_validate_json(response.content)
    assert result.username == "newname"


def test_update_user_to_duplicate_username(
    session: Session, mock_admin: User, client: TestClient
):
    """Test updating user to a username that already exists."""
    user1 = create_test_user(session, username="user1")
    _ = create_test_user(session, username="user2")

    headers = make_auth_headers(mock_admin, session)
    update_data = UserUpdate(username="user2")
    response = client.patch(
        f"/auth/users/{user1.id}",
        json=update_data.model_dump(exclude_unset=True, mode="json"),
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Update current user endpoint tests
# ---------------------------------------------------------------------------


def test_update_current_user_username(
    session: Session, mock_user: User, client: TestClient
):
    """Test updating current user's username."""
    headers = make_auth_headers(mock_user, session)
    update_data = UserUpdate(username="newusername")
    response = client.patch(
        "/auth/users/me",
        json=update_data.model_dump(exclude_unset=True, mode="json"),
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    result = UserPublic.model_validate_json(response.content)
    assert result.username == "newusername"


def test_update_current_user_cannot_change_role(
    session: Session, mock_user: User, client: TestClient
):
    """Test that users cannot change their own role."""
    headers = make_auth_headers(mock_user, session)
    update_data = UserUpdate(role=UserRole.ADMINISTRATOR)  # pyright: ignore[reportCallIssue]
    response = client.patch(
        "/auth/users/me",
        json=update_data.model_dump(exclude_unset=True, mode="json"),
        headers=headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Delete user endpoint tests
# ---------------------------------------------------------------------------


def test_delete_user_success(session: Session, mock_admin: User, client: TestClient):
    """Test deleting a user as admin."""
    user = create_test_user(session, username="todelete")
    user_id = user.id

    headers = make_auth_headers(mock_admin, session)
    response = client.delete(f"/auth/users/{user_id}", headers=headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT

    session.expire_all()
    deleted_user = session.get(User, user_id)
    assert deleted_user is None


def test_delete_user_with_sessions_success(
    session: Session, mock_admin: User, client: TestClient
):
    """Test deleting a user as admin."""
    user = create_test_user(session, username="todelete")
    session.add(make_user_session(user))
    session.commit()
    user_id = user.id

    headers = make_auth_headers(mock_admin, session)
    response = client.delete(f"/auth/users/{user_id}", headers=headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT

    session.expire_all()
    deleted_user = session.get(User, user_id)
    assert deleted_user is None


def test_delete_user_not_found(session: Session, mock_admin: User, client: TestClient):
    """Test deleting non-existent user."""
    fake_id = uuid.uuid4()

    headers = make_auth_headers(mock_admin, session)
    response = client.delete(f"/auth/users/{fake_id}", headers=headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Delete current user endpoint tests
# ---------------------------------------------------------------------------


def test_delete_current_user_success(
    session: Session, mock_user: User, client: TestClient
):
    """Test deleting own account."""
    user_id = mock_user.id
    headers = make_auth_headers(mock_user, session)
    response = client.delete("/auth/users/me", headers=headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT

    session.expire_all()
    deleted_user = session.get(User, user_id)
    assert deleted_user is None


# ---------------------------------------------------------------------------
# Change password endpoint tests
# ---------------------------------------------------------------------------


def test_change_user_password_as_admin(
    session: Session, mock_admin: User, client: TestClient
):
    """Test admin changing user password."""
    user = create_test_user(session, username="user", password="oldpass")

    headers = make_auth_headers(mock_admin, session)
    payload = UserPasswordChange(current_password=None, new_password="newpass123")
    response = client.post(
        f"/auth/users/{user.id}/password",
        json=payload.model_dump(mode="json"),
        headers=headers,
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    login_response = client.post(
        "/auth/login",
        data={"username": "user", "password": "newpass123"},
    )
    assert login_response.status_code == status.HTTP_200_OK


def test_change_own_password_success(
    session: Session, mock_user: User, client: TestClient
):
    """Test user changing own password."""
    # Set a known password
    mock_user.password = hash_password("oldpass123")
    session.add(mock_user)
    session.commit()

    headers = make_auth_headers(mock_user, session)
    payload = UserPasswordChange(
        current_password="oldpass123", new_password="newpass123"
    )
    response = client.post(
        "/auth/users/me/password",
        json=payload.model_dump(mode="json"),
        headers=headers,
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT

    login_response = client.post(
        "/auth/login",
        data={"username": mock_user.username, "password": "newpass123"},
    )
    assert login_response.status_code == status.HTTP_200_OK


def test_change_own_password_wrong_current(
    session: Session, mock_user: User, client: TestClient
):
    """Test changing own password with wrong current password."""
    mock_user.password = hash_password("correctpass")
    session.add(mock_user)
    session.commit()

    headers = make_auth_headers(mock_user, session)
    payload = UserPasswordChange(
        current_password="wrongpass", new_password="newpass123"
    )
    response = client.post(
        "/auth/users/me/password",
        json=payload.model_dump(mode="json"),
        headers=headers,
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_change_own_password_missing_current(
    session: Session, mock_user: User, client: TestClient
):
    """Test changing own password without providing current password."""
    headers = make_auth_headers(mock_user, session)
    payload = UserPasswordChange(current_password=None, new_password="newpass123")
    response = client.post(
        "/auth/users/me/password",
        json=payload.model_dump(mode="json"),
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Enable/Disable user endpoint tests
# ---------------------------------------------------------------------------


def test_enable_user_success(session: Session, mock_admin: User, client: TestClient):
    """Test enabling a user as admin."""
    user = create_test_user(session, username="user", enabled=False)

    headers = make_auth_headers(mock_admin, session)
    response = client.post(f"/auth/users/{user.id}/enable", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    result = UserPublic.model_validate_json(response.content)
    assert result.enabled is True


def test_disable_user_success(session: Session, mock_admin: User, client: TestClient):
    """Test disabling a user as admin."""
    user = create_test_user(session, username="user", enabled=True)

    headers = make_auth_headers(mock_admin, session)
    response = client.post(f"/auth/users/{user.id}/disable", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    result = UserPublic.model_validate_json(response.content)
    assert result.enabled is False
