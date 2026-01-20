import enum
import uuid
from datetime import datetime
from importlib import import_module
from typing import Any, List, Optional

from fastapi import WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import Column
from sqlmodel import Enum, Field, Relationship, SQLModel
from strands import Agent as StrandsAgent
from strands import ToolContext, tool
from strands.hooks import HookProvider
from strands.tools.decorator import DecoratedFunctionTool
from typing_extensions import Dict

from agent_tools.hooks import AgentLoggingHook, LimitToolCounts, ToolLoggingHook
from agent_tools.image import screenshot_bytes

from ..provider.models import Router
from ..tools.models import Tool
from .uitars import standalone_uitars


class Argument(SQLModel, table=True):
    """
    Defines an argument for an agent's input argument when calling it
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the argument.",
        primary_key=True,
    )
    name: str = Field(..., description="Name of the argument.")
    description: str = Field(..., description="Description of the argument.")
    type: str = Field(..., description="Python Type of the argument (e.g., str, int).")
    json_type: str = Field(
        ..., description="JSON Schema type of the argument (e.g., string, number)."
    )

    agent_id: uuid.UUID = Field(
        foreign_key="agent.id",
        description="Foreign key to the agent this argument belongs to.",
    )
    agent: "Agent" = Relationship(
        back_populates="arguments",
    )

    def __str__(self) -> str:
        return f"{self.name}: {self.type} ({self.json_type}) - {self.description}"

    def __init__(self, **data):
        super().__init__(**data)
        # Validate that the type is a valid Python type
        try:
            eval(self.type)
        except Exception as e:
            raise ValueError(
                f"Invalid type '{self.type}' for argument '{self.name}': {e}"
            )

        try:
            valid_json_types = {
                "string",
                "number",
                "integer",
                "boolean",
                "array",
                "object",
                "null",
            }
            if self.json_type not in valid_json_types:
                raise ValueError(
                    f"Invalid JSON type '{self.json_type}' for argument '{self.name}'. Must be one of {valid_json_types}."
                )
        except Exception as e:
            raise ValueError(
                f"Invalid JSON type '{self.json_type}' for argument '{self.name}': {e}"
            )

        # Check python type and json type compatibility
        type_mapping = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
        }
        if self.type in type_mapping:
            expected_json_type = type_mapping[self.type]
            if self.json_type != expected_json_type:
                raise ValueError(
                    f"Type '{self.type}' is not compatible with JSON type '{self.json_type}' for argument '{self.name}'. Expected JSON type: '{expected_json_type}'."
                )


class AgentType(str, enum.Enum):
    Agent = "Agent"
    GatewayAgent = "GatewayAgent"
    GuiAgent = "GuiAgent"
    ErrorAgent = "ErrorAgent"


class Agent(SQLModel, table=True):
    class InputType(str, enum.Enum):
        TEXT = "TEXT"
        IMAGETEXT = "IMAGETEXT"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the agent.",
        primary_key=True,
    )
    name: str = Field(..., description="Name of the agent.")
    description: str = Field(..., description="Description of the agent.")
    prompt: str = Field(..., description="The prompt used to initialize the agent.")
    # Used to import the pydantic model at runtime
    response_model: Optional[str] = Field(
        None,
        description="The module path where the agent's structured response model is located.",
    )
    # TEXT, IMAGETEXT
    input_type: InputType = Field(
        ...,
        sa_column=Column(
            Enum(InputType),
            nullable=False,
            default=InputType.TEXT,
        ),
        description="The type of input the agent can process.",
    )
    enabled: bool = Field(
        True, description="Indicates whether the agent is enabled or not."
    )

    arguments: list["Argument"] = Relationship(
        back_populates="agent",
        sa_relationship_kwargs={"lazy": "joined"},
    )

    router_id: uuid.UUID = Field(
        foreign_key="router.id",
        description="Foreign key to the router used by the agent.",
    )
    router: Router = Relationship(
        back_populates="agents",
        sa_relationship_kwargs={"lazy": "joined"},
    )

    tools: list["AgentTool"] = Relationship(
        back_populates="agent",
        sa_relationship_kwargs={"lazy": "joined"},
    )
    sub_agents: list["SubAgent"] = Relationship(
        back_populates="parent_agent",
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "SubAgent.parent_agent_id",
        },
    )

    traces: list["AgentTrace"] = Relationship(  # noqa: F821 # pyright:ignore[reportUndefinedVariable]
        back_populates="agent",
        sa_relationship_kwargs={"lazy": "joined"},
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the agent was created.",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the agent was last updated.",
    )

    type: AgentType = Field(  # Until polymorphism is supported by sqlmodel
        ...,
        sa_column=Column(
            Enum(AgentType),
            nullable=False,
            default=AgentType.Agent,
        ),
        description="The type of the agent.",
    )

    # __mapper_args__ = {
    #     "polymorphic_identity": "Agent",
    #     "polymorphic_abstract": True,
    #     "polymorphic_on": "type",
    # }

    def get_tool_name(self) -> str:
        """Return the name of the agent as a valid tool name."""
        return self.name.lower().replace(" ", "_")

    def get_tools(self) -> list[Tool]:
        """Return the list of tools associated with the agent."""
        return [at.tool for at in self.tools]

    def get_sub_agents(self) -> list["Agent"]:
        """Return the list of sub-agents associated with the agent."""
        return [sa.child_agent for sa in self.sub_agents if sa.child_agent.enabled]

    def get_tool_limiter(self) -> LimitToolCounts:
        """Return a tool limiter hook provider based on the agent's tool limits."""
        tool_limits = {}
        for at in self.tools:
            if at.limit is not None:
                tool_limits[at.tool.name] = at.limit
        for sa in self.sub_agents:
            if sa.limit is not None:
                tool_limits[sa.child_agent.get_tool_name()] = sa.limit
        return LimitToolCounts(tool_limits)

    def get_logging_hooks(self, invocation_state: Dict[str, Any]) -> List[HookProvider]:
        agent_logging_hook = AgentLoggingHook(
            agent_id=self.id,
            invocation_state=invocation_state,
            parent_trace_id=invocation_state.get("parent_trace_id", None),
            is_gui_agent=self.type == AgentType.GuiAgent,
        )
        invocation_state["parent_trace_id"] = agent_logging_hook.agent_trace_id

        tools = {at.tool.name: at.tool.id for at in self.tools}
        tool_logging_hook = ToolLoggingHook(
            agent_trace_id=agent_logging_hook.agent_trace_id,
            tools=tools,
        )

        return [agent_logging_hook, tool_logging_hook]

    def as_tool(self) -> DecoratedFunctionTool:
        """Dynamically creates the agent tool function for usage within other agents."""

        ## Temporary fix until polymorphism is supported by sqlmodel
        if self.type == AgentType.GuiAgent:  # Actually only supports uitars
            return standalone_uitars

        @tool(
            name=self.get_tool_name(),
            description=self.description,
            inputSchema=self.get_input_schema(),
            context=True,
        )
        async def agent_tool_function(
            tool_context: ToolContext,
        ) -> str | Dict[str, Any]:
            if "websocket" not in tool_context.invocation_state:
                raise ValueError(
                    "WebSocket must be provided in tool context invocation state."
                )
            if "robot_exception_id" not in tool_context.invocation_state:
                raise ValueError(
                    "A valid robot_exception_id must be provided in tool context invocation state."
                )

            return await self(
                invocation_state=tool_context.invocation_state,
                **tool_context.tool_use.get("input", {}),
            )

        return agent_tool_function

    def get_input_schema(self) -> Dict[str, Any]:
        """
        Dinamically computes the tool input schema override based on the agent's defined arguments.

        Example:
            {
                    "json": {
                        "type": "object",
                        "properties": {
                            "shape": {
                                "type": "string",
                                "enum": ["circle", "rectangle"],
                                "description": "The shape type"
                            },
                            "radius": {"type": "number", "description": "Radius for circle"},
                            "width": {"type": "number", "description": "Width for rectangle"},
                            "height": {"type": "number", "description": "Height for rectangle"}
                        },
                        "required": ["shape"]
                    }
                }
        """
        properties = {}
        required = []
        for arg in self.arguments:
            prop = {"type": arg.json_type, "description": arg.description}
            properties[arg.name] = prop
            required.append(arg.name)

        input_schema = {
            "json": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        }
        return input_schema

    def validate_input(self, *args, **kwargs) -> None:
        """
        Validate the input arguments against the agent's defined arguments.
        We expect all arguments to be provided either as keyword arguments.
        """
        if len(args) + len(kwargs) != len(self.arguments):
            raise ValueError(
                f"Expected {len(self.arguments)} arguments, got {len(args) + len(kwargs)}."
            )

        for i, arg in enumerate(self.arguments):
            if i < len(args):
                value = args[i]
            else:
                value = kwargs.get(arg.name)

            if value is None:
                raise ValueError(f"Missing required argument: {arg.name}")

            expected_type = eval(arg.type)
            if not isinstance(value, expected_type):
                raise TypeError(
                    f"Argument '{arg.name}' expected type '{arg.type}', got '{type(value).__name__}'."
                )

    def get_pydantic_response_model(self) -> BaseModel | None:
        """Dynamically import and return the agent's structured response pydantic model."""
        if not self.response_model:
            return None

        module_path, class_name = self.response_model.rsplit(".", 1)
        try:
            module = import_module(module_path)
        except Exception as e:
            raise ImportError(f"Could not import module '{module_path}': {e}")
        try:
            model_class: type[Any] = getattr(module, class_name)
        except Exception as e:
            raise ImportError(
                f"Could not find class '{class_name}' in module '{module_path}': {e}"
            )
        if not issubclass(model_class, BaseModel):
            raise ValueError(
                f"The class '{self.response_model}' is not a valid Pydantic model."
            )
        return model_class  # type: ignore It returns type[BaseModel] but cannot be expressed in type hints without __future__ annotations, which mess up SQLModel

    async def __call__(
        self, invocation_state: dict[str, Any] = {}, *args, **kwargs
    ) -> Dict[str, Any]:
        """
        Dinamically computes tools, subagents, output model and input validation. Calls the agent and returns the final structered response.
        """
        self.validate_input(*args, **kwargs)
        invocation_state["inputs"] = {
            arg.name: kwargs.get(arg.name) for arg in self.arguments
        }

        tools: list[DecoratedFunctionTool] = [
            t.get_tool_function() for t in self.get_tools()
        ]
        sub_agent_tools: list[DecoratedFunctionTool] = [
            sa.as_tool() for sa in self.get_sub_agents()
        ]

        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "text": self.prompt,
                    },
                    {
                        "image": {
                            "format": "jpeg",
                            "source": {
                                "bytes": await screenshot_bytes(
                                    invocation_state["websocket"]
                                ),
                            },
                        },
                    },
                ]
                if self.input_type == self.InputType.IMAGETEXT
                else [
                    {
                        "text": self.prompt,
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "text": "I understand the instructions. I will proceed once you give me all neccesary values.",
                    }
                ],
            },
        ]

        model = self.router.get_model()

        hooks = [self.get_tool_limiter(), *self.get_logging_hooks(invocation_state)]

        strands_agent = StrandsAgent(
            model=model,
            tools=tools + sub_agent_tools,
            hooks=hooks,
            messages=messages,  # type: ignore This works fine
        )

        input_tokens = 0
        output_tokens = 0

        try:
            instruction = "\n".join(
                [f"{arg.name}: {kwargs.get(arg.name)}" for arg in self.arguments]
            )

            mid = await strands_agent.invoke_async(
                instruction,
                invocation_state=invocation_state,
            )

            input_tokens = mid.metrics.accumulated_usage.get("inputTokens", 0)
            output_tokens = mid.metrics.accumulated_usage.get("outputTokens", 0)

            response: BaseModel = (
                await strands_agent.invoke_async(
                    "Given our conversation so far, please provide a report using structured output with the given tool.",
                    structured_output_model=self.get_pydantic_response_model(),  # type: ignore It returns type[BaseModel] but cannot be expressed in type hints without __future__ annotations, which mess up SQLModel
                    invocation_state=invocation_state,
                )
            ).structured_output

            input_tokens = mid.metrics.accumulated_usage.get("inputTokens", 0)
            output_tokens = mid.metrics.accumulated_usage.get("outputTokens", 0)

            return response.model_dump()
        except WebSocketDisconnect as _:
            raise
        except Exception as e:
            raise
        finally:
            cost = self.router.get_conversation_cost(input_tokens, output_tokens)
            hooks[1].update_trace(finished=True, cost=cost)  # type: AgentLoggingHook

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        # Validate that the response model can be imported successfully
        self.get_pydantic_response_model()


