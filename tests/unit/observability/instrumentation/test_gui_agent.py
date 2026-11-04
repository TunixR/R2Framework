import logging
from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

import observability.instrumentation.gui_agent as gui_agent_module
from observability.instrumentation.gui_agent import GuiTaskTelemetry


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def tracer(
    exporter: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Tracer]:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("tests.gui")
    monkeypatch.setattr(gui_agent_module, "tracer", tracer)
    yield tracer
    provider.shutdown()


def _spans(exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    return {span.name: span for span in exporter.get_finished_spans()}


def _task(**overrides: object) -> GuiTaskTelemetry:
    fields: dict[str, object] = {
        "task": "Fill the invoice form",
        "model": "invoice-process",
        "ui_log": [{}, {}],
        "errored_act": {"activity_id": 3},
    }
    return GuiTaskTelemetry(**{**fields, **overrides})  # pyright: ignore[reportArgumentType]


def test_task_describes_the_tool_span_and_outcome(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    with tracer.start_as_current_span("execute_tool gui_agent"):
        telemetry = _task(task="x" * 500)
        telemetry.done(iterations=3)

    attributes = _spans(exporter)["execute_tool gui_agent"].attributes or {}
    assert len(str(attributes["gui.task.name"])) == 120
    assert attributes["gui.task.process_model"] == "invoice-process"
    assert attributes["gui.task.ui_log_count"] == 2
    assert attributes["gui.task.has_errored_activity"] is True
    assert attributes["gui.task.iterations"] == 3
    assert attributes["gui.task.outcome"] == "done"


def test_actions_and_screenshots_are_child_spans(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    with tracer.start_as_current_span("execute_tool gui_agent") as tool_span:
        telemetry = _task()
        with telemetry.action(1, "click") as action:
            action.result(True)
        with telemetry.screenshot() as shot:
            shot.taken(b"jpeg", 800, 600)

    spans = _spans(exporter)
    action_span = spans["gui.action"]
    assert action_span.parent is not None
    assert action_span.parent.span_id == tool_span.get_span_context().span_id
    assert action_span.attributes == {
        "gui.action.iteration": 1,
        "gui.action.type": "click",
        "gui.action.success": True,
    }
    assert spans["gui.screenshot"].attributes == {
        "gui.screenshot.width": 800,
        "gui.screenshot.height": 600,
        "gui.screenshot.size": 4,
    }


def test_failed_action_is_recorded_on_its_span(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    telemetry = _task()
    with pytest.raises(RuntimeError), telemetry.action(2, "type") as action:
        action.result(False)
        error = RuntimeError("Action execution failed on client side")
        action.failed(error)
        raise error

    action_span = _spans(exporter)["gui.action"]
    assert action_span.status.status_code.name == "ERROR"
    assert [event.name for event in action_span.events] == ["exception"]


def test_retry_and_max_actions_are_logged(
    tracer: Tracer,  # pyright: ignore[reportUnusedParameter]
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    telemetry = _task()

    telemetry.retry(4, ValueError("Action can't parse: click(start_box=)"))
    telemetry.max_actions_exceeded(iterations=20, max_actions=20)

    events = {
        vars(record)["otel.event.name"]: vars(record) for record in caplog.records
    }
    assert events["gui.action_retry"]["error.type"] == "ValueError"
    assert events["gui.action_retry"]["gui.action.iteration"] == 4
    assert events["gui.max_actions_exceeded"]["gui.task.max_actions"] == 20
