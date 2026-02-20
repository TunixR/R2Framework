from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class RobotKey(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    name: str = Field(description="Human-friendly key name")
    description: str | None = Field(default=None, description="Key description")
    enabled: bool = Field(default=True, description="Whether key is active")

    key_hash: str = Field(index=True, description="HMAC-SHA256 of key")
    key_last4: str = Field(min_length=4, max_length=4, description="Last 4 chars")

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the key was created.",
    )


class RobotKeyCreate(SQLModel):
    name: str
    description: str | None = None
    enabled: bool = True


class RobotKeyPublic(SQLModel):
    id: UUID
    name: str
    description: str | None
    enabled: bool
    key: str
    created_at: datetime


class RobotKeyCreated(SQLModel):
    id: UUID
    name: str
    description: str | None
    enabled: bool
    key: str
    created_at: datetime
