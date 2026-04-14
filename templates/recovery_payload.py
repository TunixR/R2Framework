from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator

from templates.common import TemplateModel


class RecoveryActivityAttributes(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    # Common
    state: str = Field(
        ...,
        description="Execution state for the activity node. One of 'past','errored','future'.",
    )
    activity_name: str | None = Field(
        default=None,
        description="Human-readable activity name.",
    )
    activity_type: str | None = Field(
        default=None,
        description="Provider-specific activity type identifier.",
    )
    application: str | None = Field(
        default=None,
        description="Application context for the activity, if applicable.",
    )
    input_type: str | None = Field(
        default=None,
        description="Whether the keyboard input (if any) is raw or variable-based.",
    )
    input_value: str | None = Field(
        default=None,
        description="Value of the raw/variable keyboard input, if applicable.",
    )
    selector_type: str | None = Field(
        default=None,
        description="Type of selector used (e.g., 'selector', 'coords', 'ocr'), if applicable.",
    )
    selector_value: str | None = Field(
        default=None,
        description="Selector string when selector-based automation is available.",
    )
    has_visual_ref: bool = Field(
        default=False,
        description="Marks activity as carrying a visual reference.",
    )
    visual_ref_type: str | None = Field(
        default=None,
        description="Type of visual reference (e.g., Screenshot, CV reference), if has_visual_ref is true.",
    )
    visual_ref_value: str | None = Field(
        default=None,
        description="Value of the visual reference, such as a base64-encoded image string.",
    )

    # Errored
    error_message: str | None = Field(
        default=None,
        description="Error message for errored activities.",
    )

    # Past Activities
    ui_element_target: str | None = Field(
        default=None,
        description="Short str. identifier of interacted element. (e.g., html)",
    )
    ui_group: str | None = Field(
        default=None,
        description="Where is the UI Element located in regards to the compo hierarchy of the screen",
    )
    timestamp: str | None = Field(
        default=None,
        description="ISO 8601 formatted timestamp of when the activity occurred.",
    )
    previous_ui_state: str | None = Field(
        default=None,
        description="State of the UI element before the activity occurred, if applicable.",
    )
    current_ui_state: str | None = Field(
        default=None,
        description="State of the UI element after the activity occurred, if applicable.",
    )

    @model_validator(mode="after")
    def validate_visual_pipeline_support(self) -> RecoveryActivityAttributes:
        has_visual_inputs = self.visual_ref_type or self.visual_ref_value
        descriptor_missing = not self.activity_name

        if self.has_visual_ref and has_visual_inputs and descriptor_missing:
            raise ValueError(
                "visual-data-not-supported: visual-dependent activity requires a non-empty activity_descriptor."
            )

        return self


class RecoveryActivityNode(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique node identifier in the recovery graph.")
    node_type: Literal["activity"] = Field(
        ..., description="Discriminator for activity nodes."
    )
    attributes: RecoveryActivityAttributes


class RecoveryGateAttributes(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    gate_type: str = Field(..., description="Type of gate (e.g., if, switch).")
    condition_statement: str = Field(
        ..., description="Condition expression evaluated by this gate."
    )


class RecoveryGateNode(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique node identifier in the recovery graph.")
    node_type: Literal["gate"] = Field(..., description="Discriminator for gate nodes.")
    attributes: RecoveryGateAttributes


RecoveryNode = Annotated[
    RecoveryActivityNode | RecoveryGateNode,
    Field(discriminator="node_type"),
]


class RecoveryActivityEdge(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Source node id.")
    target: str = Field(..., description="Target node id.")
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary edge attributes.",
    )


class RecoveryActivities(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[RecoveryNode]
    edges: list[RecoveryActivityEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_edge_references(self) -> RecoveryActivities:
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Duplicate node id in recovery activities.")
        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError("Edge references unknown node id.")
        return self


class RecoveryPayload(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    task_name: str
    platform: str
    os: str
    variables: dict[str, Any] = Field(default_factory=dict)
    activities: RecoveryActivities


__all__ = [
    "RecoveryActivities",
    "RecoveryActivityAttributes",
    "RecoveryActivityEdge",
    "RecoveryActivityNode",
    "RecoveryGateAttributes",
    "RecoveryGateNode",
    "RecoveryNode",
    "RecoveryPayload",
]
