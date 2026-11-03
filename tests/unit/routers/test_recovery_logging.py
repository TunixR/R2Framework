from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlmodel import Session

import routers.recovery as recovery_module
from database.agents.models import Agent
from observability.attributes import OTEL_EVENT_NAME, RECOVERY_PAYLOAD_INVALID_FIELDS

PASSWORD = "hunter2-sk-abcdef123456"


@pytest.fixture
def robot_key_raw(make_robot_key) -> str:  # pyright: ignore[reportMissingParameterType]
    key_raw = "test-robot-key-logging-0001"
    _ = make_robot_key(name="Logging", enabled=True, key_raw=key_raw)
    return key_raw


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def recovery_tracer(
    span_exporter: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TracerProvider]:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    monkeypatch.setattr(
        recovery_module, "tracer", provider.get_tracer("tests.recovery")
    )
    try:
        yield provider
    finally:
        provider.shutdown()


def _extra(record: logging.LogRecord, name: str) -> Any:
    return vars(record)[name]


def _records_by_event(caplog: pytest.LogCaptureFixture) -> dict[str, logging.LogRecord]:
    return {
        _extra(record, OTEL_EVENT_NAME): record
        for record in caplog.records
        if str(vars(record).get(OTEL_EVENT_NAME, "")).startswith("recovery.")
    }


def _assert_no_secret(caplog: pytest.LogCaptureFixture) -> None:
    for record in caplog.records:
        assert PASSWORD not in record.getMessage()
        assert PASSWORD not in str(vars(record).get(RECOVERY_PAYLOAD_INVALID_FIELDS))


def test_recovery_turn_is_traced_without_lifecycle_logs(
    session: Session,  # pyright: ignore[reportUnusedParameter]
    client: TestClient,
    valid_recovery_payload: dict[str, Any],
    gateway_agent: Agent,
    robot_key_raw: str,
    recovery_tracer: TracerProvider,
    span_exporter: InMemorySpanExporter,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_call(
        _self: Agent,
        invocation_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {"success": True, "continue_from_step": 2}

    monkeypatch.setattr(Agent, "__call__", _fake_call)
    caplog.set_level(logging.INFO)

    headers = {"X-ROBOT-KEY": robot_key_raw}
    with client.websocket_connect(
        "/recovery/robot_exception/ws", headers=headers
    ) as ws:
        ws.send_json(valid_recovery_payload)
        message = ws.receive_json()

    assert message["type"] == "done"
    recovery_id = message["id"]
    # Successful turns are described by spans; only problems are logged.
    assert _records_by_event(caplog) == {}
    for record in caplog.records:
        assert robot_key_raw not in record.getMessage()

    recovery_tracer.force_flush()
    spans = {span.name: span for span in span_exporter.get_finished_spans()}
    turn = spans["recovery.turn"]
    assert turn.attributes is not None
    assert turn.attributes["recovery.id"] == recovery_id
    assert turn.attributes["recovery.success"] is True
    assert turn.attributes["recovery.outcome"] == "success"
    assert turn.attributes["agent.id"] == str(gateway_agent.id)
    assert turn.attributes["robot_key.id"]
    assert turn.attributes["recovery.payload.ui_log_count"] == 1
    assert turn.attributes["recovery.payload.size"] > 0  # pyright: ignore[reportOperatorIssue]

    persist = spans["recovery.persist"]
    assert persist.parent is not None
    assert turn.context is not None
    assert persist.parent.span_id == turn.context.span_id


def test_invalid_payload_logs_field_paths_not_values(
    session: Session,  # pyright: ignore[reportUnusedParameter]
    client: TestClient,
    gateway_agent: Agent,  # pyright: ignore[reportUnusedParameter]
    robot_key_raw: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    secret_value = "do-not-log-this-task"
    payload = {"task_name": secret_value, "ui_log": [{"case_id": "1"}]}

    headers = {"X-ROBOT-KEY": robot_key_raw}
    with client.websocket_connect(
        "/recovery/robot_exception/ws", headers=headers
    ) as ws:
        ws.send_json(payload)
        message = ws.receive_json()

    assert message["code"] == "INVALID_RECOVERY_PAYLOAD"
    events = _records_by_event(caplog)
    invalid = events["recovery.payload_invalid"]
    field_paths = _extra(invalid, RECOVERY_PAYLOAD_INVALID_FIELDS)
    assert field_paths
    assert all(not path.startswith("task_name.") for path in field_paths)
    for record in caplog.records:
        assert secret_value not in record.getMessage()
        assert secret_value not in str(
            vars(record).get(RECOVERY_PAYLOAD_INVALID_FIELDS)
        )


def test_turn_failure_logs_and_records_redacted_exception(
    session: Session,  # pyright: ignore[reportUnusedParameter]
    client: TestClient,
    valid_recovery_payload: dict[str, Any],
    gateway_agent: Agent,  # pyright: ignore[reportUnusedParameter]
    robot_key_raw: str,
    recovery_tracer: TracerProvider,
    span_exporter: InMemorySpanExporter,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _failing_call(
        _self: Agent,
        invocation_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise RuntimeError(f"model call failed password={PASSWORD}")

    monkeypatch.setattr(Agent, "__call__", _failing_call)
    caplog.set_level(logging.INFO)

    headers = {"X-ROBOT-KEY": robot_key_raw}
    with client.websocket_connect(
        "/recovery/robot_exception/ws", headers=headers
    ) as ws:
        ws.send_json(valid_recovery_payload)
        message = ws.receive_json()

    assert message == {"type": "error", "content": "Internal server error"}
    events = _records_by_event(caplog)
    assert _extra(events["recovery.turn_failed"], "recovery.id")
    assert _extra(events["recovery.turn_failed"], "error.type") == "RuntimeError"
    _assert_no_secret(caplog)

    recovery_tracer.force_flush()
    spans = span_exporter.get_finished_spans()
    turn = next(span for span in spans if span.name == "recovery.turn")
    assert turn.status.status_code.name == "ERROR"
    assert turn.attributes is not None
    assert turn.attributes["recovery.outcome"] == "internal_error"
    exception_event = next(event for event in turn.events if event.name == "exception")
    assert exception_event.attributes is not None
    message_attr = exception_event.attributes["exception.message"]
    stacktrace = exception_event.attributes["exception.stacktrace"]
    assert isinstance(message_attr, str)
    assert isinstance(stacktrace, str)
    assert PASSWORD not in message_attr
    assert PASSWORD not in stacktrace
    assert "[REDACTED]" in message_attr
