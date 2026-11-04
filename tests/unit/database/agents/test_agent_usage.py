"""Token accounting of ``Agent.__call__`` across its two Strands invocations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

import database.agents.models as agent_models
from agent_tools.hooks import AgentLoggingHook
from database.agents.models import Agent
from database.provider.models import Router


class _Report(BaseModel):
    done: bool


class _FakeStrandsAgent:
    """Mimics Strands: every result shares one cumulative metrics object."""

    usage_per_call = (
        {"inputTokens": 100, "outputTokens": 10},
        {"inputTokens": 40, "outputTokens": 5},
    )

    def __init__(self, **_: Any) -> None:
        self.event_loop_metrics = SimpleNamespace(
            accumulated_usage={"inputTokens": 0, "outputTokens": 0}
        )
        self._calls = 0

    async def invoke_async(self, *_: Any, **kwargs: Any) -> SimpleNamespace:
        usage = self.usage_per_call[self._calls]
        self._calls += 1
        for key, value in usage.items():
            self.event_loop_metrics.accumulated_usage[key] += value
        if self._calls == 2 and kwargs.get("fail"):
            raise RuntimeError("structured output failed")
        return SimpleNamespace(
            metrics=self.event_loop_metrics,
            structured_output=_Report(done=True) if self._calls == 2 else None,
        )


@pytest.fixture
def agent(
    make_agent: Callable[..., Agent],
    mock_router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> Agent:
    async def _no_screenshot(_websocket: object) -> bytes:
        return b""

    monkeypatch.setattr(agent_models, "StrandsAgent", _FakeStrandsAgent)
    monkeypatch.setattr(agent_models, "screenshot_bytes", _no_screenshot)
    monkeypatch.setattr(Router, "get_model", lambda _self: object())
    monkeypatch.setattr(Agent, "get_pydantic_response_model", lambda _self: _Report)
    monkeypatch.setattr(
        Router, "get_conversation_cost", lambda _self, i, o: i * 0.001 + o * 0.01
    )
    monkeypatch.setattr(AgentLoggingHook, "update_trace", lambda *_a, **_k: None)
    return make_agent(router=mock_router)


@pytest.mark.asyncio
async def test_usage_sums_both_invocations(
    agent: Agent, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    result = await agent(invocation_state={"websocket": None})

    assert result == {"done": True}
    [usage] = [
        r for r in caplog.records if vars(r).get("otel.event.name") == "agent.usage"
    ]
    assert vars(usage)["gen_ai.usage.input_tokens"] == 140
    assert vars(usage)["gen_ai.usage.output_tokens"] == 15
    assert vars(usage)["agent.cost"] == pytest.approx(0.29)


@pytest.mark.asyncio
async def test_usage_is_reported_when_the_second_invocation_fails(
    agent: Agent, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO)
    original = _FakeStrandsAgent.invoke_async

    async def _failing(
        self: _FakeStrandsAgent, *args: Any, **kwargs: Any
    ) -> SimpleNamespace:
        return await original(self, *args, **kwargs, fail=True)

    monkeypatch.setattr(_FakeStrandsAgent, "invoke_async", _failing)

    with pytest.raises(RuntimeError):
        await agent(invocation_state={"websocket": None})

    [usage] = [
        r for r in caplog.records if vars(r).get("otel.event.name") == "agent.usage"
    ]
    assert vars(usage)["gen_ai.usage.input_tokens"] == 140
