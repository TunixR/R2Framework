from pydantic import Field

from templates.common import TemplateModel


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


__all__ = [
    "UiExceptionReport",
]
