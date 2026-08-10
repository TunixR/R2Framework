from pydantic import Field

from templates.common import TemplateModel


class ResponseToRPA(TemplateModel):
    success: bool = Field(
        ...,
        description="Indicates whether the recovery was successful and the RPA can continue.",
    )
    continue_from_step: int | None = Field(
        ...,
        description="The step number from which the RPA should continue its execution. PRIORITIZE THE STEP INDICATED BY THE CALLED RECOVERY PATH RESPONSE IF GIVEN. Indexes future activities. If error or future activities have been executed, this should be None.",
    )


__all__ = [
    "ResponseToRPA",
]