# class GatewayAgent(Agent):
#     id: uuid.UUID = Field(
#         ...,
#         description="Unique identifier for the gateway agent.",
#         foreign_key="agent.id",
#     )

#     __mapper_args__ = {
#         "polymorphic_identity": "GatewayAgent",
#     }


class ErrorAgent(SQLModel):
    __mapper_args__ = {
        "polymorphic_identity": "GatewayAgent",
    }


class SubAgent(SQLModel, table=True):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the sub-agent.",
        primary_key=True,
    )
    parent_agent_id: uuid.UUID = Field(
        foreign_key="agent.id",
        description="Foreign key to the parent agent.",
    )
    parent_agent: Agent = Relationship(
        back_populates="sub_agents",
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "SubAgent.parent_agent_id",
        },
    )
    child_agent_id: uuid.UUID = Field(
        foreign_key="agent.id",
        description="Foreign key to the child agent.",
    )
    child_agent: Agent = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "SubAgent.child_agent_id",
        },
    )

    limit: Optional[int] = Field(
        None,
        description="Optional limit on the number of times the sub-agent can be called by the parent agent.",
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the sub-agent association was created.",
    )

    def __init__(self, **data):
        super().__init__(**data)
        if self.parent_agent_id == self.child_agent_id:
            raise ValueError("An agent cannot be a sub-agent of itself.")


class AgentTool(SQLModel, table=True):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the agent-tool association.",
        primary_key=True,
    )
    agent_id: uuid.UUID = Field(
        foreign_key="agent.id",
        description="Foreign key to the agent.",
    )
    agent: Agent = Relationship(
        back_populates="tools",
        sa_relationship_kwargs={"lazy": "joined"},
    )
    tool_id: uuid.UUID = Field(
        foreign_key="tool.id",
        description="Foreign key to the tool.",
    )
    tool: Tool = Relationship(
        sa_relationship_kwargs={"lazy": "joined"},
    )

    limit: Optional[int] = Field(
        None,
        description="Optional limit on the number of times the tool can be called by the agent.",
    )
    required: bool = Field(
        False,
        description="Indicates whether the tool must be called by the agent at least once.",
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of when the agent-tool association was created.",
    )
