import json
from base64 import b64encode
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import model_validator
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
from templates.recovery_payload import (
    RecoveryActivityNode as PayloadActivityNode,
)
from templates.recovery_payload import (
    RecoveryGateNode as PayloadGateNode,
)
from templates.recovery_payload import (
    RecoveryPayload,
)


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

    nodes: list["RecoveryGraphNode"] = Relationship(
        back_populates="recovery_context",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
        cascade_delete=True,
    )
    edges: list["RecoveryGraphEdge"] = Relationship(
        back_populates="recovery_context",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
        cascade_delete=True,
    )

    # TODO: Introduce RecoveryVariableMutation table when variable writebacks are enabled.

    @staticmethod
    def _resolve_edge_condition(attributes: dict[str, Any]) -> str | None:
        return (
            attributes.get("condition_statement")
            or attributes.get("condition")
            or attributes.get("label")
        )

    @staticmethod
    def _build_activity_node(node: PayloadActivityNode) -> "RecoveryGraphNode":
        has_visual_ref = bool(node.attributes.has_visual_ref)
        is_non_selector = (
            node.attributes.selector_type or ""
        ).strip().lower() != "selector"
        lacks_activity_descriptor = not (node.attributes.activity_name or "").strip()

        if has_visual_ref and is_non_selector and lacks_activity_descriptor:
            raise NotImplementedError(
                "visual-data-not-supported: non-selector visual activity requires an activity_name descriptor."
            )

        return RecoveryGraphNode(
            node_key=node.id,
            node_type=node.node_type,
            state=node.attributes.state,
            activity_name=node.attributes.activity_name,
            activity_type=node.attributes.activity_type,
            application=node.attributes.application,
            input_type=node.attributes.input_type,
            input_value=node.attributes.input_value,
            selector_type=node.attributes.selector_type,
            selector_value=node.attributes.selector_value,
            has_visual_ref=node.attributes.has_visual_ref,
            visual_ref_type=node.attributes.visual_ref_type,
            visual_ref_value=node.attributes.visual_ref_value,
            error_message=node.attributes.error_message,
            ui_element_target=node.attributes.ui_element_target,
            ui_group=node.attributes.ui_group,
            timestamp=node.attributes.timestamp,
            previous_ui_state=node.attributes.previous_ui_state,
            current_ui_state=node.attributes.current_ui_state,
        )

    @staticmethod
    def _build_gate_node(node: PayloadGateNode) -> "RecoveryGraphNode":
        return RecoveryGraphNode(
            node_key=node.id,
            node_type=node.node_type,
            gate_type=node.attributes.gate_type,
            condition_statement=node.attributes.condition_statement,
        )

    @staticmethod
    def _node_to_payload_attributes(node: "RecoveryGraphNode") -> dict[str, Any]:
        if node.node_type == "activity":
            attributes = {
                "state": node.state,
                "activity_name": node.activity_name,
                "activity_type": node.activity_type,
                "application": node.application,
                "input_type": node.input_type,
                "input_value": node.input_value,
                "selector_type": node.selector_type,
                "selector_value": node.selector_value,
                "has_visual_ref": node.has_visual_ref,
                "visual_ref_type": node.visual_ref_type,
                "visual_ref_value": node.visual_ref_value,
                "error_message": node.error_message,
                "ui_element_target": node.ui_element_target,
                "ui_group": node.ui_group,
                "timestamp": node.timestamp,
                "previous_ui_state": node.previous_ui_state,
                "current_ui_state": node.current_ui_state,
            }
        else:
            attributes = {
                "gate_type": node.gate_type,
                "condition_statement": node.condition_statement,
            }

        return {key: value for key, value in attributes.items() if value is not None}

    @staticmethod
    def _dot_attributes(node: "RecoveryGraphNode") -> dict[str, Any]:
        if node.node_type == "activity":
            return {
                "node_type": node.node_type,
                "state": node.state,
                "activity_name": node.activity_name,
                "activity_type": node.activity_type,
                "application": node.application,
                "input_type": node.input_type,
                "input_value": node.input_value,
                "selector_type": node.selector_type,
                "selector_value": node.selector_value,
                "has_visual_ref": node.has_visual_ref,
                "visual_ref_type": node.visual_ref_type,
                "visual_ref_value": node.visual_ref_value,
                "error_message": node.error_message,
                "ui_element_target": node.ui_element_target,
                "ui_group": node.ui_group,
                "timestamp": node.timestamp,
                "previous_ui_state": node.previous_ui_state,
                "current_ui_state": node.current_ui_state,
            }

        return {
            "node_type": node.node_type,
            "gate_type": node.gate_type,
            "condition_statement": node.condition_statement,
        }

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
        )

        for node in parsed_payload.activities.nodes:
            if isinstance(node, PayloadActivityNode):
                recovery_context.nodes.append(cls._build_activity_node(node))

            if isinstance(node, PayloadGateNode):
                recovery_context.nodes.append(cls._build_gate_node(node))

        for edge in parsed_payload.activities.edges:
            recovery_context.edges.append(
                RecoveryGraphEdge(
                    source_node_key=edge.source,
                    target_node_key=edge.target,
                    condition=cls._resolve_edge_condition(edge.attributes),
                )
            )

        return recovery_context

    def to_payload(self) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        for node in self.nodes:
            nodes.append(
                {
                    "id": node.node_key,
                    "node_type": node.node_type,
                    "attributes": self._node_to_payload_attributes(node),
                }
            )

        edges: list[dict[str, Any]] = []
        for edge in self.edges:
            edges.append(
                {
                    "source": edge.source_node_key,
                    "target": edge.target_node_key,
                    "attributes": (
                        {"condition_statement": edge.condition}
                        if edge.condition
                        else {}
                    ),
                }
            )

        return {
            "task_name": self.task_name,
            "platform": self.platform,
            "os": self.os,
            "variables": self.variables,
            "activities": {
                "nodes": nodes,
                "edges": edges,
            },
        }

    def to_dot(self) -> str:
        def _escape(value: str) -> str:
            return value.replace("\\", "\\\\").replace('"', '\\"')

        def _attr_pairs(attrs: dict[str, Any]) -> str:
            serialized: list[str] = []
            for key, value in attrs.items():
                if value is None:
                    continue
                if isinstance(value, bool):
                    rendered = "true" if value else "false"
                else:
                    rendered = str(value)
                serialized.append(f'{key}="{_escape(rendered)}"')
            return ", ".join(serialized)

        lines: list[str] = ["digraph Activities {"]
        emitted_edges: set[tuple[str, str, str | None]] = set()

        for node in self.nodes:
            node_attrs = self._dot_attributes(node)

            lines.append(f'    "{_escape(node.node_key)}" [{_attr_pairs(node_attrs)}];')

            for edge in self.edges:
                if edge.source_node_key != node.node_key:
                    continue
                edge_key = (edge.source_node_key, edge.target_node_key, edge.condition)
                emitted_edges.add(edge_key)
                edge_attrs = {"condition_statement": edge.condition}
                pairs = _attr_pairs(edge_attrs)
                if pairs:
                    lines.append(
                        f'    "{_escape(edge.source_node_key)}" -> "{_escape(edge.target_node_key)}" [{pairs}];'
                    )
                else:
                    lines.append(
                        f'    "{_escape(edge.source_node_key)}" -> "{_escape(edge.target_node_key)}";'
                    )

        for edge in self.edges:
            edge_key = (edge.source_node_key, edge.target_node_key, edge.condition)
            if edge_key in emitted_edges:
                continue
            edge_attrs = {"condition_statement": edge.condition}
            pairs = _attr_pairs(edge_attrs)
            if pairs:
                lines.append(
                    f'    "{_escape(edge.source_node_key)}" -> "{_escape(edge.target_node_key)}" [{pairs}];'
                )
            else:
                lines.append(
                    f'    "{_escape(edge.source_node_key)}" -> "{_escape(edge.target_node_key)}";'
                )

        lines.append("}")
        return "\n".join(lines)


