"""Strands model that replays a fixed script, so agent loops run without an LLM."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, override

from pydantic import BaseModel
from strands.models import Model


@dataclass(frozen=True)
class ToolCall:
    """A model turn that requests one tool call."""

    name: str
    input: dict[str, Any]


type Turn = str | ToolCall | Exception


class ScriptedModel(Model):
    """Answers each model call with the next turn of a script.

    Text ends the agent loop, a ``ToolCall`` makes Strands run that tool (or
    fill a ``structured_output_model``, whose tool is named after the class),
    and an exception is raised as a model failure. The last turn is repeated
    if the agent asks for more. Every answer reports ``usage`` tokens.
    """

    def __init__(self, *turns: Turn, usage: tuple[int, int] = (12, 4)) -> None:
        assert turns, "a script needs at least one turn"
        self._turns = list(turns)
        self._input_tokens, self._output_tokens = usage
        self.calls = 0

    @override
    def update_config(self, **model_config: Any) -> None:
        return None

    @override
    def get_config(self) -> Any:
        return {}

    @override
    async def structured_output(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        output_model: type[BaseModel],
        prompt: Any,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError
        yield {}

    @override
    async def stream(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        turn = self._turns[min(self.calls, len(self._turns) - 1)]
        self.calls += 1
        if isinstance(turn, Exception):
            raise turn
        yield {"messageStart": {"role": "assistant"}}
        if isinstance(turn, ToolCall):
            tool_use = {"toolUseId": f"call-{self.calls}", "name": turn.name}
            yield {"contentBlockStart": {"start": {"toolUse": tool_use}}}
            yield {
                "contentBlockDelta": {
                    "delta": {"toolUse": {"input": json.dumps(turn.input)}}
                }
            }
            stop_reason = "tool_use"
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": turn}}}
            stop_reason = "end_turn"
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": stop_reason}}
        yield {
            "metadata": {
                "usage": {
                    "inputTokens": self._input_tokens,
                    "outputTokens": self._output_tokens,
                    "totalTokens": self._input_tokens + self._output_tokens,
                },
                "metrics": {"latencyMs": 1},
            }
        }
