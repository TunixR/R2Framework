"""
Authentication and authorization middleware for the R2Framework.

This module provides:
- Authentication dependencies for endpoints
- Authorization checks for role-based access control
"""

from uuid import UUID

from fastapi import Depends, Header, HTTPException, status

from database.auth.models import User, UserRole, UserSession
from database.auth.utils import is_session_valid
from database.general import SessionDep


def get_current_user(
    session: SessionDep,
    authorization: str = Header(None),
) -> User:
    """
    Get the currently authenticated user from session token.
    
    Expects Authorization header with format: Bearer <session_id>
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    
    try:
        # Parse Bearer token
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme",
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )
    
    # Find session by ID
    try:
        session_id = UUID(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )
    
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
