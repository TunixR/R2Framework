from typing import Any, AsyncGenerator, Literal, Optional, TypeVar, Union

import pytest
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import (
    Choice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)

from tests.shared.mock_strands_model import MockStrandsModel

# Local typevar to match structured_output signature expectations
T = TypeVar("T")


class DummyOutputModel:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def make_messages() -> list[dict]:
    # The mock ignores inputs and only uses its internal stack. Provide a minimal structure.
    return [{"role": "user", "content": "Hello"}]


def make_tool_specs() -> list[dict]:
    return [{"name": "toolA", "description": "A test tool"}]


def make_system_prompt() -> str:
    return "You are a helpful assistant."


def build_chat_completion_chunk(
    content: str,
    finish_reason: Optional[
        Literal["stop", "length", "tool_calls", "content_filter", "function_call"]
    ] = "stop",
) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id="chunk_1",
        object="chat.completion.chunk",
        created=0,
        model="gpt-mock",
        choices=[
            Choice(
                index=0,
                delta=ChoiceDelta(content=content, role=None, tool_calls=None),
                finish_reason=finish_reason,
                logprobs=None,
            )
        ],
    )


def make_structured_output(obj: Any) -> dict[str, Union[T, Any]]:
    return {"output": obj}


# -------------------------
# Stack management behavior
# -------------------------


def test_stack_push_and_remaining():
    MockStrandsModel.clear_responses()
    assert MockStrandsModel.remaining() == 0

    MockStrandsModel.push_response({"r": 1})  # pyright:ignore
    MockStrandsModel.push_response({"r": 2})  # pyright:ignore
    assert MockStrandsModel.remaining() == 2

    MockStrandsModel.clear_responses()
    assert MockStrandsModel.remaining() == 0


def test_set_responses_replaces_stack():
    MockStrandsModel.clear_responses()
    MockStrandsModel.set_responses([{"r": 1}, {"r": 2}, {"r": 3}])  # pyright:ignore
    assert MockStrandsModel.remaining() == 3

    MockStrandsModel.set_responses([{"r": 42}])  # pyright:ignore
    assert MockStrandsModel.remaining() == 1


# -------------------------
# Synchronous vs async call
# -------------------------


@pytest.mark.asyncio
async def test_stream_formats_chat_completion_chunk():
    MockStrandsModel.clear_responses()

    # Push a ChatCompletionChunk with a single text delta and finish_reason
    MockStrandsModel.push_response(build_chat_completion_chunk("Hello"))
    model = MockStrandsModel()

    gen = model.stream(
        messages=make_messages(),  # type: ignore[arg-type]
        tool_specs=make_tool_specs(),  # type: ignore[arg-type]
        system_prompt=make_system_prompt(),
        tool_choice=None,
        extra="ignored",
    )

    assert isinstance(gen, AsyncGenerator)

    collected = []

    async for chunk in gen:
        collected.append(chunk)

    # Validate formatted sequence
    assert "messageStart" in collected[0]
    assert "contentBlockStart" in collected[1]
    assert (
        "contentBlockDelta" in collected[2]
        and collected[2]["contentBlockDelta"]["delta"]["text"] == "Hello"
    )
    assert "contentBlockStop" in collected[3]
    assert (
        "messageStop" in collected[4]
        and collected[4]["messageStop"]["stopReason"] == "end_turn"
    )


@pytest.mark.asyncio
async def test_stream_handles_multiple_choice_deltas():
    MockStrandsModel.clear_responses()

    # Build a chunk with two choices to ensure multiple deltas are processed
    chunk = ChatCompletionChunk(
        id="chunk_multi",
        object="chat.completion.chunk",
        created=0,
        model="gpt-mock",
        choices=[
            Choice(
                index=0,
                delta=ChoiceDelta(content="Hello", role=None, tool_calls=None),
                finish_reason=None,
                logprobs=None,
            ),
            Choice(
                index=1,
                delta=ChoiceDelta(content=" World", role=None, tool_calls=None),
                finish_reason="stop",
                logprobs=None,
            ),
        ],
    )
    MockStrandsModel.push_response(chunk)
    model = MockStrandsModel()

    gen = model.stream(
        messages=make_messages(),  # type: ignore[arg-type]
        tool_specs=None,
        system_prompt=None,
        tool_choice=None,
        foo="bar",
    )

    collected = []
    async for chunk in gen:
        collected.append(chunk)

    # Expect message_start, content_start, two deltas, content_stop, message_stop
    assert "messageStart" in collected[0]
    assert "contentBlockStart" in collected[1]
    assert (
        "contentBlockDelta" in collected[2]
        and collected[2]["contentBlockDelta"]["delta"]["text"] == "Hello"
    )
    assert (
        "contentBlockDelta" in collected[3]
        and collected[3]["contentBlockDelta"]["delta"]["text"] == " World"
    )
    assert "contentBlockStop" in collected[4]
    assert (
        "messageStop" in collected[5]
        and collected[5]["messageStop"]["stopReason"] == "end_turn"
    )


