"""Output templates expected from UI error recovery agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Type

from pydantic import BaseModel, Field


class TemplateModel(BaseModel):
    """Base model that provides consistent formatting helpers."""

    class ConfigDict:
        extra = "forbid"

    def __str__(self) -> str:  # pragma: no cover - simple serialization helper
        return json.dumps(self.model_dump(), indent=2, ensure_ascii=True)


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


class UiExceptionReport(TemplateModel):
    result: str = Field(
        ...,
        description="Summary of the recovery execution result.",
    )
    finished_activity: bool = Field(
        ...,
        description="Flag indicating whether the task and all future activities were completed.",
    )
    success: bool = Field(
        ...,
        description="Indicates if the recovery was successful.",
    )
    continue_from_step: int = Field(
        ...,
        description="Index of the next step to resume if unfinished, otherwise -1.",
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
    model: Type[TemplateModel]


TEMPLATES: Dict[str, TemplateDefinition] = {
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
    "ui_exception_report": TemplateDefinition(
        name="ui_exception_report",
        description="Execution summary returned by the ui_exception_handler workflow.",
        model=UiExceptionReport,
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
    "UiExceptionReport",
]
