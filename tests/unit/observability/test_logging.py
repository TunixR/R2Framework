import json
import logging
import sys

from observability.correlation import _request_id
from observability.events import EVENT_FIELDS_ATTR
from observability.logging import (
    JsonFormatter,
    RedactingLoggingHandler,
    RedactionFilter,
    TraceContextFilter,
    redact,
)


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
    record.request_id = "req-1"

    payload = json.loads(JsonFormatter(service_name="svc").format(record))

    assert payload == {
        "timestamp": payload["timestamp"],
        "level": "INFO",
        "logger": "tests",
        "message": "hello",
        "service": "svc",
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "request_id": "req-1",
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
    record.event = "recovery.turn_finished"
    record.recovery_id = "rid-1"
    record.success = True
    record.duration_ms = 12.5
    record.ignored_field = "not declared as an event field"
    setattr(
        record,
        EVENT_FIELDS_ATTR,
        ("event", "recovery_id", "success", "duration_ms"),
    )

    payload = json.loads(JsonFormatter(service_name="svc").format(record))

    assert payload["event"] == "recovery.turn_finished"
    assert payload["recovery_id"] == "rid-1"
    assert payload["success"] is True
    assert payload["duration_ms"] == 12.5
    assert "ignored_field" not in payload


def test_json_formatter_redacts_exception_and_extras() -> None:
    try:
        raise RuntimeError("db password=hunter2 sk-abcdef123456")
    except RuntimeError:
        record = _record("failed")
        record.exc_info = sys.exc_info()

    record.task_name = "password=super-secret"
    setattr(record, EVENT_FIELDS_ATTR, ("task_name",))

    payload = json.loads(JsonFormatter().format(record))

    assert "hunter2" not in payload["message"]
    assert "hunter2" not in payload["exception"]
    assert "abcdef123456" not in payload["exception"]
    assert "super-secret" not in payload["task_name"]
    assert "[REDACTED]" in payload["exception"]


def test_otel_handler_redacts_exception_attributes() -> None:
    try:
        raise RuntimeError("api_key=sk-abcdef123456 password=hunter2")
    except RuntimeError:
        record = _record("failed")
        record.exc_info = sys.exc_info()

    setattr(record, EVENT_FIELDS_ATTR, ("event",))

    attributes = RedactingLoggingHandler._get_attributes(record)

    assert attributes is not None
    assert EVENT_FIELDS_ATTR not in attributes
    message = attributes["exception.message"]
    stacktrace = attributes["exception.stacktrace"]
    assert isinstance(message, str)
    assert isinstance(stacktrace, str)
    assert "abcdef123456" not in message
    assert "hunter2" not in message
    assert "abcdef123456" not in stacktrace
    assert "hunter2" not in stacktrace


def test_redaction_masks_assignments_and_tokens() -> None:
    assert "hunter2" not in redact("password=hunter2")
    assert "abcdef123456" not in redact("key sk-abcdef123456 leaked")
    assert "abcdef123456" not in redact("Authorization: Bearer abcdef123456")
    assert "supersecret" not in redact("robot_key: supersecret")


def test_filter_redacts_the_record() -> None:
    record = _record("api_key=super-secret")
    assert RedactionFilter().filter(record) is True
    assert "super-secret" not in record.getMessage()


def test_request_id_context_is_read() -> None:
    token = _request_id.set("ctx-1")
    try:
        record = _record("hi")
        assert TraceContextFilter().filter(record) is True
        assert vars(record)["request_id"] == "ctx-1"
        assert vars(record)["trace_id"] is None
    finally:
        _request_id.reset(token)
