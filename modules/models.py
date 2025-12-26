import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Execution(SQLModel, table=True):
    """
    Represents an execution of a tool.
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the execution.",
        primary_key=True,
    )
    timestamp_start: str = Field(
        datetime.now(), description="Timestamp of when the tool was executed."
    )
    timestamp_end: Optional[str] = Field(
        None, description="Timestamp of when the tool execution ended."
    )
    exception_id: uuid.UUID = Field(
        None,
        foreign_key="robotexception.id",
        description="ID of the exception that was raised during the tool execution.",
    )
    module_id: uuid.UUID = Field(
        ...,
        foreign_key="module.id",
        description="ID of the module that executed the tool.",
    )

    class ConfigDict:
        arbitrary_types_allowed = True

    def to_json(self) -> dict:
        """Convert the model to a dictionary structure."""
        return {
            "id": str(self.id),
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "exception_id": str(self.exception_id) if self.exception_id else None,
            "module_id": str(self.module_id),
        }


class Solution(SQLModel, table=True):
    """
    Represents a solution to an exception.
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the solution.",
        primary_key=True,
    )
    timestamp: str = Field(
        datetime.now(), description="Timestamp of when the solution was created."
    )
    details: Optional[str] = Field(
        None, description="Details about the solution, if available."
    )
    fix: Optional[str] = Field(
        ..., description="Fix to be applied, if any"
    )  # TODO: Further develop this to allow for not only info, but automated fixes via tool use
    resolved: bool = Field(
        ..., description="Indicates whether the solution was successfully applied."
    )
    requires_planning: bool = Field(
        ...,
        description="Indicates whether the solution requires planning before execution.",
    )
    execution_id: uuid.UUID = Field(
        ...,
        foreign_key="execution.id",
        description="ID of the execution that this solution is associated with.",
    )

    def to_json(self) -> dict:
        """Convert the model to a dictionary structure."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp,
            "details": self.details,
            "fix": self.fix,
            "resolved": self.resolved,
            "requires_planning": self.requires_planning,
            "execution_id": str(self.execution_id),
        }


class Planning(SQLModel, table=True):
    """
    Represents a planning for a solution.
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the planning.",
        primary_key=True,
    )
    timestamp: str = Field(
        datetime.now(), description="Timestamp of when the planning was created."
    )
    details: Optional[str] = Field(
        None, description="Details about the planning, if available."
    )
    solution_id: Optional[uuid.UUID] = Field(
        ...,
        foreign_key="solution.id",
        description="ID of the solution that this planning is associated with.",
    )

    def to_json(self) -> dict:
        """Convert the model to a dictionary structure."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp,
            "details": self.details,
            "solution_id": str(self.solution_id),
        }


class Step(SQLModel, table=True):
    """
    Represents a step in the planning.
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the step.",
        primary_key=True,
    )
    timestamp: str = Field(
        datetime.now(), description="Timestamp of when the step was created."
    )
    step: str = Field(..., description="Description of the step to be executed.")
    details: Optional[str] = Field(
        None, description="Details about the step, if available."
    )
    planning_id: uuid.UUID = Field(
        ...,
        foreign_key="planning.id",
        description="ID of the planning that this step is associated with.",
    )

    def to_json(self) -> dict:
        """Convert the model to a dictionary structure."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp,
            "step": self.step,
            "details": self.details,
            "planning_id": str(self.planning_id),
        }


class ExecutedAction(SQLModel, table=True):
    """
    Represents an action that has been executed as part of a step.
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the executed action.",
        primary_key=True,
    )
    timestamp: str = Field(
        datetime.now(), description="Timestamp of when the action was executed."
    )
    step_id: uuid.UUID = Field(
        ...,
        foreign_key="step.id",
        description="ID of the step that this action is associated with.",
    )
    details: Optional[str] = Field(
        None, description="Details about the executed action, if available."
    )
    result: Optional[str] = Field(
        None, description="Result of the executed action, if available."
    )
    # TODO: action: "Action" = Field(..., description="The action that was executed. This should be a reference to an Action model that defines the action's logic.")
    tool_use_id: Optional[uuid.UUID] = Field(
        None,
        foreign_key="tooluse.id",
        description="ID of the tool use that this action is associated with.",
    )

    def to_json(self) -> dict:
        """Convert the model to a dictionary structure."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp,
            "step_id": str(self.step_id),
            "details": self.details,
            "result": self.result,
            "tool_use_id": str(self.tool_use_id) if self.tool_use_id else None,
        }
