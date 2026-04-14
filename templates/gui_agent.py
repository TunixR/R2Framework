"""Output templates expected from UI error recovery agents."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from templates.common import TemplateModel


class RecoveryReasoning(TemplateModel):
    root_cause: str = Field(
        ...,
        description="Root cause category for the failure (e.g. UI change, timing issue).",
    )
    failure_analysis: str = Field(
        ...,
        description="Analysis of what may have caused the failure.",
    )
    ui_state: str = Field(
        ...,
        description="Description of the current UI state and deviations from the expected one.",
    )
    recovery_approach: str = Field(
        ...,
        description="General approach for recovering the process.",
    )
    challenges: str = Field(
        ...,
        description="Potential challenges or alternative approaches considered.",
    )


class RecoveryDirectReport(TemplateModel):
    reasoning: RecoveryReasoning = Field(
        ...,
        description="Detailed reasoning that explains the recovery process.",
    )
    steps: list[str] = Field(
        ...,
        description="Ordered list of actions taken during the recovery.",
    )
    result: list[str] = Field(
        ...,
        description="Outcome for each executed step.",
    )
    final_outcome: str = Field(
        ...,
        description="Overall recovery outcome (e.g. Success or Failure).",
    )


class RecoveryPlannerReport(TemplateModel):
    reasoning: RecoveryReasoning = Field(
        ...,
        description="Detailed reasoning that supports the proposed recovery plan.",
    )
    steps: list[str] = Field(
        ...,
        description="High level steps grouped into logical units.",
    )


class RecoveryStepExecutionResult(TemplateModel):
    status: str = Field(
        ...,
        description="Execution status for the step (success, replan, abort).",
    )
    message: str = Field(
        ...,
        description="Additional context explaining the status.",
    )


class RecoveryActionDetail(TemplateModel):
    type: str = Field(
        ...,
        description="Action type such as LeftClick, Type, Press, Finish, Scroll, or Wait.",
    )
    target_id: str = Field(
        ...,
        description="Identifier or description for the action target.",
    )


class RecoveryActionPayload(TemplateModel):
    context_analysis: str = Field(
        ...,
        description="Reasoning used to ground the chosen UI action.",
    )
    action: RecoveryActionDetail = Field(
        ...,
        description="Concrete UI action to execute.",
    )


@dataclass(frozen=True)
class TemplateDefinition:
    """Metadata describing a structured output template."""

    name: str
    description: str
    model: type[TemplateModel]


TEMPLATES: dict[str, TemplateDefinition] = {
    "recovery_direct_report": TemplateDefinition(
        name="recovery_direct_report",
        description="Structured summary after executing direct UI recovery actions.",
        model=RecoveryDirectReport,
    ),
    "recovery_planner_report": TemplateDefinition(
        name="recovery_planner_report",
        description="High level plan that groups recovery actions into logical steps.",
        model=RecoveryPlannerReport,
    ),
    "recovery_step_execution_result": TemplateDefinition(
        name="recovery_step_execution_result",
        description="Status payload returned after attempting to execute a recovery step.",
        model=RecoveryStepExecutionResult,
    ),
    "recovery_action_payload": TemplateDefinition(
        name="recovery_action_payload",
        description="Grounded UI action containing a reasoning summary and actionable command.",
        model=RecoveryActionPayload,
    ),
}


__all__ = [
    "TemplateDefinition",
    "TemplateModel",
    "TEMPLATES",
    "RecoveryActionPayload",
    "RecoveryActionDetail",
    "RecoveryDirectReport",
    "RecoveryPlannerReport",
    "RecoveryStepExecutionResult",
    "RecoveryReasoning",
]
