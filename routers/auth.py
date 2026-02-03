"""
Authentication and authorization endpoints for the R2Framework.

This module provides endpoints for:
- User authentication (login, logout)
- User management (CRUD operations)
- Password management
- Session management

Admin operations: Create, List, Search, Disable/Enable, Edit any, Delete any, Change any password
User operations: Login, See self, Delete self, Edit self, Change own password, Logout
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlmodel import select

from database.auth.models import (
    User,
    UserCreate,
    UserLogin,
    UserPasswordChange,
    UserPublic,
    UserSession,
    UserUpdate,
)
from database.auth.utils import (
    get_session_expiry,
    hash_password,
    verify_password,
)
from database.general import SessionDep
from middlewares.auth import get_current_user, require_admin

router = APIRouter(prefix="/auth", tags=["Auth"])


# Authentication endpoints


@router.post("/login", response_model=dict, summary="User login")
def login(credentials: UserLogin, session: SessionDep) -> dict:
    """
    Authenticate a user and create a session.
    Returns the user information (without password) and session token.
    """
    # Find user by username
    statement = select(User).where(User.username == credentials.username)
    user = session.exec(statement).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    # Verify password
    if not verify_password(credentials.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    # Check if user is enabled
    if not user.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    
    # Create session
    user_session = UserSession(
        user=user,
        valid_until=get_session_expiry(hours=24),
    )
    session.add(user_session)
    session.commit()
    session.refresh(user_session)
    
    # Return user info and session token
    return {
        "user": UserPublic.model_validate(user),
        "session_token": str(user_session.id),
        "valid_until": user_session.valid_until.isoformat(),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="User logout")
def logout(
    session: SessionDep,
    current_user: User = Depends(get_current_user),
    authorization: str = Header(None),
) -> None:
    """
    Logout the current user by invalidating their session.
    """
    # Extract session ID from authorization header
    _, token = authorization.split()
    session_id = UUID(token)
    
    # Find and delete session
    user_session = session.get(UserSession, session_id)
    if user_session:
        session.delete(user_session)
        session.commit()


# User CRUD endpoints (admin operations)


@router.post(
    "/users",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create user (Admin only)",
)
def create_user(
    user_data: UserCreate,
    session: SessionDep,
    current_user: User = Depends(require_admin),
) -> UserPublic:
    """
    Create a new user. Requires admin role.
    Password will be hashed before storage.
    """
    # Check if username already exists
    statement = select(User).where(User.username == user_data.username)
    existing_user = session.exec(statement).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    
    # Hash password and create user
    hashed_password = hash_password(user_data.password)
    new_user = User(
        username=user_data.username,
        password=hashed_password,
        role=user_data.role,
        enabled=user_data.enabled,
    )
    
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    
    return UserPublic.model_validate(new_user)


@router.get(
    "/users",
    response_model=Sequence[UserPublic],
    summary="List all users (Admin only)",
)
def list_users(
    session: SessionDep,
    current_user: User = Depends(require_admin),
) -> Sequence[UserPublic]:
    """
    List all users. Requires admin role.
    """
    users = session.exec(select(User)).all()
    return [UserPublic.model_validate(user) for user in users]


@router.get(
    "/users/search",
    response_model=Sequence[UserPublic],
    summary="Search users (Admin only)",
)
def search_users(
    username: str | None = None,
    enabled: bool | None = None,
    session: SessionDep,
    current_user: User = Depends(require_admin),
) -> Sequence[UserPublic]:
    """
    Search users by username or enabled status. Requires admin role.
    """
    statement = select(User)
    
    if username is not None:
        statement = statement.where(User.username.contains(username))
    
    if enabled is not None:
        statement = statement.where(User.enabled == enabled)
    
    users = session.exec(statement).all()
    return [UserPublic.model_validate(user) for user in users]


@router.get("/users/me", response_model=UserPublic, summary="Get current user")
def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserPublic:
    """
    Get information about the currently authenticated user.
    """
    return UserPublic.model_validate(current_user)


@router.get(
    "/users/{user_id}",
    response_model=UserPublic,
    summary="Get user by ID (Admin only)",
)
def get_user(
    user_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_admin),
) -> UserPublic:
    """
    Get user by ID. Requires admin role.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserPublic.model_validate(user)


