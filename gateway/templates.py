from __future__ import annotations

import json

from pydantic import BaseModel, Field


class TemplateModel(BaseModel):
    """Base model that provides consistent formatting helpers."""

    class Config:
        extra = "forbid"

    def __str__(self) -> str:  # pragma: no cover - simple serialization helper
        return json.dumps(self.model_dump(), indent=2, ensure_ascii=True)


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
