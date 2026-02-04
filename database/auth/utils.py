"""
Authentication utilities for password hashing and verification.

This module provides:
- Password hashing using bcrypt
- Password verification
- Session token generation and validation
"""

import secrets
from datetime import datetime, timedelta

import bcrypt
from pydantic import SecretStr


def hash_password(password: SecretStr | str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password as a string
    """
    # Generate a salt and hash the password
    salt = bcrypt.gensalt()
    if isinstance(password, SecretStr):
        password = password.get_secret_value()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(
    plain_password: SecretStr | str, hashed_password: SecretStr | str
) -> bool:
    """
    Verify a password against a hashed password.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    if isinstance(plain_password, SecretStr):
        plain_password = plain_password.get_secret_value()
    if isinstance(hashed_password, SecretStr):
        hashed_password = hashed_password.get_secret_value()
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def generate_session_token() -> str:
    """
    Generate a secure random session token.

    Returns:
        Random session token as a hex string
    """
    return secrets.token_hex(32)


def get_session_expiry(hours: int = 24) -> datetime:
    """
    Calculate session expiry time.

    Args:
        hours: Number of hours until expiry (default: 24)

    Returns:
        Datetime of when session should expire
    """
    return datetime.now() + timedelta(hours=hours)


def is_session_valid(valid_until: datetime) -> bool:
    """
    Check if a session is still valid.

    Args:
        valid_until: Session expiry datetime

    Returns:
        True if session is still valid, False otherwise
    """
    return datetime.now() < valid_until
