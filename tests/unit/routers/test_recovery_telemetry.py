import logging
from collections.abc import Iterator
from uuid import UUID

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer
from pydantic import BaseModel, ValidationError

from routers.recovery_telemetry import invalid_field_paths, recovery_turn

ROBOT_KEY_ID = UUID(int=7)


class _Payload(BaseModel):
    task_name: str


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def tracer(exporter: InMemorySpanExporter) -> Iterator[Tracer]:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield provider.get_tracer("tests.recovery")
    provider.shutdown()


def _turn_span(exporter: InMemorySpanExporter) -> ReadableSpan:
    return next(s for s in exporter.get_finished_spans() if s.name == "recovery.turn")


def _validation_failure() -> Exception:
    try:
        _Payload.model_validate({"task_name": 1})
    except ValidationError as exc:
        try:
            raise RuntimeError("invalid payload input=do-not-export") from exc
        except RuntimeError as wrapped:
            return wrapped
    raise AssertionError("expected a validation error")


def test_payload_is_described_by_shape_only(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    raw = '{"ui_log": [{"input": "secret"}], "errored_act": {"id": 1}}'

    with recovery_turn(tracer, ROBOT_KEY_ID) as turn:
        turn.payload_received(raw, {"ui_log": [{"input": "secret"}], "errored_act": {}})

    attributes = _turn_span(exporter).attributes or {}
    assert attributes["robot_key.id"] == str(ROBOT_KEY_ID)
    assert attributes["recovery.payload.size"] == len(raw)
    assert attributes["recovery.payload.ui_log_count"] == 1
    assert attributes["recovery.payload.has_errored_activity"] is False
    assert "secret" not in str(attributes)


def test_completed_turn_sets_outcome(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    with recovery_turn(tracer, ROBOT_KEY_ID) as turn:
        with turn.persisting():
            pass
        turn.persisted(UUID(int=1))
        turn.completed(False)

    spans = {span.name: span for span in exporter.get_finished_spans()}
    attributes = spans["recovery.turn"].attributes or {}
    assert attributes["recovery.id"] == str(UUID(int=1))
    assert attributes["recovery.success"] is False
    assert attributes["recovery.outcome"] == "completed_unsuccessful"
    assert spans["recovery.turn"].status.status_code.name == "UNSET"
    assert "recovery.persist" in spans


def test_no_gateway_agent_marks_the_turn_as_error(
    tracer: Tracer, exporter: InMemorySpanExporter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR)

    with recovery_turn(tracer, ROBOT_KEY_ID) as turn:
        turn.no_gateway_agent()

    span = _turn_span(exporter)
    assert span.status.status_code.name == "ERROR"
    assert (span.attributes or {})["recovery.outcome"] == "no_gateway_agent"
    assert [vars(r)["otel.event.name"] for r in caplog.records] == [
        "recovery.no_gateway_agent"
    ]


def test_invalid_payload_exports_field_paths_only(
    tracer: Tracer, exporter: InMemorySpanExporter
) -> None:
    exc = _validation_failure()

    with recovery_turn(tracer, ROBOT_KEY_ID) as turn:
        turn.invalid_payload(exc)

    span = _turn_span(exporter)
    attributes = span.attributes or {}
    assert attributes["recovery.outcome"] == "invalid_payload"
    assert list(attributes["recovery.payload.invalid_fields"]) == ["task_name"]  # pyright: ignore[reportArgumentType]
    [event] = span.events
    assert "do-not-export" not in str(event.attributes)


def test_failed_turn_logs_the_recovery_id(
    tracer: Tracer, exporter: InMemorySpanExporter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR)

    with recovery_turn(tracer, ROBOT_KEY_ID) as turn:
        turn.persisted(UUID(int=2))
        turn.failed(RuntimeError("boom"))

    [record] = caplog.records
    assert vars(record)["recovery.id"] == str(UUID(int=2))
    assert vars(record)["error.type"] == "RuntimeError"
    assert (_turn_span(exporter).attributes or {})[
        "recovery.outcome"
    ] == "internal_error"


def test_invalid_field_paths_ignores_other_causes() -> None:
    assert invalid_field_paths(RuntimeError("no cause")) == []
