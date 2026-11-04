import logging
from collections.abc import Iterator

import pytest
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability.config import ObservabilitySettings
from observability.events import EVENT_FIELDS_ATTR, log_event
from observability.logging import configure_logging, create_logger_provider
from observability.redaction import (
    RedactingLogRecordProcessor,
    RedactingSpanProcessor,
    RedactionFilter,
    redact,
)


@pytest.fixture
def otel_logs() -> Iterator[InMemoryLogRecordExporter]:
    """Route root logging through the real OTel pipeline into memory."""
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(RedactingLogRecordProcessor())
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    configure_logging(ObservabilitySettings(log_format="console"), provider)
    try:
        yield exporter
    finally:
        configure_logging(ObservabilitySettings(log_format="console"))
        provider.shutdown()


def test_redaction_masks_assignments_and_tokens() -> None:
    assert "hunter2" not in redact("password=hunter2")
    assert "abcdef123456" not in redact("key sk-abcdef123456 leaked")
    assert "abcdef123456" not in redact("Authorization: Bearer abcdef123456")
    assert "supersecret" not in redact("robot_key: supersecret")


def test_filter_redacts_the_record() -> None:
    record = logging.LogRecord(
        "tests", logging.INFO, __file__, 1, "api_key=super-secret", (), None
    )
    assert RedactionFilter().filter(record) is True
    assert "super-secret" not in record.getMessage()


def test_events_are_exported_with_event_name(
    otel_logs: InMemoryLogRecordExporter,
) -> None:
    log_event(
        logging.getLogger("tests.redaction"),
        "recovery.turn_failed",
        {"recovery.id": "rid-1", "recovery.task_name": "password=hunter2"},
        logging.WARNING,
    )

    [exported] = otel_logs.get_finished_logs()
    record = exported.log_record
    attributes = dict(record.attributes or {})
    assert record.event_name == "recovery.turn_failed"
    assert attributes["recovery.id"] == "rid-1"
    assert "hunter2" not in str(attributes["recovery.task_name"])
    assert "hunter2" not in str(record.body)
    for local_only in (EVENT_FIELDS_ATTR, "trace_id", "span_id", "otel.event.name"):
        assert local_only not in attributes


def test_exception_attributes_are_redacted(
    otel_logs: InMemoryLogRecordExporter,
) -> None:
    try:
        raise RuntimeError("api_key=sk-abcdef123456 password=hunter2")
    except RuntimeError:
        logging.getLogger("tests.redaction").exception("failed")

    [exported] = otel_logs.get_finished_logs()
    attributes = dict(exported.log_record.attributes or {})
    for key in ("exception.message", "exception.stacktrace"):
        assert "abcdef123456" not in str(attributes[key])
        assert "hunter2" not in str(attributes[key])


def test_logger_provider_registers_redaction_before_export() -> None:
    exporter = InMemoryLogRecordExporter()
    provider = create_logger_provider(
        ObservabilitySettings(), exporter, set_global=False
    )
    configure_logging(ObservabilitySettings(log_format="console"), provider)
    try:
        logging.getLogger("tests.redaction").warning("token=abc12345678")
        provider.force_flush()
    finally:
        configure_logging(ObservabilitySettings(log_format="console"))
        provider.shutdown()

    [exported] = exporter.get_finished_logs()
    assert "abc12345678" not in str(exported.log_record.body)


def test_span_processor_forwards_spans_to_its_delegate() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor(SimpleSpanProcessor(exporter)))

    with provider.get_tracer("tests").start_as_current_span("unit"):
        pass
    provider.shutdown()

    assert [span.name for span in exporter.get_finished_spans()] == ["unit"]


def test_logger_provider_mirrors_event_name_as_attribute() -> None:
    exporter = InMemoryLogRecordExporter()
    provider = create_logger_provider(
        ObservabilitySettings(), exporter, set_global=False
    )
    configure_logging(ObservabilitySettings(log_format="console"), provider)
    try:
        log_event(
            logging.getLogger("tests.redaction"),
            "recovery.auth_failed",
            None,
            logging.WARNING,
        )
        provider.force_flush()
    finally:
        configure_logging(ObservabilitySettings(log_format="console"))
        provider.shutdown()

    [exported] = exporter.get_finished_logs()
    assert exported.log_record.event_name == "recovery.auth_failed"
    assert dict(exported.log_record.attributes or {})["event.name"] == (
        "recovery.auth_failed"
    )