@router.patch(
    "/users/{user_id}",
    response_model=UserPublic,
    summary="Update user (Admin only)",
)
def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    session: SessionDep,
    current_user: User = Depends(require_admin),
) -> UserPublic:
    """
    Update user information. Requires admin role.
    Can update username, enabled status, and role.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Check if new username already exists
    if user_data.username and user_data.username != user.username:
        statement = select(User).where(User.username == user_data.username)
        existing_user = session.exec(statement).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )
        user.username = user_data.username
    
    if user_data.enabled is not None:
        user.enabled = user_data.enabled
    
    if user_data.role is not None:
        user.role = user_data.role
    
    user.updated_at = datetime.now()
    session.add(user)
    session.commit()
    session.refresh(user)
    
    return UserPublic.model_validate(user)


@router.patch("/users/me", response_model=UserPublic, summary="Update current user")
def update_current_user(
    user_data: UserUpdate,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> UserPublic:
    """
    Update current user's own information.
    Users can only update their username (not role or enabled status).
    """
    if user_data.role is not None or user_data.enabled is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify role or enabled status",
        )
    
    if user_data.username:
        # Check if new username already exists
        if user_data.username != current_user.username:
            statement = select(User).where(User.username == user_data.username)
            existing_user = session.exec(statement).first()
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already exists",
                )
            current_user.username = user_data.username
    
    current_user.updated_at = datetime.now()
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    
    return UserPublic.model_validate(current_user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user (Admin only)",
)
def delete_user(
    user_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_admin),
) -> None:
    """
    Delete a user. Requires admin role.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Delete user's sessions first
    statement = select(UserSession).where(UserSession.user_id == user_id)
    sessions = session.exec(statement).all()
    for user_session in sessions:
        session.delete(user_session)
    
    session.delete(user)
    session.commit()


@router.delete(
    "/users/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete current user",
)
def delete_current_user(
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete current user's own account.
    """
    # Delete user's sessions first
    statement = select(UserSession).where(UserSession.user_id == current_user.id)
    sessions = session.exec(statement).all()
    for user_session in sessions:
        session.delete(user_session)
    
    session.delete(current_user)
    session.commit()


# Password management endpoints


@router.post(
    "/users/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change user password (Admin only)",
)
def change_user_password(
    user_id: UUID,
    password_data: UserPasswordChange,
    session: SessionDep,
    current_user: User = Depends(require_admin),
) -> None:
    """
    Change a user's password. Requires admin role.
    Admin does not need to provide current password.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Hash new password and update
    user.password = hash_password(password_data.new_password)
    user.updated_at = datetime.now()
    session.add(user)
    session.commit()


@router.post(
    "/users/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change own password",
)
def change_own_password(
    password_data: UserPasswordChange,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Change current user's own password.
    Requires current password for verification.
    """
    if not password_data.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is required",
        )
    
    # Verify current password
    if not verify_password(password_data.current_password, current_user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    
    # Hash new password and update
    current_user.password = hash_password(password_data.new_password)
    current_user.updated_at = datetime.now()
    session.add(current_user)
    session.commit()


# User enable/disable endpoints


@router.post(
    "/users/{user_id}/enable",
    response_model=UserPublic,
    summary="Enable user (Admin only)",
)
def enable_user(
    user_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_admin),
) -> UserPublic:
    """
    Enable a user account. Requires admin role.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    user.enabled = True
    user.updated_at = datetime.now()
    session.add(user)
    session.commit()
    session.refresh(user)
    
    return UserPublic.model_validate(user)


@router.post(
    "/users/{user_id}/disable",
    response_model=UserPublic,
    summary="Disable user (Admin only)",
)
def disable_user(
    user_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_admin),
) -> UserPublic:
    """
    Disable a user account. Requires admin role.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    user.enabled = False
    user.updated_at = datetime.now()
    session.add(user)
    session.commit()
    session.refresh(user)
    
    return UserPublic.model_validate(user)
