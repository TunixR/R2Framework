"""TooledGuiAgent reports its task, actions and screenshots through GuiTaskTelemetry."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

import database.agents.tooled_gui_agent as tooled_module
import observability.instrumentation.gui_agent as gui_agent_module
from database.agents.tooled_gui_agent import TooledGuiAgent
from tests.unit.shared.fake_websocket import FakeWebSocket
from tests.unit.shared.scripted_model import ToolCall
from tests.unit.shared.tooled_gui_fakes import (
    GUI_TASK_INPUT,
    make_robot,
    make_tooled_gui_agent,
    patch_gui_io,
)

pytestmark = pytest.mark.asyncio

TYPED_SECRET = "typed-secret-value"


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def tracer(
    exporter: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Tracer]:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("tests.tooled_gui")
    monkeypatch.setattr(gui_agent_module, "tracer", tracer)
    yield tracer
    provider.shutdown()


@pytest.fixture(autouse=True)
def _no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_gui_io(monkeypatch)


async def _run(
    tracer: Tracer, gui_agent: TooledGuiAgent, robot: FakeWebSocket
) -> tuple[Any, int]:
    """Call the tool inside a stand-in for its Strands ``execute_tool`` span."""
    with tracer.start_as_current_span("execute_tool tooled_guiagent"):
        result = await gui_agent.tooled_guiagent(  # pyright: ignore[reportCallIssue]
            **GUI_TASK_INPUT,
            override_invocation_state={"websocket": robot},
        )
    return result, len(robot.actions)


def _spans(exporter: InMemorySpanExporter, name: str) -> list[ReadableSpan]:
    return [span for span in exporter.get_finished_spans() if span.name == name]


def _task_attributes(exporter: InMemorySpanExporter) -> dict[str, Any]:
    [task] = _spans(exporter, "execute_tool tooled_guiagent")
    return dict(task.attributes or {})


async def test_finished_task_reports_actions_and_screenshots(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    gui_agent = make_tooled_gui_agent(
        ToolCall("click", {"start_box": [10, 20]}),
        ToolCall("finished", {"content": "Invoice filled"}),
    )

    _, sent = await _run(tracer, gui_agent, make_robot())

    assert sent == 1
    task = _task_attributes(exporter)
    assert task["gui.task.name"] == "Fill the invoice"
    assert task["gui.task.process_model"] == "invoice-process"
    assert task["gui.task.ui_log_count"] == 2
    assert task["gui.task.has_errored_activity"] is True
    assert task["gui.task.outcome"] == "done"
    assert task["gui.task.iterations"] == 1

    [action] = _spans(exporter, "gui.action")
    assert action.attributes == {
        "gui.action.iteration": 1,
        "gui.action.type": "left_single",
        "gui.action.success": True,
    }
    # One before the loop, one after the click.
    screenshots = _spans(exporter, "gui.screenshot")
    assert len(screenshots) == 2
    assert screenshots[0].attributes is not None
    assert screenshots[0].attributes["gui.screenshot.width"] == 64
    assert screenshots[0].attributes["gui.screenshot.height"] == 48


async def test_failed_action_is_recorded_without_its_inputs(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    gui_agent = make_tooled_gui_agent(
        ToolCall("type_text", {"content": TYPED_SECRET}), "Gave up."
    )

    await _run(tracer, gui_agent, make_robot(action_success=False))

    [action] = _spans(exporter, "gui.action")
    assert action.attributes is not None
    assert action.attributes["gui.action.success"] is False
    assert action.status.status_code.name == "ERROR"
    [event] = action.events
    assert event.name == "exception"
    assert TYPED_SECRET not in str(event.attributes)
    # Strands hands the failure back to the model, which may still go on.
    task = _task_attributes(exporter)
    assert task["gui.task.outcome"] == "model_stopped"
    assert task["gui.task.iterations"] == 1


async def test_unexpected_error_is_recorded_on_the_task_span(
    tracer: Tracer, exporter: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    gui_agent = make_tooled_gui_agent("unused")

    async def _broken(*_: Any, **__: Any) -> Any:
        raise ConnectionError("model endpoint unreachable")

    monkeypatch.setattr(tooled_module.StrandsAgent, "invoke_async", _broken)

    (result, _), _ = await _run(tracer, gui_agent, make_robot())

    assert result == "model endpoint unreachable"
    [task] = _spans(exporter, "execute_tool tooled_guiagent")
    assert (task.attributes or {})["gui.task.outcome"] == "error"
    assert task.status.status_code.name == "ERROR"
    assert [event.name for event in task.events] == ["exception"]
