from typing import Any, Dict

import pytest
from strands.types.tools import JSONSchema

from database.agents.models import Agent, AgentType, Argument
from database.logging.models import (
    ToolTrace,  # noqa: F401 Needs to be imported to register with SQLModel
)
from database.provider.models import Router


def make_router() -> Router:
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


def make_agent(router: Router) -> Agent:
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


def valid_kwargs() -> dict:
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
    agent = make_agent(make_router())
    # Should not raise
    agent.validate_input(**valid_kwargs())


def test_validate_input_missing_argument():
    agent = make_agent(make_router())
    bad_args = valid_kwargs()
    bad_args.pop("variables")
    with pytest.raises(ValueError) as e:
        agent.validate_input(**bad_args)
    assert "Expected" in str(e.value) or "Missing required argument" in str(e.value)


def test_validate_input_wrong_type():
    agent = make_agent(make_router())
    bad_args = valid_kwargs()
    bad_args["action_history"] = "not-a-list"
    with pytest.raises(TypeError) as e:
        agent.validate_input(**bad_args)
    assert "expected type 'list'" in str(e.value)


def test_validate_input_positional_arguments():
    agent = make_agent(make_router())
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
    agent = make_agent(make_router())
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
    agent = make_agent(make_router())
    schema: Dict[str, Any] = agent.get_input_schema().get("json", {})
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
    agent = make_agent(make_router())
    decorated = agent.as_tool()
    assert decorated._tool_name == agent.get_tool_name()
    assert decorated._tool_spec.get("description", "") == agent.description
    # Input schema from decoration should mirror dynamic schema
    tool_schema = decorated._tool_spec.get("inputSchema", JSONSchema()).get("json", {})
    agent_schema = agent.get_input_schema().get("json", {})
    assert tool_schema == agent_schema
    # We validate the input against the JSON schema in the agent
    assert decorated._metadata.validate_input(valid_kwargs()) == {}


# ---------------------------------------------------------------------------
# __call__ behavior (lightweight)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Full __call__ invokes external model; skip in unit tests.")
def test_agent_call_execution():
    """
    Placeholder test for future integration where model invocation can be mocked.
    """
    agent = make_agent(make_router())
    # Would require mocking StrandsAgent to avoid network
    _ = agent  # For linter silence
    assert True
