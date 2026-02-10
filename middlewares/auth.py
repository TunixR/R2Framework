"""
Authentication and authorization middleware for the R2Framework.

This module provides:
- Authentication dependencies for endpoints
- Authorization checks for role-based access control
"""

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from jwt.exceptions import InvalidTokenError

from database.auth.models import User, UserRole, UserSession
from database.general import SessionDep
from security.token import oauth2_scheme
from security.utils import is_session_valid
from settings import ALGORITHM, SECRET_KEY


def get_current_user(
    session: SessionDep,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    """
    Get the currently authenticated user from session token.

    Expects Authorization header with format: Bearer <session_id>
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("username")
        session_id_raw = payload.get("session_id")
        if username is None or session_id_raw is None:
            raise credentials_exception
        session_id = UUID(str(session_id_raw))
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    except ValueError:
        raise credentials_exception

    user_session = session.get(UserSession, session_id)
    if not user_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    # Check if session is still valid
    if not is_session_valid(user_session.valid_until):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )

    # Get user from session
    user = user_session.user
    if user.username != username:
        raise credentials_exception
    if not user.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role for the current user."""
    if current_user.role != UserRole.ADMINISTRATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return current_user
