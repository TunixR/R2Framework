# Defines the data models for the gateway service

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSON
from sqlmodel import Field, SQLModel

from gateway.enums import ExceptionType


class RobotException(SQLModel, table=True):
    """
    Represents an exception to be routed for resolution by the gateway service.
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the exception.",
        primary_key=True,
    )
    timestamp: str = Field(
        datetime.now(),
        description="Timestamp of when the exception record was created.",
    )
    code: str = Field(..., description="The error code associated with the exception.")
    variables: Optional[dict] = Field(
        None,
        description="A dictionary of variables associated with the robot execution, if any.",
        sa_column=Column(JSON),
    )
    exception_type: ExceptionType = Field(..., description="The type of exception")
    message: str = Field(
        ..., description="A human-readable message describing the error."
    )
    details: Optional[str] = Field(
        None, description="Additional details about the error, if available."
    )

    class Config:
        arbitrary_types_allowed = True

    def to_json(self) -> dict:
        """Convert the model to a dictionary structure."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp,
            "code": self.code,
            "exception_type": self.exception_type.value
            if self.exception_type
            else None,
            "message": self.message,
            "details": self.details,
        }


class Result(SQLModel, table=True):
    """
    Represents the result of an exception resolve operation.
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the result.",
        primary_key=True,
    )
    timestamp: str = Field(
        datetime.now(),
        description="Timestamp of when the exception record was created.",
    )
    solved: bool = Field(
        ..., description="Indicates whether the exception was successfully resolved."
    )
    has_fix: bool = Field(
        ..., description="Indicates whether a fix was applied to the exception."
    )
    audit_id: uuid.UUID = Field(
        ...,
        foreign_key="audit.id",
        description="ID of the audit record associated with this result.",
    )

    def to_json(self) -> dict:
        """Convert the model to a dictionary structure."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp,
            "solved": self.solved,
            "has_fix": self.has_fix,
            "audit_id": str(self.audit_id),
        }


class Audit(SQLModel, table=True):
    """
    Represents an audit record for the routing of an Exception.
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the audit record.",
        primary_key=True,
    )
    timestamp: str = Field(
        datetime.now(),
        description="Timestamp of when the exception record was created.",
    )
    reasoning: str = Field(
        ..., description="The reasoning behind the routing decision."
    )
    module_id: uuid.UUID = Field(
        ...,
        description="ID of the module that handled the exception.",
        foreign_key="module.id",
    )
    exception_id: uuid.UUID = Field(
        ...,
        foreign_key="robotexception.id",
        description="ID of the exception that was routed for resolution.",
    )

    def to_json(self) -> dict:
        """Convert the model to a dictionary structure."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp,
            "reasoning": self.reasoning,
            "module_id": str(self.module_id),
            "exception_id": str(self.exception_id),
        }


####################
## REQUEST MODELS ##
####################


class RobotExceptionRequest(BaseModel):
    code: str
    variables: Optional[dict]
    details: Optional[dict]

    def __str__(self):
        return super().__str__()
