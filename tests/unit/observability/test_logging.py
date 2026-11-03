import json
import logging
import sys

from observability.attributes import OTEL_EVENT_NAME, REQUEST_ID
from observability.correlation import _request_id
from observability.events import EVENT_FIELDS_ATTR
from observability.logging import JsonFormatter, TraceContextFilter


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="tests",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_json_formatter_includes_context() -> None:
    record = _record("hello")
    record.trace_id = "a" * 32
    record.span_id = "b" * 16
    setattr(record, REQUEST_ID, "req-1")

    payload = json.loads(JsonFormatter(service_name="svc").format(record))

    assert payload == {
        "timestamp": payload["timestamp"],
        "level": "INFO",
        "logger": "tests",
        "message": "hello",
        "service": "svc",
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "request.id": "req-1",
    }


def test_json_formatter_includes_exception() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = _record("failed")
        record.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(record))

    assert "RuntimeError: boom" in payload["exception"]


def test_json_formatter_includes_structured_extras() -> None:
    record = _record("hello")
    setattr(record, OTEL_EVENT_NAME, "recovery.turn_failed")
    setattr(record, "recovery.id", "rid-1")
    setattr(record, "recovery.success", False)
    record.ignored_field = "not declared as an event field"
    setattr(record, EVENT_FIELDS_ATTR, ("recovery.id", "recovery.success"))

    payload = json.loads(JsonFormatter(service_name="svc").format(record))

    assert payload["event"] == "recovery.turn_failed"
    assert payload["recovery.id"] == "rid-1"
    assert payload["recovery.success"] is False
    assert "ignored_field" not in payload


def test_json_formatter_redacts_exception_and_extras() -> None:
    try:
        raise RuntimeError("db password=hunter2 sk-abcdef123456")
    except RuntimeError:
        record = _record("failed")
        record.exc_info = sys.exc_info()

    setattr(record, "recovery.task_name", "password=super-secret")
    setattr(record, EVENT_FIELDS_ATTR, ("recovery.task_name",))

    payload = json.loads(JsonFormatter().format(record))

    assert "hunter2" not in payload["message"]
    assert "hunter2" not in payload["exception"]
    assert "abcdef123456" not in payload["exception"]
    assert "super-secret" not in payload["recovery.task_name"]
    assert "[REDACTED]" in payload["exception"]


def test_request_id_context_is_read() -> None:
    token = _request_id.set("ctx-1")
    try:
        record = _record("hi")
        assert TraceContextFilter().filter(record) is True
        assert vars(record)[REQUEST_ID] == "ctx-1"
        assert vars(record)["trace_id"] is None
    finally:
        _request_id.reset(token)