class RecoveryGraphNode(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    recovery_context_id: UUID | None = Field(
        default=None, foreign_key="recoverycontext.id"
    )
    recovery_context: RecoveryContext = Relationship(back_populates="nodes")

    node_key: str = Field(default="")
    node_type: str = Field(
        default="activity"
    )  # Polymorphism not yet fully supported in SQLModel

    # Activity attributes
    state: str | None = Field(default=None)
    activity_name: str | None = Field(default=None)
    activity_type: str | None = Field(default=None)
    application: str | None = Field(default=None)
    input_type: str | None = Field(default=None)
    input_value: str | None = Field(default=None)
    selector_type: str | None = Field(default=None)
    selector_value: str | None = Field(default=None)
    has_visual_ref: bool = Field(default=False)
    visual_ref_type: str | None = Field(default=None)
    visual_ref_value: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    ui_element_target: str | None = Field(default=None)
    ui_group: str | None = Field(default=None)
    timestamp: str | None = Field(default=None)
    previous_ui_state: str | None = Field(default=None)
    current_ui_state: str | None = Field(default=None)

    # Gate attributes
    gate_type: str | None = Field(default=None)
    condition_statement: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_node_type(self) -> "RecoveryGraphNode":
        if self.node_type not in {"activity", "gate"}:
            raise ValueError("node_type must be one of: activity, gate")
        if self.node_type == "activity" and not self.state:
            raise ValueError("activity nodes require state")
        if self.node_type == "gate" and (
            not self.gate_type or not self.condition_statement
        ):
            raise ValueError("gate nodes require gate_type and condition_statement")
        return self


class RecoveryGraphEdge(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
        primary_key=True,
    )

    recovery_context_id: UUID | None = Field(
        default=None, foreign_key="recoverycontext.id"
    )
    recovery_context: RecoveryContext = Relationship(back_populates="edges")

    source_node_key: str = Field(default="")
    target_node_key: str = Field(default="")
    condition: str | None = Field(default=None)


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
