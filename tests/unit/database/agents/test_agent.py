from collections.abc import Callable
from typing import Any

import pytest
from sqlmodel import Session
from strands.types.tools import JSONSchema

from database.agents.models import Agent, AgentType, AgentUpdate, Argument
from database.logging.models import (
    ToolTrace,  # pyright: ignore[reportUnusedImport] # noqa: F401 Needs to be imported to register with SQLModel
)
from database.provider.models import Router


def _make_router() -> Router:
    return Router(
        api_key="test-key",
        model_name="test-model",
        api_endpoint="https://api.test/v1",
        provider_type=Router.Provider.OPENAI,
    )


def make_arguments() -> list[Argument]:
    return [
        Argument(
            name="task",
            description="Task description",
            type="str",
            json_type="string",
        ),
        Argument(
            name="action_history",
            description="List of prior actions",
            type="list",
            json_type="array",
        ),
        Argument(
            name="failed_activity",
            description="Failed activity details",
            type="dict",
            json_type="object",
        ),
        Argument(
            name="future_activities",
            description="Planned future actions",
            type="list",
            json_type="array",
        ),
        Argument(
            name="variables",
            description="Runtime variables",
            type="dict",
            json_type="object",
        ),
    ]


def _make_agent(router: Router) -> Agent:
    """
    Create an in-memory Agent instance (not persisted) for validation tests.
    """
    return Agent(
        name="Validation Test Agent",
        description="Agent used for testing validation logic.",
        prompt="You are a test agent.",
        response_model=None,  # No structured output model for these tests
        input_type=Agent.InputType.TEXT,
        enabled=True,
        router=router,
        type=AgentType.Agent,
        arguments=make_arguments(),
    )


def valid_kwargs() -> dict[str, Any]:
    return {
        "task": "Process invoice",
        "action_history": ["open_app", "login"],
        "failed_activity": {"name": "click_submit", "error": "ElementNotFound"},
        "future_activities": ["validate_submission", "logout"],
        "variables": {"invoice_id": 123, "user": "alice"},
    }


# ---------------------------------------------------------------------------
# Validation logic tests
# ---------------------------------------------------------------------------


def test_validate_input_success():
    agent = _make_agent(_make_router())
    # Should not raise
    agent.validate_input(**valid_kwargs())


def test_validate_input_missing_argument():
    agent = _make_agent(_make_router())
    bad_args = valid_kwargs()
    bad_args.pop("variables")
    with pytest.raises(ValueError) as e:
        agent.validate_input(**bad_args)
    assert "Expected" in str(e.value) or "Missing required argument" in str(e.value)


def test_validate_input_wrong_type():
    agent = _make_agent(_make_router())
    bad_args = valid_kwargs()
    bad_args["action_history"] = "not-a-list"
    with pytest.raises(TypeError) as e:
        agent.validate_input(**bad_args)
    assert "expected type 'list'" in str(e.value)


def test_validate_input_positional_arguments():
    agent = _make_agent(_make_router())
    # Provide all arguments positionally in correct order
    args = [
        "Process invoice",
        ["open_app"],
        {"name": "click_submit"},
        ["validate_submission"],
        {"invoice_id": 42},
    ]
    # Should succeed
    agent.validate_input(*args)

    # Too few positional args
    with pytest.raises(ValueError):
        agent.validate_input("only_one")


def test_validate_input_mixed_args_kwargs():
    agent = _make_agent(_make_router())
    # First two as positional, rest as kwargs
    agent.validate_input(
        "Process invoice",
        ["open_app"],
        failed_activity={"name": "click"},
        future_activities=["validate"],
        variables={"x": 1},
    )

    # Missing one when mixing
    with pytest.raises(ValueError):
        agent.validate_input(
            "Process invoice",
            ["open_app"],
            failed_activity={"name": "click"},
            future_activities=["validate"],
            # variables missing
        )


def test_argument_python_json_type_mapping():
    arg = Argument(
        name="amount",
        description="Numeric amount",
        type="float",
        json_type="number",
    )
    assert arg.type == "float"
    assert arg.json_type == "number"


def test_argument_incompatible_json_type():
    with pytest.raises(ValueError):
        Argument(
            name="bad",
            description="Invalid json type",
            type="int",
            json_type="string",  # Should be 'integer'
        )


