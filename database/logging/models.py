import json
from base64 import b64encode
from datetime import datetime
from typing import Any, override
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
)

from database.agents.models import Agent
from database.keys.models import RobotKey
from database.tools.models import Tool
from s3 import S3Client
from templates.recovery_payload import RecoveryPayload


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

    gui_traces: list["GUITrace"] = Relationship(
        back_populates="agent_trace",
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "GUITrace.agent_trace_id",
            "single_parent": True,
        },
        cascade_delete=True,
    )

    sub_agents_traces: list["SubAgentTrace"] = Relationship(
        back_populates="parent_trace",
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "SubAgentTrace.parent_trace_id",
        },
    )

    tool_traces: list["ToolTrace"] = Relationship(back_populates="agent_trace")

    inputs: dict[str, Any] = Field(
        sa_type=JSONB,
    )

    # Input and output messages exchanged with the LLM
    # Each message is a dict with 'role' and 'content' keys
    messages: list[dict[str, Any]] | None = Field(default=None, sa_type=JSONB)

    cost: float = Field(default=0.0)

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the trace was created.",
    )
    finished_at: datetime = Field(
        default=None,
        description="Timestamp of when the trace was closed.",
        nullable=True,
    )

    async def get_makdown_log(
        self, include_subtraces: bool = True, include_tool_traces: bool = True
    ) -> str:
        log = f"# Agent Trace: {self.id}\n"
        log += f"**Agent:** {self.agent.name} ({self.agent.id})\n\n"
        log += f"**Created At:** {self.created_at}\n\n"
        log += f"**Finished At:** {self.finished_at}\n\n"
        log += f"**Cost:** ${self.cost:.6f}\n\n"
        log += f"**Inputs:**\n```\n{json.dumps(self.inputs)}\n```\n\n"
        log += "## Messages:\n"

        timestamped_logs: list[
            tuple[datetime, str]
        ] = []  # We will use this to later sort messages by timestamp
        # Sorry. Dict moment
        if self.messages:
            for i, msg in enumerate(self.messages):
                log_msg = f"\n### Message {i}:\n"
                log_msg += f"- **{msg.get('role', '').capitalize()}:** "
                content = msg.get("content", [])
                for part in content:
                    if "text" in part:
                        log_msg += f"{part['text']}\n"
                    elif "image" in part:
                        image_uuid: str = part["image"].get("uuid", "")
                        if image_uuid == "<uuid_pending>":
                            log_msg += "_Image upload pending..._\n"
                        else:
                            image_b = await S3Client.download_bytes(image_uuid)
                            if image_b:
                                image_url = f"data:image/jpeg;base64,{b64encode(image_b).decode()}"
                                log_msg += f"![Image]({image_url})\n"
                            else:
                                log_msg += "_Image no longer available_\n"
                    else:  # Unknown dict format
                        log_msg += f"{part}\n"
                date = msg.get("timestamp", datetime.now())
                if isinstance(date, str):
                    timestamped_logs.append(
                        (
                            datetime.strptime(
                                date.replace(" ", "T"),
                                "%Y-%m-%dT%H:%M:%S.%f",
                            ),
                            log_msg,
                        )
                    )
                else:
                    timestamped_logs.append(
                        (
                            date,
                            log_msg,
                        )
                    )
        else:
            log += "_No messages recorded._\n"
            return log

        for i, tool_trace in enumerate(self.tool_traces):
            log_msg = f"\n### Tool Trace {i}:\n"
            if include_tool_traces and self.tool_traces:
                log_msg += f"- Tool: {tool_trace.tool.name} ({tool_trace.tool.id})\n"
                log_msg += f"  - Input: {tool_trace.input}\n"
                log_msg += f"  - Output: {tool_trace.output}\n"
                log_msg += f"  - Success: {tool_trace.success}\n"
            timestamped_logs.append((tool_trace.created_at, log_msg))

        for i, sub_trace in enumerate(self.sub_agents_traces):
            log_msg = f"\n### Sub-Agent Trace: {sub_trace.child_trace.agent.name}:\n"
            if include_subtraces and self.sub_agents_traces:
                log_msg += "BEGIN Sub-Agent Trace:\n"
                log_msg += await sub_trace.child_trace.get_makdown_log(
                    include_subtraces=include_subtraces,
                    include_tool_traces=include_tool_traces,
                )
                log_msg += "END Sub-Agent Trace:\n"
            timestamped_logs.append((sub_trace.child_trace.created_at, log_msg))

        timestamped_logs.sort(key=lambda x: x[0])
        for _, log_msg in timestamped_logs:
            log += log_msg

        return log


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

    def __init__(self, **data: object) -> None:
        super().__init__(**data)
        if self.parent_trace_id == self.child_trace_id:
            raise ValueError("A trace cannot be a sub-trace of itself.")


