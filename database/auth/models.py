"""
Authentication and authorization models for the R2Framework.

This module defines:
- User: Main user model with credentials and roles
- UserRole: Enumeration of user roles (DEVELOPER, ADMINISTRATOR)
- UserPublic: Public representation of user (without sensitive data)
- UserSession: Session management for logged-in users
"""

import enum
import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlalchemy import Column
from sqlmodel import Enum, Field, Relationship, SQLModel


class UserRole(str, enum.Enum):
    """User roles for authorization."""

    DEVELOPER = "DEVELOPER"
    ADMINISTRATOR = "ADMINISTRATOR"


class User(SQLModel, table=True):
    """
    Main user model for authentication and authorization.
    
    Attributes:
        id: Unique identifier for the user
        username: Unique username for login
        password: Hashed password
        enabled: Whether the user account is active
        roles: List of roles assigned to the user (stored as comma-separated string)
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the user.",
        primary_key=True,
    )
    username: str = Field(
        ...,
        description="Unique username for login.",
        unique=True,
        index=True,
    )
    password: str = Field(
        ...,
        description="Hashed password for authentication.",
    )
    enabled: bool = Field(
        default=True,
        description="Indicates whether the user account is active.",
    )
    # Store roles as a single role enum value
    role: UserRole = Field(
        ...,
        sa_column=Column(
            Enum(UserRole),
            nullable=False,
            default=UserRole.DEVELOPER,
        ),
        description="User role for authorization.",
    )

    sessions: list["UserSession"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "joined"},
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the user was created.",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the user was last updated.",
    )


class UserPublic(SQLModel):
    """
    Public representation of a user without sensitive information.
    Used for API responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    enabled: bool
    role: UserRole
    created_at: datetime
    updated_at: datetime


class UserSession(SQLModel, table=True):
    """
    Session management for authenticated users.
    
    Attributes:
        id: Unique session identifier
        user_id: Foreign key to the user
        valid_until: Expiration timestamp for the session
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique session identifier.",
        primary_key=True,
    )
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        description="Foreign key to the user this session belongs to.",
    )
    user: User = Relationship(
        back_populates="sessions",
        sa_relationship_kwargs={"lazy": "joined"},
    )
    valid_until: datetime = Field(
        ...,
        description="Expiration timestamp for the session.",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the session was created.",
    )


class UserCreate(SQLModel):
    """Schema for creating a new user."""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    role: UserRole = Field(default=UserRole.DEVELOPER)
    enabled: bool = Field(default=True)


class UserUpdate(SQLModel):
    """Schema for updating user information."""

    username: str | None = Field(None, min_length=3, max_length=50)
    enabled: bool | None = None
    role: UserRole | None = None


class UserPasswordChange(SQLModel):
    """Schema for changing user password."""

    current_password: str | None = Field(None, description="Current password (required for self)")
    new_password: str = Field(..., min_length=8)


class UserLogin(SQLModel):
    """Schema for user login."""

    username: str
    password: str
