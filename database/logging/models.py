from datetime import datetime, timezone
from typing import Dict
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlmodel import Field, Relationship, Session, SQLModel, select

from database.agents.models import Agent
from database.tools.models import Tool


class AgentTrace(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    robot_exception_id: UUID | None = Field(
        foreign_key="robotexception.id", default=None
    )
    robot_exception: "RobotException" = Relationship(back_populates="agent_traces")

    agent_id: UUID = Field(foreign_key="agent.id")
    agent: Agent = Relationship(back_populates="traces")

    gui_trace_id: UUID | None = Field(foreign_key="guitrace.id", default=None)
    gui_trace: "GUITrace" = Relationship(
        back_populates="agent_trace",
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "GUITrace.agent_trace_id",
        },
    )

    sub_agents_traces: list["SubAgentTrace"] = Relationship(
        back_populates="parent_trace",
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "SubAgentTrace.parent_trace_id",
        },
    )

    tool_traces: list["ToolTrace"] = Relationship(back_populates="agent_trace")

    inputs: Dict = Field(
        sa_type=JSONB,
    )

    output: str | None = Field(default=None)

    tokens: int = Field(default=0)

    conversion_rate: int = Field(default=0)  # cost per 1M tokens in cents

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the trace was created.",
    )
    finished_at: datetime = Field(
        default=None,
        description="Timestamp of when the trace was closed.",
        nullable=True,
    )

    @property
    def cost(self) -> float:
        return float(self.tokens * self.conversion_rate) / 1_000_000.0

    # TODO: Use agent router on creation to fetch model conversion rate from router


class SubAgentTrace(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )
    parent_trace_id: UUID = Field(
        foreign_key="agenttrace.id",
        description="Foreign key to the parent agent trace.",
    )
    parent_trace: AgentTrace = Relationship(
        back_populates="sub_agents_traces",
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "SubAgentTrace.parent_trace_id",
        },
    )
    child_trace_id: UUID = Field(
        foreign_key="agenttrace.id",
        description="Foreign key to the child agent trace.",
    )
    child_trace: AgentTrace = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "SubAgentTrace.child_trace_id",
        },
    )

    def __init__(self, session: Session, **data):
        super().__init__(**data)
        if self.parent_trace_id == self.child_trace_id:
            raise ValueError("An trace cannot be a sub-trace of itself.")

        if session.exec(
            select(SubAgentTrace).where(
                SubAgentTrace.child_trace_id == self.child_trace_id
            )
        ).first():
            raise ValueError("One trace cannot have multiple parent traces.")
        elif session.exec(
            select(SubAgentTrace).where(
                (SubAgentTrace.parent_trace_id == self.parent_trace_id)
                & (SubAgentTrace.child_trace_id == self.child_trace_id)
            )
        ).first():
            raise ValueError("This sub-trace relationship already exists.")
        elif session.exec(
            select(SubAgentTrace).where(
                (SubAgentTrace.child_trace_id == self.parent_trace_id)
                & (SubAgentTrace.parent_trace_id == self.child_trace_id)
            )
        ).first():
            raise ValueError("Circular sub-trace relationships are not allowed.")


class RobotException(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    exception_details: Dict = Field(
        sa_type=JSONB,
        nullable=True,
    )

    agent_traces: list[AgentTrace] = Relationship(back_populates="robot_exception")

    infered_success: bool = Field(
        default=False
    )  # Whether the agents reported a successful recovery
    reported_success: bool = Field(
        default=False
    )  # Whether the robot operator reported a successful recovery

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the trace was created.",
    )
    finished_at: datetime = Field(
        default=None,
        description="Timestamp of when the trace was closed.",
        nullable=True,
    )


class GUITrace(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    agent_trace_id: UUID = Field(foreign_key="agenttrace.id")
    agent_trace: AgentTrace = Relationship(
        back_populates="gui_trace",
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "GUITrace.agent_trace_id",
        },
    )

    screenshot_id: UUID | None = Field(
        default=None
    )  # Screenshot name identifier in the configured S3 bucket

    action_type: str = Field(default="")  # e.g., "click", "input", etc.
    action_content: Dict = Field(
        sa_type=JSONB,
        default={},
    )  # Details about the action performed

    success: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the trace was created.",
    )
    finished_at: datetime = Field(
        default=None,
        description="Timestamp of when the trace was closed.",
        nullable=True,
    )


class ToolTrace(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    agent_trace_id: UUID = Field(foreign_key="agenttrace.id")
    agent_trace: AgentTrace = Relationship(
        back_populates="tool_traces",
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "ToolTrace.agent_trace_id",
        },
    )

    tool_id: UUID = Field(foreign_key="tool.id")
    tool: Tool = Relationship(back_populates="traces")

    input: Dict = Field(
        sa_type=JSONB,
        default={},
    )

    output: str = Field(nullable=True, default=None)

    success: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the trace was created.",
    )
    finished_at: datetime = Field(
        default=None,
        description="Timestamp of when the trace was closed.",
        nullable=True,
    )