class RobotException(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    exception_details: dict[str, Any] = Field(
        sa_type=JSONB,
        nullable=True,
    )

    robot_key_id: UUID | None = Field(
        default=None,
        foreign_key="robotkey.id",
        description="RobotKey used to submit the exception",
    )
    robot_key: RobotKey | None = Relationship(
        sa_relationship_kwargs={
            "lazy": "noload",
        },
    )

    agent_traces: list[AgentTrace] = Relationship(back_populates="robot_exception")
    recovery_context: "RecoveryContext" = Relationship(back_populates="robot_exception")

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


class RecoveryUiLogEntry(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    recovery_context_id: UUID | None = Field(
        default=None, foreign_key="recoverycontext.id"
    )
    recovery_context: "RecoveryContext" = Relationship(back_populates="ui_log_entries")

    position: int = Field(default=0)
    case_id: str = Field(default="")
    activity_id: str | None = Field(default=None)
    event_id: str = Field(default="")
    event_name: str | None = Field(default=None)
    activity_name: str | None = Field(default=None)
    action_type: str = Field(default="")
    application: str | None = Field(default=None)
    input: str | None = Field(default=None)
    ui_element_target: str | None = Field(default=None)
    ui_group: str | None = Field(default=None)
    timestamp: str = Field(default="")
    previous_state: str | None = Field(default=None)
    current_state: str | None = Field(default=None)


class RecoveryErroredActivity(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    recovery_context_id: UUID | None = Field(
        default=None,
        foreign_key="recoverycontext.id",
        unique=True,
    )
    recovery_context: "RecoveryContext" = Relationship(
        back_populates="errored_activity",
        sa_relationship_kwargs={
            "uselist": False,
        },
    )

    case_id: str = Field(default="")
    activity_id: str | None = Field(default=None)
    event_id: str = Field(default="")
    event_name: str | None = Field(default=None)
    activity_name: str | None = Field(default=None)
    action_type: str = Field(default="")
    application: str | None = Field(default=None)
    input: str | None = Field(default=None)
    error_code: str = Field(default="")
    error_description: str = Field(default="")


class RecoveryContext(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    robot_exception_id: UUID | None = Field(
        default=None, foreign_key="robotexception.id"
    )
    robot_exception: RobotException | None = Relationship(
        sa_relationship_kwargs={"uselist": False}, back_populates="recovery_context"
    )

    task_name: str = Field(default="")
    platform: str = Field(default="")
    os: str = Field(default="")
    variables: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    model: str = Field(default="")

    ui_log_entries: list[RecoveryUiLogEntry] = Relationship(
        back_populates="recovery_context",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
            "order_by": "RecoveryUiLogEntry.position",
        },
        cascade_delete=True,
    )

    errored_activity: RecoveryErroredActivity | None = Relationship(
        back_populates="recovery_context",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "joined",
            "uselist": False,
        },
        cascade_delete=True,
    )

    # TODO: Introduce RecoveryVariableMutation table when variable writebacks are enabled.

    @classmethod
    def from_payload(
        cls,
        *,
        payload: RecoveryPayload | dict[str, Any],
    ) -> "RecoveryContext":
        parsed_payload = (
            payload
            if isinstance(payload, RecoveryPayload)
            else RecoveryPayload.model_validate(payload)
        )

        recovery_context = cls(
            task_name=parsed_payload.task_name,
            platform=parsed_payload.platform,
            os=parsed_payload.os,
            variables=parsed_payload.variables,
            model=parsed_payload.model,
        )

        for position, entry in enumerate(parsed_payload.ui_log):
            recovery_context.ui_log_entries.append(
                RecoveryUiLogEntry(position=position, **entry.model_dump())
            )

        recovery_context.errored_activity = RecoveryErroredActivity(
            **parsed_payload.errored_act.model_dump()
        )

        return recovery_context

    @override
    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(**kwargs)
        data["ui_log"] = [entry.model_dump() for entry in self.ui_log_entries]
        if self.errored_activity:
            data["errored_act"] = self.errored_activity.model_dump()
        else:
            data["errored_act"] = None
        return data


class GUITrace(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    agent_trace_id: UUID = Field(
        foreign_key="agenttrace.id",
        ondelete="CASCADE",
    )
    agent_trace: AgentTrace = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "GUITrace.agent_trace_id",
        },
    )

    screenshot_key: str | None = Field(
        default=None
    )  # Screenshot name identifier in the configured S3 bucket

    action_type: str = Field(default="")  # e.g., "click", "input", etc.
    action_content: dict[str, Any] = Field(
        sa_type=JSONB,
        default={},
    )  # Details about the action performed

    success: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the gui interaction was started.",
    )
    finished_at: datetime = Field(
        default=None,
        description="Timestamp of when the gui interaction was finished.",
        nullable=True,
    )

    @staticmethod
    async def create(screenshot_b: bytes, **data: Any):
        screenshot_key = await S3Client.upload_bytes(
            screenshot_b,
            content_type="image/jpeg",
        )
        return GUITrace(screenshot_key=screenshot_key, **data)

    def __init__(self, **data: Any):
        super().__init__(**data)
        if not self.agent_trace_id:
            raise ValueError("GUITrace must be associated with an AgentTrace.")


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

    input: dict[str, Any] = Field(
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
