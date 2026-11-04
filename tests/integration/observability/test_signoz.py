"""Happy paths of each observability feature, verified in a live SigNoz.

Each test drives the app, flushes the exporters, then reads back what SigNoz
stored. See ``conftest.py`` for the setup and cleanup.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from opentelemetry import trace
from sqlmodel import Session

from database.agents.gui_telemetry import GuiTaskTelemetry
from database.agents.models import Agent
from database.logging.models import RobotException
from tests.integration.observability.conftest import SECRET, ScriptedModel, Telemetry
from tests.integration.observability.signoz import Row


def _by_name(spans: list[Row]) -> dict[str, Row]:
    return {span["name"]: span for span in spans}


def _trace_spans(telemetry: Telemetry, trace_id: str, at_least: int) -> list[Row]:
    return telemetry.signoz.wait_for(
        lambda: telemetry.signoz.spans(f"trace_id = '{trace_id}'"), at_least=at_least
    )


def _request_trace_id(telemetry: Telemetry, request_id: str) -> str:
    [span] = telemetry.signoz.wait_for(
        lambda: telemetry.signoz.spans(
            f"attributes_string['request.id'] = '{request_id}'"
        )
    )
    return span["trace_id"]


def test_http_requests_are_traced_by_route_with_request_id(
    telemetry: Telemetry,
) -> None:
    response = telemetry.client.get("/items/42", headers={"X-Request-ID": "it-http-1"})
    telemetry.flush()

    assert response.headers["x-request-id"] == "it-http-1"
    [span] = telemetry.signoz.wait_for(
        lambda: telemetry.signoz.spans("attributes_string['request.id'] = 'it-http-1'")
    )
    assert span["name"] == "GET /items/{item_id}"
    assert span["kind_string"] == "Server"
    assert span["has_error"] is False


def test_events_are_logged_with_typed_attributes_in_the_request_trace(
    telemetry: Telemetry,
) -> None:
    telemetry.client.get("/events", headers={"X-Request-ID": "it-events-1"})
    telemetry.flush()

    trace_id = _request_trace_id(telemetry, "it-events-1")
    [log] = telemetry.signoz.wait_for(
        lambda: telemetry.signoz.logs(
            "attributes_string['event.name'] = 'integration.checked'"
        )
    )
    assert log["trace_id"] == trace_id
    assert log["severity_text"] == "WARN"
    assert log["attributes_string"]["request.id"] == "it-events-1"
    assert log["attributes_number"]["integration.count"] == 3
    assert log["attributes_bool"]["integration.passed"] is True
    # Redacted before export, in the attribute and in the rendered body.
    assert SECRET not in log["attributes_string"]["integration.note"]
    assert SECRET not in log["body"]
    # Local-only bookkeeping never reaches the backend.
    assert "event_fields" not in log["attributes_string"]


def test_client_errors_are_warn_events_and_not_span_errors(
    telemetry: Telemetry,
) -> None:
    response = telemetry.client.get(
        "/items/missing", headers={"X-Request-ID": "it-404-1"}
    )
    telemetry.flush()

    assert response.status_code == 404
    trace_id = _request_trace_id(telemetry, "it-404-1")
    [span] = _trace_spans(telemetry, trace_id, at_least=1)
    assert span["has_error"] is False
    [log] = telemetry.signoz.wait_for(
        lambda: telemetry.signoz.logs(f"trace_id = '{trace_id}'")
    )
    assert log["attributes_string"]["event.name"] == "http.client_error"
    assert log["attributes_number"]["http.response.status_code"] == 404


def test_unhandled_errors_are_recorded_once_and_redacted(
    telemetry: Telemetry,
) -> None:
    response = telemetry.client.get("/boom", headers={"X-Request-ID": "it-boom-1"})
    telemetry.flush()

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error",
        "request_id": "it-boom-1",
    }
    trace_id = _request_trace_id(telemetry, "it-boom-1")

    [span] = _trace_spans(telemetry, trace_id, at_least=1)
    assert span["has_error"] is True
    assert span["status_code_string"] == "Error"

    [error] = telemetry.signoz.wait_for(lambda: telemetry.signoz.errors(trace_id))
    assert error["exceptionType"] == "RuntimeError"
    assert SECRET not in error["exceptionMessage"]
    assert SECRET not in error["exceptionStacktrace"]

    [log] = telemetry.signoz.wait_for(
        lambda: telemetry.signoz.logs(f"trace_id = '{trace_id}'")
    )
    assert log["severity_text"] == "ERROR"
    assert log["attributes_string"]["event.name"] == "http.unhandled_exception"
    assert log["attributes_string"]["exception.type"] == "RuntimeError"
    assert SECRET not in log["attributes_string"]["exception.stacktrace"]


@pytest.mark.usefixtures("gateway_agent")
def test_recovery_turn_is_one_trace_joined_to_the_database(
    telemetry: Telemetry,
    session: Session,
    make_robot_key: Any,
    valid_recovery_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_raw = "integration-robot-key-0001"
    robot_key = make_robot_key(name="Integration", key_raw=key_raw)

    async def _gateway(
        _self: Agent, invocation_state: dict[str, Any] | None = None, **_: Any
    ) -> dict[str, Any]:
        # A real Strands agent with a scripted model: its spans must join the turn.
        from strands import Agent as StrandsAgent

        agent = StrandsAgent(
            model=ScriptedModel("Recovered."), name="gateway", callback_handler=None
        )
        await agent.invoke_async("Recover the robot")
        return {"success": True, "continue_from_step": 2}

    monkeypatch.setattr(Agent, "__call__", _gateway)

    with telemetry.client.websocket_connect(
        "/recovery/robot_exception/ws", headers={"X-ROBOT-KEY": key_raw}
    ) as ws:
        ws.send_json(valid_recovery_payload)
        message = ws.receive_json()
    telemetry.flush()

    assert message["type"] == "done"
    recovery_id = message["id"]

    [turn] = telemetry.signoz.wait_for(
        lambda: telemetry.signoz.spans(
            f"name = 'recovery.turn' AND attributes_string['recovery.id'] = '{recovery_id}'"
        )
    )
    spans = _trace_spans(telemetry, turn["trace_id"], at_least=4)
    by_name = _by_name(spans)

    # Turn attributes describe the payload by shape only.
    assert turn["attributes_string"]["robot_key.id"] == str(robot_key.id)
    assert turn["attributes_string"]["recovery.outcome"] == "success"
    assert turn["attributes_bool"]["recovery.success"] is True
    assert turn["attributes_number"]["recovery.payload.ui_log_count"] == 1

    # Nesting: websocket span -> recovery.turn -> persist and the Strands agent.
    websocket_span = next(s for s in spans if s["span_id"] == turn["parent_span_id"])
    assert "robot_exception/ws" in websocket_span["name"]
    assert by_name["recovery.persist"]["parent_span_id"] == turn["span_id"]
    agent_span = next(s for s in spans if s["name"].startswith("invoke_agent"))
    assert agent_span["parent_span_id"] == turn["span_id"]
    assert any(s["name"] == "chat" for s in spans)

    # Correlation: the span attribute is the primary key of the audit row.
    stored = session.get(RobotException, UUID(recovery_id))
    assert stored is not None
    assert stored.infered_success is True


def test_gui_task_records_actions_and_screenshots_as_child_spans(
    telemetry: Telemetry,
) -> None:
    tracer = trace.get_tracer("tests.integration.gui")
    with tracer.start_as_current_span("execute_tool gui_agent") as tool_span:
        task = GuiTaskTelemetry(
            task="Fill the invoice",
            model="invoice-process",
            ui_log=[{}],
            errored_act={},
        )
        with task.screenshot() as shot:
            shot.taken(b"jpeg-bytes", 1280, 720)
        with task.action(1, "click") as action:
            action.result(True)
        task.done(iterations=1)
    telemetry.flush()

    trace_id = format(tool_span.get_span_context().trace_id, "032x")
    spans = _by_name(_trace_spans(telemetry, trace_id, at_least=3))

    tool = spans["execute_tool gui_agent"]
    assert tool["attributes_string"]["gui.task.outcome"] == "done"
    assert tool["attributes_number"]["gui.task.iterations"] == 1
    for child in ("gui.screenshot", "gui.action"):
        assert spans[child]["parent_span_id"] == tool["span_id"]
    assert spans["gui.action"]["attributes_string"]["gui.action.type"] == "click"
    assert spans["gui.action"]["attributes_bool"]["gui.action.success"] is True
    assert spans["gui.screenshot"]["attributes_number"]["gui.screenshot.width"] == 1280
