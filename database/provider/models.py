import enum
import uuid
from datetime import datetime
from typing import Tuple

import requests
from sqlmodel import Column, Enum, Field, Relationship, SQLModel
from strands.models import Model
from strands.models.openai import OpenAIModel


class Router(SQLModel, table=True):
    class Provider(str, enum.Enum):
        OPENAI = "openai"
        OPENROUTER = "openrouter"

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

    agents: list["Agent"] = (  # noqa: F821 # pyright: ignore[reportUndefinedVariable]
        Relationship(
            back_populates="router",
        )
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the router was created.",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the router was last updated.",
    )

    # Overrides get to not retun the api_key
    def model_dump(self, *args, **kwargs):
        data = super().model_dump(*args, **kwargs)
        data.pop("api_key", None)
        return data

    def get_model(self) -> Model:
        """Return the model instance for the router."""
        if (
            self.provider_type == self.Provider.OPENAI
            or self.provider_type == self.Provider.OPENROUTER
        ):
            return OpenAIModel(
                client_args={
                    "api_key": self.api_key,
                    "base_url": self.api_endpoint,
                },
                model_id=self.model_name,
            )

        raise NotImplementedError(
            f"Router provider {self.provider_type} not yet implemented."
        )

    def get_rates(self) -> Tuple[float, float]:
        """Return the token rates for the router model."""
        if self.provider_type == self.Provider.OPENROUTER:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.get(
                "https://openrouter.ai/api/v1/models", headers=headers
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


class RouterPublic(SQLModel):
    id: uuid.UUID
    model_name: str
    api_endpoint: str
    provider_type: Router.Provider
    created_at: datetime
    updated_at: datetime
