from datetime import datetime, timedelta
from typing import Any

import pytest

from database.agents.models import Agent, AgentType
from database.logging.models import AgentTrace, SubAgentTrace, ToolTrace
from database.provider.models import Router
from tests.unit.conftest.mock_s3_client_fixture import (
    mock_s3client_model,  # pyright: ignore[reportUnusedImport] # noqa: F401 We need to import this fixture for it to activate
)


def make_router() -> Router:
    return Router(
        api_key="test-key",
        model_name="test-model",
        api_endpoint="https://api.test/v1",
        provider_type=Router.Provider.OPENAI,
    )


def make_agent() -> Agent:
    return Agent(
        name="Markdown Logger",
        description="Agent used for testing markdown log generation.",
        prompt="You are a test agent.",
        response_model=None,
        input_type=Agent.InputType.TEXT,
        enabled=True,
        router=make_router(),
        type=AgentType.Agent,
        arguments=[],
    )


def make_agent_trace(
    agent: Agent,
    *,
    inputs: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
    created_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> AgentTrace:
    now = datetime.now()
    return AgentTrace(
        agent_id=agent.id,
        agent=agent,
        inputs=inputs or {"task": "do something"},
        messages=messages,
        created_at=created_at or now,
        finished_at=finished_at or now,
    )


def make_tool(monkeypatch, name: str = "echo"):  # pyright: ignore[reportMissingParameterType]
    from database.tools.models import Tool as DBTool

    # Bypass validation in Tool.__init__ that imports a module
    monkeypatch.setattr(
        DBTool,
        "get_tool_function",
        lambda self: object(),  # pyright: ignore[reportUnknownLambdaType]
        raising=True,
    )
    return DBTool(name=name, description=f"{name} tool", fn_module="tests.fake:echo")


def add_tool_trace(
    agent_trace,  # pyright: ignore[reportMissingParameterType]
    tool,  # pyright: ignore[reportMissingParameterType]
    created_at,  # pyright: ignore[reportMissingParameterType]
    input_data,  # pyright: ignore[reportMissingParameterType]
    output,  # pyright: ignore[reportMissingParameterType]
    success: bool = True,
):
    tt = ToolTrace(
        agent_trace_id=agent_trace.id,
        agent_trace=agent_trace,
        tool_id=tool.id,
        tool=tool,
        input=input_data,
        output=output,
        success=success,
        created_at=created_at,
    )
    agent_trace.tool_traces.append(tt)
    return tt


def add_sub_trace(parent_trace, child_trace, monkeypatch):  # pyright: ignore[reportMissingParameterType, reportUnusedParameter]
    sub = SubAgentTrace(
        session=None,
        parent_trace_id=parent_trace.id,
        child_trace_id=child_trace.id,
    )
    setattr(sub, "parent_trace", parent_trace)
    setattr(sub, "child_trace", child_trace)

    parent_trace.sub_agents_traces.append(sub)
    return sub


@pytest.mark.asyncio
async def test_no_messages_returns_early_with_no_messages_section_only():
    agent = make_agent()
    trace = make_agent_trace(agent, messages=None, inputs={"task": "T1"})

    log = await trace.get_makdown_log()

    # Header basics
    assert f"# Agent Trace: {trace.id}" in log
    assert f"**Agent:** {agent.name} ({agent.id})" in log
    assert "**Cost:** $" in log  # don't depend on exact float formatting
    assert "**Inputs:**" in log
    assert '```\n{"task": "T1"}\n```' in log

    # No messages path
    assert "## Messages:" in log
    assert "_No messages recorded._" in log

    # Early return means no tool traces or subtraces appear
    assert "### Tool Trace" not in log
    assert "### Sub-Agent Trace" not in log
    assert "BEGIN Sub-Agent Trace" not in log


@pytest.mark.asyncio
async def test_messages_are_rendered_in_log_after_bug_fix():
    agent = make_agent()
    msgs = [
        {
            "role": "user",
            "content": [
                {"text": "Hello world"},
                {"text": "How are you?"},
            ],
            "timestamp": datetime.now(),
        },
        {
            "role": "assistant",
            "content": [{"text": "Response from assistant"}],
            "timestamp": datetime.now(),
        },
    ]
    trace = make_agent_trace(agent, messages=msgs)

    log = await trace.get_makdown_log()

    # Messages section is present
    assert "## Messages:" in log

    # User text appears
    assert "Hello world" in log
    assert "How are you?" in log

    # Assistant text appears
    assert "Response from assistant" in log


@pytest.mark.parametrize(
    "include_sub, include_tools",
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
@pytest.mark.asyncio
async def test_flags_control_presence_of_tool_and_sub_sections(
    include_sub,  # pyright: ignore[reportMissingParameterType]
    include_tools,  # pyright: ignore[reportMissingParameterType]
    monkeypatch,  # pyright: ignore[reportMissingParameterType]
):
    agent = make_agent()

    # Construct timestamps to test ordering
    base = datetime.now()
    t1 = base
    t2 = base + timedelta(seconds=1)
    t3 = base + timedelta(seconds=2)
    t4 = base + timedelta(seconds=3)
    t5 = base + timedelta(seconds=4)
    t6 = base + timedelta(seconds=5)

    # Parent trace with two messages
    parent = make_agent_trace(
        agent,
        messages=[
            {"role": "user", "content": [{"text": "FIRST"}], "timestamp": t1},
            {"role": "assistant", "content": [{"text": "SECOND"}], "timestamp": t3},
        ],
    )

    # Real ToolTrace using patched Tool validation
    tool = make_tool(monkeypatch, name="echo")
    _ = add_tool_trace(
        parent,
        tool=tool,
        created_at=t2,
        input_data={"text": "ping"},
        output="pong",
        success=True,
    )

    # Sub-agent (child) with its own tool call (edge case 1)
    child_agent = make_agent()
    child = make_agent_trace(
        child_agent,
        messages=[
            {"role": "assistant", "content": [{"text": "CHILD"}], "timestamp": t4}
        ],
        inputs={"task": "child"},
        created_at=t4,
    )
    _ = add_tool_trace(
        child,
        tool=tool,
        created_at=t5,
        input_data={"text": "child ping"},
        output="child pong",
        success=True,
    )
    add_sub_trace(parent, child, monkeypatch)

    # Sub-agent of sub-agent (grandchild) to test nesting (edge case 2)
    grandchild_agent = make_agent()
    grandchild = make_agent_trace(
        grandchild_agent,
        messages=[
            {"role": "assistant", "content": [{"text": "GRANDCHILD"}], "timestamp": t6}
        ],
        inputs={"task": "grandchild"},
        created_at=t6,
    )
    add_sub_trace(child, grandchild, monkeypatch)

    log = await parent.get_makdown_log(
        include_subtraces=include_sub,
        include_tool_traces=include_tools,
    )

    # Messages of parent should always be present
    assert "FIRST" in log and "SECOND" in log

    # Tool traces presence controlled by flag; includes parent's and child's tools
    assert "### Tool Trace" in log
    if include_tools:
        assert "Tool: echo" in log
        assert "Input: {'text': 'ping'}" in log
        assert "Output: pong" in log
        if include_sub:
            assert "child ping" in log
            assert "child pong" in log
    else:
        assert "Tool: echo" not in log
        assert "Input: {'text': 'ping'}" not in log
        assert "Output: pong" not in log

    # Sub-traces presence controlled by flag; check both child and grandchild
    assert "### Sub-Agent Trace" in log
    if include_sub:
        assert f"# Agent Trace: {child.id}" in log
        assert f"# Agent Trace: {grandchild.id}" in log
    else:
        assert f"# Agent Trace: {child.id}" not in log
        assert f"# Agent Trace: {grandchild.id}" not in log

    # Ordering by timestamps: FIRST (t1) < Tool Trace (t2) < SECOND (t3) < Sub-Agent Trace (t4+)
    if include_sub and include_tools:
        p1 = log.find("FIRST")
        ptool = log.find("### Tool Trace")
        p2 = log.find("SECOND")
        psub = log.find("### Sub-Agent Trace")
        assert p1 != -1 and ptool != -1 and p2 != -1 and psub != -1
        assert p1 < ptool < p2 < psub
