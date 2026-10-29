import enum
import uuid
from datetime import datetime, timezone
from typing import Any, override

import requests
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Enum, Field, Relationship, SQLModel
from strands.models import Model
from strands.models.openai import OpenAIModel

from database.provider.scripts.image import Qwen2_5ImageResizer


class Router(SQLModel, table=True):
    class Provider(str, enum.Enum):
        OPENAI = "openai"
        OPENROUTER = "openrouter"
        VLLM = "vllm"

    class Capability(str, enum.Enum):
        TEXT = "TEXT"
        VISION = "VISION"

    class VisionBackbone(str, enum.Enum):
        OTHER = "OTHER"
        QWEN2_5 = "QWEN2.5"
        QWEN3_5 = "QWEN3.5"
        QWEN3_8 = "QWEN3.8"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the router.",
        primary_key=True,
    )
    # Encrypted API key for accessing the router service
    api_key: str = Field(..., description="API key for accessing the router service.")
    model_name: str = Field(..., description="Name of the model used by the router.")
    api_endpoint: str = Field(..., description="API endpoint of the provider.")
    provider_type: Provider = Field(
        Provider.OPENAI,
        sa_column=Column(
            Enum(Provider),
            nullable=False,
            default=Provider.OPENAI,
        ),
        description="The type of input the agent can process.",
    )
    capabilities: list[Capability] = Field(
        default_factory=lambda: [Router.Capability.TEXT],
        sa_type=JSONB,
        description="Capabilities supported by the model behind this router.",
    )
    vision_backbone: VisionBackbone | None = Field(
        default=None,
        sa_column=Column(Enum(VisionBackbone), nullable=True),
        description=(
            "Vision backbone used by the model. Defaults to OTHER for "
            "vision-capable routers and stays unset otherwise."
        ),
    )

    agents: list["Agent"] = (  # noqa: F821 # pyright: ignore[reportUndefinedVariable]
        Relationship(
            back_populates="router",
        )
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of when the router was created.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of when the router was last updated.",
    )

    # Overrides get to not retun the api_key
    @override
    def model_dump(self, *args: Any, **kwargs: Any):
        data = super().model_dump(*args, **kwargs)
        data.pop("api_key", None)
        return data

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self.normalize_vision_backbone()

    def supports_capabilities(self, *capabilities: Capability) -> bool:
        """Return whether the router supports every requested capability."""
        available = {self.Capability(capability) for capability in self.capabilities}
        return all(capability in available for capability in capabilities)

    def normalize_vision_backbone(self) -> None:
        """Keep the vision backbone consistent with the router capabilities."""
        available = {self.Capability(capability) for capability in self.capabilities}
        if self.Capability.VISION not in available:
            self.vision_backbone = None
        elif self.vision_backbone is None:
            self.vision_backbone = self.VisionBackbone.OTHER

    def relative_dim(self, height: int, width: int) -> list[int]:
        """Return the image dimensions the model actually interprets.

        This mirrors the coordinate space the vision backbone reports actions
        in: Qwen2.5 uses its smart-resized dimensions, Qwen3.5 uses a fixed
        1000x1000 space, and every other backbone keeps the original size.
        """
        if height <= 0 or width <= 0:
            raise ValueError("Image dimensions must be positive.")

        if self.vision_backbone == self.VisionBackbone.QWEN3_5:
            return [1000, 1000]
        if self.vision_backbone == self.VisionBackbone.QWEN2_5:
            resized_height, resized_width = Qwen2_5ImageResizer.smart_resize(
                height, width
            )
            return [resized_height, resized_width]
        return [height, width]

    def original_coords(
        self, x: float, y: float, width: int, height: int
    ) -> list[float]:
        """Map model-space coordinates back to original-image coordinates."""
        model_height, model_width = self.relative_dim(height, width)
        return [
            x * width / model_width,
            y * height / model_height,
        ]

    def get_model(self) -> Model:
        """Return the model instance for the router."""
        if (
            self.provider_type == self.Provider.OPENAI
            or self.provider_type == self.Provider.VLLM
            or self.provider_type == self.Provider.OPENROUTER
        ):
            return OpenAIModel(
                client_args={
                    "api_key": self.api_key,
                    "base_url": self.api_endpoint,
                },
                stream=True,
                model_id=self.model_name,
            )

        raise NotImplementedError(
            f"Router provider {self.provider_type} not yet implemented."
        )

    def get_rates(self) -> tuple[float, float]:
        """Return the token rates for the router model. Per token"""
        if self.provider_type == self.Provider.OPENROUTER:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.get(
                "https://openrouter.ai/api/v1/models", headers=headers, timeout=10
            )

            if response.status_code == 200:
                models = response.json()["data"]
                # Find specific model
                for model in models:
                    if model["id"] == self.model_name:
                        pricing = model.get("pricing", {})
                        prompt_cost = float(pricing.get("prompt", 0)) * 1_000_000
                        completion_cost = (
                            float(pricing.get("completion", 0)) * 1_000_000
                        )

                        return (prompt_cost, completion_cost)
            return (-1.0, -1.0)

        raise NotImplementedError(
            f"Router provider {self.provider_type} not yet implemented."
        )

    def get_conversation_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate the cost of a conversation based on input and output tokens."""
        prompt_rate, completion_rate = self.get_rates()
        if prompt_rate < 0 or completion_rate < 0:
            return -1.0  # Unknown cost

        total_cost = (input_tokens * prompt_rate) + (output_tokens * completion_rate)
        return total_cost


class RouterPublic(SQLModel):
    id: uuid.UUID
    model_name: str
    api_endpoint: str
    provider_type: Router.Provider
    capabilities: list[Router.Capability]
    vision_backbone: Router.VisionBackbone | None
    created_at: datetime
    updated_at: datetime


class RouterCreate(SQLModel):
    """Schema for creating a new router."""

    api_key: str = Field(description="API key for accessing the router service.")
    model_name: str = Field(description="Name of the model used by the router.")
    api_endpoint: str = Field(description="API endpoint of the provider.")
    provider_type: Router.Provider = Field(
        default=Router.Provider.OPENROUTER,
        description="The provider type backing this router.",
    )
    capabilities: list[Router.Capability] = Field(
        default_factory=lambda: [Router.Capability.TEXT],
        description="Capabilities supported by the model behind this router.",
    )
    vision_backbone: Router.VisionBackbone | None = Field(
        default=None,
        description=(
            "Vision backbone used by the model. Defaults to OTHER for "
            "vision-capable routers and stays unset otherwise."
        ),
    )


class RouterUpdate(SQLModel):
    """Schema for updating an existing router."""

    api_key: str | None = Field(
        default=None, description="API key for accessing the router service."
    )
    model_name: str | None = Field(
        default=None, description="Name of the model used by the router."
    )
    api_endpoint: str | None = Field(
        default=None, description="API endpoint of the provider."
    )
    provider_type: Router.Provider | None = Field(
        default=None, description="The provider type backing this router."
    )
    capabilities: list[Router.Capability] | None = Field(
        default=None,
        description="Capabilities supported by the model behind this router.",
    )
    vision_backbone: Router.VisionBackbone | None = Field(
        default=None,
        description="Vision backbone used by the model behind this router.",
    )
