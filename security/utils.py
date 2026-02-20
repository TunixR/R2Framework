"""
Authentication utilities for password hashing and verification.

This module provides:
- Password hashing using bcrypt
- Password verification
- Session token generation and validation
"""

from datetime import datetime, timedelta, timezone
import hmac
import hashlib

import bcrypt
import jwt
from pydantic import SecretStr

from security.token import TokenData
from settings import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY


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


def generate_session_token(
    data: TokenData,
    expires_delta: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
) -> str:
    """
    Generate a secure random session token.

    Returns:
        Random session token as a hex string
    """
    to_encode = data.model_dump(mode="json").copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


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


def robot_key_hash(key: str) -> str:
    """Compute an HMAC-SHA256 hash of a robot key for storage/lookup."""
    mac = hmac.new(SECRET_KEY.encode("utf-8"), key.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    return hmac.compare_digest(a, b)
