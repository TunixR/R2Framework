from __future__ import annotations

import asyncio
from typing import (
    Any,
    AsyncGenerator,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    override,
)

from openai.types.chat import ChatCompletionChunk
from strands.models.openai import OpenAIModel
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolSpec

T = TypeVar("T")


class MockStrandsModel(OpenAIModel):
    """
    Test double for strands.models.openai.OpenAIModel.

    This mock model serves responses from a predefined LIFO stack instead of calling
    any external API. It is intended to be injected in tests where code under test
    constructs and uses `OpenAIModel`.

    Usage:
      - Preload the stack with `mockOpenAIModel.set_responses([...])` or
        `mockOpenAIModel.push_response(obj)`.
      - If the stack is empty when a method is invoked, an AssertionError is raised.

    Notes:
      - The mock is deliberately lax about signatures and returns the exact objects
        that were preloaded. Your tests should push whatever structure your
        production code expects (e.g., a dict with `choices`, tool calls, etc.).
      - Methods unrelated to chat-completions can be added on-demand for tests.
    """

    # Class-level LIFO stack shared across all instances
    _response_stack: List[ChatCompletionChunk] = []
    _structured_output_stack: List[Any] = []

    def __init__(
        self,
        client_args: Optional[dict] = None,
        model_id: Optional[str] = None,
        **_: Any,
    ) -> None:
        # Store args for parity with real OpenAIModel constructor, though unused
        self.client_args = client_args or {}
        self.model_id = model_id

    # ---------------------------
    # Stack management utilities
    # ---------------------------

    @classmethod
    def push_response(cls, response: ChatCompletionChunk) -> None:
        """
        Push a single response onto the stack (LIFO).
        """
        cls._response_stack.append(response)

    @classmethod
    def push_structured_output(cls, response: Any) -> None:
        """
        Push a single structured output response onto the structured output stack (LIFO).
        The response will be returned by the next invocation of `structured_output`.
        """
        cls._structured_output_stack.append(response)

    @classmethod
    def set_responses(cls, responses: List[ChatCompletionChunk]) -> None:
        """
        Replace the stack with the provided list of responses (LIFO semantics).
        The last item in the list will be returned first.
        """
        cls._response_stack = list(responses)

    @classmethod
    def set_structured_outputs(cls, responses: List[Any]) -> None:
        """
        Replace the structured output stack with the provided list of responses (LIFO semantics).
        The last item in the list will be returned first.
        """
        cls._structured_output_stack = list(responses)

    @classmethod
    def clear_responses(cls) -> None:
        """
        Clear all preloaded responses.
        """
        cls._response_stack.clear()
        cls._structured_output_stack.clear()

    @classmethod
    def remaining(cls) -> int:
        """
        Return the number of responses left on the stack.
        """
        return len(cls._response_stack)

    @classmethod
    def remaining_structured_outputs(cls) -> int:
        """
        Return the number of structured output responses left on the stack.
        """
        return len(cls._structured_output_stack)

    def _pop_next(self) -> ChatCompletionChunk:
        if not self._response_stack:
            raise AssertionError(
                "mockOpenAIModel stack is empty. Preload responses with `push_response` or `set_responses`."
            )
        # LIFO: pop the last pushed response
        return self._response_stack.pop()

    def _pop_next_structured_output(self) -> Any:
        if not self._structured_output_stack:
            raise AssertionError(
                "mockOpenAIModel structured output stack is empty. Preload responses with `push_structured_output` or `set_structured_outputs`."
            )
        # LIFO: pop the last pushed structured output response
        return self._structured_output_stack.pop()

    # ---------------------------
    # Streaming override (aligns with real OpenAIModel.stream)
    # ---------------------------

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        *,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """

        Async generator for streaming completions.

        If a preloaded response is an iterable (and not str/bytes/dict), yield its items;
        otherwise yield the single response.

        """

        yield self.format_chunk({"chunk_type": "message_start"})
        tool_calls: dict[int, list[Any]] = {}
        data_type = None
        finish_reason = None

        response = self._pop_next()

        for choice in response.choices:
            if choice.delta.content:
                chunks, data_type = self._stream_switch_content("text", data_type)
                for chunk in chunks:
                    yield chunk
                yield self.format_chunk(
                    {
                        "chunk_type": "content_delta",
                        "data_type": data_type,
                        "data": choice.delta.content,
                    }
                )

            for tool_call in choice.delta.tool_calls or []:
                tool_calls.setdefault(tool_call.index, []).append(tool_call)

            if choice.finish_reason:
                finish_reason = choice.finish_reason  # Store for use outside loop
                if data_type:
                    yield self.format_chunk(
                        {"chunk_type": "content_stop", "data_type": data_type}
                    )
                break

        for tool_deltas in tool_calls.values():
            yield self.format_chunk(
                {
                    "chunk_type": "content_start",
                    "data_type": "tool",
                    "data": tool_deltas[0],
                }
            )

            for tool_delta in tool_deltas:
                yield self.format_chunk(
                    {
                        "chunk_type": "content_delta",
                        "data_type": "tool",
                        "data": tool_delta,
                    }
                )

            yield self.format_chunk({"chunk_type": "content_stop", "data_type": "tool"})

        yield self.format_chunk(
            {"chunk_type": "message_stop", "data": finish_reason or "end_turn"}
        )

    # ---------------------------
    # Structured output passthrough
    # ---------------------------

    @override
    async def structured_output(
        self,
        output_model: Type[T],
        prompt: Messages,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """
        Return the next preloaded response instead of making an API call.
        Tests can push either the structured object or a dict representing the structured output.
        """
        await asyncio.sleep(0)
        yield {"output": self._pop_next_structured_output()}
