import enum
import uuid
from datetime import datetime

from sqlmodel import Column, Enum, Field, Relationship, SQLModel
from strands.models import Model
from strands.models.openai import OpenAIModel


class Router(SQLModel, table=True):
    class Provider(str, enum.Enum):
        OPENAI = "openai"

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
        if self.provider_type == self.Provider.OPENAI:
            return OpenAIModel(
                client_args={
                    "api_key": self.api_key,
                    "base_url": self.api_endpoint,
                },
                model_id=self.model_name,
            )

        raise ValueError(f"Unsupported provider type: {self.provider_type}")