# ---------------------------------------------------------------------------
# Schema generation tests
# ---------------------------------------------------------------------------


def test_get_input_schema_matches_arguments():
    agent = _make_agent(_make_router())
    schema: dict[str, Any] = agent.get_input_schema().get("json", {})
    assert schema["type"] == "object"
    props = schema["properties"]
    required = set(schema["required"])
    arg_names = {a.name for a in agent.arguments}
    assert required == arg_names
    for a in agent.arguments:
        assert a.name in props
        assert props[a.name]["type"] == a.json_type
        assert "description" in props[a.name]


def test_as_tool_reflects_agent_metadata():
    agent = _make_agent(_make_router())
    decorated = agent.as_tool()
    assert decorated._tool_name == agent.get_tool_name()  # pyright: ignore[reportPrivateUsage]
    assert decorated._tool_spec.get("description", "") == agent.description  # pyright: ignore[reportPrivateUsage]
    # Input schema from decoration should mirror dynamic schema
    tool_schema = decorated._tool_spec.get("inputSchema", JSONSchema()).get("json", {})  # pyright: ignore[reportPrivateUsage]
    agent_schema = agent.get_input_schema().get("json", {})
    assert tool_schema == agent_schema
    # We validate the input against the JSON schema in the agent
    assert decorated._metadata.validate_input(valid_kwargs()) == {}  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# __call__ behavior (lightweight)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Full __call__ invokes external model; skip in unit tests.")
def test_agent_call_execution():
    """
    Placeholder test for future integration where model invocation can be mocked.
    """
    agent = _make_agent(_make_router())
    # Would require mocking StrandsAgent to avoid network
    _ = agent  # For linter silence
    assert True


# ---------------------------------------------------------------------------
# Router capability alignment
# ---------------------------------------------------------------------------


def test_text_agent_aligns_with_text_capability(
    make_agent: Callable[..., Agent],
    make_router: Callable[..., Router],
):
    agent = make_agent(
        router=make_router(),
        input_type=Agent.InputType.TEXT,
    )

    assert agent.input_type == Agent.InputType.TEXT


def test_agent_construction_rejects_text_agent_on_vision_only_router(
    make_agent: Callable[..., Agent],
    make_router: Callable[..., Router],
):
    router = make_router(
        capabilities=[Router.Capability.VISION],
        persist=False,
    )

    with pytest.raises(ValueError, match="TEXT"):
        make_agent(router=router, input_type=Agent.InputType.TEXT)


def test_agent_construction_rejects_image_agent_without_vision(
    make_agent: Callable[..., Agent],
    make_router: Callable[..., Router],
):
    router = make_router(
        capabilities=[Router.Capability.TEXT],
        persist=False,
    )

    with pytest.raises(ValueError, match="VISION"):
        make_agent(router=router, input_type=Agent.InputType.IMAGETEXT)


def test_imagtext_agent_aligns_with_text_and_vision_capabilities(
    make_agent: Callable[..., Agent],
    make_router: Callable[..., Router],
):
    agent = make_agent(
        router=make_router(
            capabilities=[Router.Capability.TEXT, Router.Capability.VISION]
        ),
        input_type=Agent.InputType.IMAGETEXT,
    )

    assert agent.input_type == Agent.InputType.IMAGETEXT


def test_agent_update_rejects_input_type_not_supported_by_router(
    make_agent: Callable[..., Agent],
    make_router: Callable[..., Router],
):
    router = make_router(capabilities=[Router.Capability.TEXT])
    agent = make_agent(router=router, input_type=Agent.InputType.TEXT)

    with pytest.raises(ValueError, match="VISION"):
        agent.apply_update(
            AgentUpdate(input_type=Agent.InputType.IMAGETEXT),
            router,
        )


def test_agent_update_accepts_compatible_input_type(
    session: Session,
    make_agent: Callable[..., Agent],
    make_router: Callable[..., Router],
):
    router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION]
    )
    agent = make_agent(router=router, input_type=Agent.InputType.TEXT)

    agent.apply_update(
        AgentUpdate(input_type=Agent.InputType.IMAGETEXT),
        router,
    )
    session.add(agent)
    session.commit()

    assert agent.input_type == Agent.InputType.IMAGETEXT
