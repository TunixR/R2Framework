"""GenAI spans carry what SigNoz reads: conversations, reasoning parts and tokens."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer
from strands.telemetry import tracer as strands_tracer

import observability.instrumentation.gui_agent as gui_agent_module
from observability.instrumentation.genai import (
    SEMCONV_OPT_IN_ENV,
    GenAITracer,
    TracedOpenAIModel,
    install_genai_tracer,
)
from tests.unit.shared.scripted_model import ToolCall
from tests.unit.shared.tooled_gui_fakes import (
    GUI_TASK_INPUT,
    make_robot,
    make_tooled_gui_agent,
    patch_gui_io,
)


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def tracer(
    exporter: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Tracer]:
    """Route both our spans and the Strands ones to ``exporter``."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("tests.genai")
    monkeypatch.delenv(SEMCONV_OPT_IN_ENV, raising=False)
    monkeypatch.setattr(strands_tracer, "_tracer_instance", None)
    install_genai_tracer("")
    genai_tracer = strands_tracer.get_tracer()
    genai_tracer.tracer = tracer
    monkeypatch.setattr(gui_agent_module, "tracer", tracer)
    yield tracer
    provider.shutdown()


def _spans(exporter: InMemorySpanExporter, name: str) -> list[ReadableSpan]:
    return [span for span in exporter.get_finished_spans() if span.name == name]


def _span_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return span.context.span_id


def _messages(span: ReadableSpan, key: str) -> list[dict[str, Any]]:
    value = (span.attributes or {})[key]
    assert isinstance(value, str)
    return json.loads(value)


def test_install_adds_the_signoz_tokens_to_the_configured_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SEMCONV_OPT_IN_ENV, raising=False)
    monkeypatch.setattr(strands_tracer, "_tracer_instance", None)

    install_genai_tracer("gen_ai_tool_definitions, gen_ai_latest_experimental")

    assert isinstance(strands_tracer.get_tracer(), GenAITracer)
    assert os.environ[SEMCONV_OPT_IN_ENV].split(",") == [
        "gen_ai_tool_definitions",
        "gen_ai_latest_experimental",
        "gen_ai_span_attributes_only",
    ]


def test_reasoning_blocks_become_reasoning_parts(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    genai_tracer = strands_tracer.get_tracer()
    span = genai_tracer.start_model_invoke_span(messages=[], model_id="m")
    message: Any = {
        "role": "assistant",
        "content": [
            {"reasoningContent": {"reasoningText": {"text": "Look first."}}},
            {"text": "Clicking."},
        ],
    }
    usage: Any = {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3}
    metrics: Any = {"latencyMs": 1}
    genai_tracer.end_model_invoke_span(span, message, usage, metrics, "end_turn")

    [chat] = _spans(exporter, "chat")
    [output] = _messages(chat, "gen_ai.output.messages")
    assert output["parts"] == [
        {"type": "reasoning", "content": "Look first."},
        {"type": "text", "content": "Clicking."},
    ]


def test_reasoning_tokens_are_set_on_the_model_call_span(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    model = TracedOpenAIModel(client_args={"api_key": "unused"}, model_id="m")
    usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=7,
        total_tokens=17,
        prompt_tokens_details=None,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=5),
    )

    with tracer.start_as_current_span("chat"):
        chunk = model.format_chunk({"chunk_type": "metadata", "data": usage})

    assert chunk["metadata"]["usage"]["outputTokens"] == 7  # pyright: ignore[reportTypedDictNotRequiredAccess]
    [chat] = _spans(exporter, "chat")
    assert (chat.attributes or {})["gen_ai.usage.reasoning.output_tokens"] == 5


def test_missing_reasoning_tokens_set_nothing(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    model = TracedOpenAIModel(client_args={"api_key": "unused"}, model_id="m")
    usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    with tracer.start_as_current_span("chat"):
        _ = model.format_chunk({"chunk_type": "metadata", "data": usage})

    [chat] = _spans(exporter, "chat")
    assert "gen_ai.usage.reasoning.output_tokens" not in (chat.attributes or {})


@pytest.mark.asyncio
async def test_gui_task_is_one_tree_with_its_conversation(
    tracer: Tracer, exporter: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_gui_io(monkeypatch)
    gui_agent = make_tooled_gui_agent(
        ToolCall("click", {"start_box": [10, 20]}),
        ToolCall("finished", {"content": "Invoice filled"}),
    )

    with tracer.start_as_current_span("recovery.eval"):
        _ = await gui_agent.tooled_guiagent(  # pyright: ignore[reportCallIssue]
            **GUI_TASK_INPUT, override_invocation_state={"websocket": make_robot()}
        )

    spans = exporter.get_finished_spans()
    ids = {_span_id(span) for span in spans}
    orphans = [s.name for s in spans if s.parent and s.parent.span_id not in ids]
    assert orphans == []
    [root] = [span for span in spans if span.parent is None]
    assert root.name == "recovery.eval"

    # ``finished`` cancels the loop, yet its span sits beside the other tools.
    [finished] = _spans(exporter, "execute_tool finished")
    [click] = _spans(exporter, "execute_tool click")
    cycles = {_span_id(s): s for s in _spans(exporter, "execute_event_loop_cycle")}
    assert finished.parent is not None and click.parent is not None
    assert finished.parent.span_id in cycles
    assert cycles[finished.parent.span_id].parent == cycles[click.parent.span_id].parent

    # The conversation is on the spans as attributes, as SigNoz reads it.
    last_chat = _spans(exporter, "chat")[-1]
    roles = [m["role"] for m in _messages(last_chat, "gen_ai.input.messages")]
    assert roles[0] == "user" and "assistant" in roles
    [output] = _messages(last_chat, "gen_ai.output.messages")
    assert output["parts"][0]["type"] == "tool_call"
    assert output["parts"][0]["name"] == "finished"
