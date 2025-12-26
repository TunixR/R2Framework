import uuid
from datetime import datetime
from importlib import import_module
from typing import Callable

from sqlmodel import Field, Relationship, SQLModel
from strands.tools.decorator import DecoratedFunctionTool


class Tool(SQLModel, table=True):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the tool.",
        primary_key=True,
    )
    name: str = Field(..., description="Name of the tool.", unique=True)
    description: str = Field(..., description="Description of the tool.")

    # Used to import thge tool at runtime
    fn_module: str = Field(
        ...,
        description="The module path where the tool function is located.",
        unique=True,
    )

    traces: list["ToolTrace"] = Relationship(  # noqa: F821 # pyright:ignore[reportUndefinedVariable]
        back_populates="tool",
        sa_relationship_kwargs={"lazy": "joined"},
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the tool was created.",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the tool was last updated.",
    )

    def get_tool_function(self) -> DecoratedFunctionTool:
        """Dynamically import and return the tool function."""
        module_path, function_name = self.fn_module.rsplit(".", 1)
        try:
            module = import_module(module_path)
        except Exception as e:
            raise ImportError(f"Could not import module '{module_path}': {e}")
        try:
            fn: Callable = getattr(module, function_name)
        except Exception as e:
            raise ImportError(
                f"Could not find function '{function_name}' in module '{module_path}': {e}"
            )
        # Check it has the @tool decorator by looking for the 'name' attribute
        if not isinstance(fn, DecoratedFunctionTool):
            raise ValueError(
                f"The function '{self.fn_module}' is not a valid tool. Make sure it is decorated with @tool."
            )
        return fn

    # Override validation to check the tool can be imported and fn exists
    def __init__(self, **data):
        super().__init__(**data)
        # Validate that the function can be imported successfully
        self.get_tool_function()
