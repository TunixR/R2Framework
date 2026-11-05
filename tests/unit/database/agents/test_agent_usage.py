"""Token accounting of ``Agent.__call__`` across its two Strands invocations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

import database.agents.models as agent_models
from database.agents.models import Agent, Argument
from database.provider.models import Router
from tests.unit.shared.scripted_model import ScriptedModel, ToolCall, Turn


class _Report(BaseModel):
    done: bool


def _usage_event(caplog: pytest.LogCaptureFixture) -> dict[str, Any]:
    [usage] = [
        r for r in caplog.records if vars(r).get("otel.event.name") == "agent.usage"
    ]
    return vars(usage)


@pytest.fixture
def run_agent(
    make_agent: Callable[..., Agent],
    mock_router: Router,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> Callable[..., Any]:
    """Run ``Agent.__call__`` on a real Strands agent whose model plays ``turns``."""

    async def _no_screenshot(_websocket: object) -> bytes:
        return b""

    monkeypatch.setattr(agent_models, "screenshot_bytes", _no_screenshot)
    monkeypatch.setattr(Agent, "get_pydantic_response_model", lambda _self: _Report)
    monkeypatch.setattr(
        Router, "get_conversation_cost", lambda _self, i, o: i * 0.001 + o * 0.01
    )
    # The logging hooks write audit rows to Postgres; this test is about tokens.
    monkeypatch.setattr(Agent, "get_logging_hooks", lambda _self, _state: [])
    caplog.set_level(logging.INFO)
    # Strands rejects a blank prompt, and the instruction lists the arguments.
    task = Argument(name="task", description="Task", type="str", json_type="string")
    agent = make_agent(router=mock_router, arguments=[task])

    async def _run(*turns: Turn) -> tuple[Any, ScriptedModel]:
        model = ScriptedModel(*turns, usage=(100, 10))
        monkeypatch.setattr(Router, "get_model", lambda _self: model)
        result = await agent({"websocket": None}, task="Recover the robot")
        return result, model

    return _run


@pytest.mark.asyncio
async def test_usage_sums_both_invocations(
    run_agent: Callable[..., Any], caplog: pytest.LogCaptureFixture
) -> None:
    # First invocation answers in text, the second fills the report.
    result, model = await run_agent(
        "Looked at the robot.", ToolCall("_Report", {"done": True})
    )

    assert result == {"done": True}
    assert model.calls >= 2
    usage = _usage_event(caplog)
    assert usage["gen_ai.usage.input_tokens"] == 100 * model.calls
    assert usage["gen_ai.usage.output_tokens"] == 10 * model.calls
    assert usage["agent.cost"] == pytest.approx(0.2 * model.calls)


@pytest.mark.asyncio
async def test_usage_is_reported_when_the_second_invocation_fails(
    run_agent: Callable[..., Any], caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(RuntimeError):
        await run_agent("Looked at the robot.", RuntimeError("model unavailable"))

    # Tokens of the first invocation are still accounted for.
    assert _usage_event(caplog)["gen_ai.usage.input_tokens"] == 100
