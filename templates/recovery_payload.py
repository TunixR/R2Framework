from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field, field_validator

from templates.common import TemplateModel


class RecoveryUiLogEntry(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    model_act_id: str
    activity_name: str | None
    action_type: str
    application: str | None
    input: str | None
    ui_element_target: str | None
    ui_group: str | None
    timestamp: str
    previous_state: str | None
    current_state: str | None

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_iso8601(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                "timestamp must be a valid ISO-8601 datetime string"
            ) from exc
        return value


class RecoveryErroredAct(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    model_act_id: str
    activity_name: str | None
    action_type: str
    application: str | None
    input: str | None
    error_code: str
    error_description: str


class RecoveryPayload(TemplateModel):
    model_config = ConfigDict(extra="forbid")

    task_name: str
    platform: str
    os: str
    variables: dict[str, Any] = Field(default_factory=dict)
    ui_log: list[RecoveryUiLogEntry]
    errored_act: RecoveryErroredAct
    model: str

    @field_validator("model")
    @classmethod
    def validate_model_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must be a non-empty string")
        return value


__all__ = [
    "RecoveryErroredAct",
    "RecoveryPayload",
    "RecoveryUiLogEntry",
]
