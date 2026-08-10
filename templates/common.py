from __future__ import annotations

import json
from typing import override

from pydantic import BaseModel, ConfigDict


class TemplateModel(BaseModel):
    """Base model that provides consistent formatting helpers."""

    model_config = ConfigDict(extra="forbid")

    @override
    def __str__(self) -> str:  # pragma: no cover - simple serialization helper
        return json.dumps(self.model_dump(), indent=2, ensure_ascii=True)