@pytest.mark.asyncio
async def test_stream_handles_tool_deltas():
    MockStrandsModel.clear_responses()

    # Build a chunk with tool calls
    chunk = ChatCompletionChunk(
        id="chunk_tool",
        object="chat.completion.chunk",
        created=0,
        model="gpt-mock",
        choices=[
            Choice(
                index=0,
                delta=ChoiceDelta(content="Hello", role=None, tool_calls=None),
                finish_reason=None,
                logprobs=None,
            ),
            Choice(
                index=0,
                delta=ChoiceDelta(
                    content=None,
                    role=None,
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=0,
                            id="tool_call_1",
                            function=ChoiceDeltaToolCallFunction(
                                name="toolA", arguments='{"param": "value"}'
                            ),
                            type="function",
                        )
                    ],
                ),
                finish_reason="tool_calls",
                logprobs=None,
            ),
        ],
    )
    MockStrandsModel.push_response(chunk)
    model = MockStrandsModel()

    gen = model.stream(
        messages=make_messages(),  # type: ignore[arg-type]
        tool_specs=make_tool_specs(),  # type: ignore[arg-type]
        system_prompt=None,
        tool_choice=None,
    )

    collected = []
    async for chunk in gen:
        collected.append(chunk)

    # Expect message_start, content_start (tool), tool delta, content_stop, message_stop
    assert "messageStart" in collected[0]
    assert "contentBlockStart" in collected[1]
    assert (
        "contentBlockDelta" in collected[2]
        and collected[2]["contentBlockDelta"]["delta"]["text"] == "Hello"
    )
    assert "contentBlockStop" in collected[3]
    assert (
        "contentBlockStart" in collected[4]
        and collected[4]["contentBlockStart"]["start"]["toolUse"]["inputs"]
        == '{"param": "value"}'
    )
    assert (
        "messageStop" in collected[5]
        and collected[5]["messageStop"]["stopReason"] == "tool_calls"
    )


# -------------------------
# Structured output behavior
# -------------------------


@pytest.mark.asyncio
async def test_structured_output_yields_preloaded_object():
    MockStrandsModel.clear_responses()

    output_obj = DummyOutputModel(value=42)

    # Push into structured output stack
    MockStrandsModel.push_structured_output(output_obj)
    model = MockStrandsModel()

    gen = model.structured_output(
        output_model=DummyOutputModel,  # type: ignore[type-var]
        prompt=make_messages(),  # type: ignore[arg-type]
        system_prompt="context",
        max_output_tokens=256,
    )

    assert isinstance(gen, AsyncGenerator)

    collected = []

    async for event in gen:
        collected.append(event)

    assert len(collected) == 1
    assert "output" in collected[0]
    assert isinstance(collected[0]["output"], DummyOutputModel)
    assert collected[0]["output"].value == 42
    assert MockStrandsModel.remaining_structured_outputs() == 0


#
# -------------------------
# Error handling expectations
# -------------------------


@pytest.mark.asyncio
async def test_stream_raises_on_empty_stack():
    MockStrandsModel.clear_responses()
    model = MockStrandsModel()
    with pytest.raises(AssertionError):
        # Consume the generator to trigger execution and the pop
        async for _ in model.stream(  # type: ignore[arg-type]
            messages=make_messages(),  # type: ignore[arg-type]
            tool_specs=None,
            system_prompt=None,
        ):
            pass


@pytest.mark.asyncio
async def test_structured_output_raises_on_empty_stack():
    MockStrandsModel.clear_responses()
    model = MockStrandsModel()
    with pytest.raises(AssertionError):
        async for _ in model.structured_output(  # type: ignore[type-var, arg-type]
            output_model=DummyOutputModel,
            prompt=make_messages(),  # type: ignore[arg-type]
            system_prompt=None,
        ):
            pass
