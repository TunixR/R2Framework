from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from observability import Observability, configure_observability
from observability.config import ObservabilitySettings
from observability.exceptions import record_exception

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class Payload(BaseModel):
    count: int


@dataclass
class Harness:
    client: TestClient
    exported: InMemorySpanExporter
    logs: InMemoryLogRecordExporter
    provider: TracerProvider
    handle: Observability


def _build(register: Callable[[FastAPI], None]) -> Harness:
    settings = ObservabilitySettings(log_format="console", log_level="WARNING")
    app = FastAPI()
    register(app)
    exported = InMemorySpanExporter()
    log_exporter = InMemoryLogRecordExporter()
    handle = configure_observability(
        app,
        settings=settings,
        span_exporter=exported,
        log_exporter=log_exporter,
        set_global=False,
    )
    assert handle.tracer_provider is not None
    return Harness(
        client=TestClient(app),
        exported=exported,
        logs=log_exporter,
        provider=handle.tracer_provider,
        handle=handle,
    )


@pytest.fixture()
def boom_app() -> Iterator[Harness]:
    def register(app: FastAPI) -> None:
        @app.get("/boom")
        async def boom() -> None:
            raise RuntimeError("db password=hunter2 sk-abcdef123456")

    harness = _build(register)
    try:
        yield harness
    finally:
        harness.handle.shutdown()


def test_unhandled_error_is_generic_and_recorded(boom_app: Harness) -> None:
    response = boom_app.client.get("/boom")
    boom_app.provider.force_flush()
    assert boom_app.handle.logger_provider is not None
    boom_app.handle.logger_provider.force_flush()
    spans = boom_app.exported.get_finished_spans()
    logs = boom_app.logs.get_finished_logs()

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "hunter2" not in response.text
    assert "abcdef123456" not in response.text
    assert response.json()["request_id"]
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
    exception_event = next(
        event for event in spans[0].events if event.name == "exception"
    )
    assert exception_event.attributes is not None
    message = exception_event.attributes["exception.message"]
    stacktrace = exception_event.attributes["exception.stacktrace"]
    assert isinstance(message, str)
    assert isinstance(stacktrace, str)
    assert "hunter2" not in message
    assert "abcdef123456" not in message
    assert "hunter2" not in stacktrace
    assert "abcdef123456" not in stacktrace
    assert "[REDACTED]" in message

    error_logs = [
        record
        for record in logs
        if "unhandled_exception" in str(record.log_record.body)
    ]
    assert error_logs
    for record in error_logs:
        attributes = record.log_record.attributes or {}
        assert "hunter2" not in str(attributes)
        assert "abcdef123456" not in str(attributes)


def test_record_exception_sanitizes_message_override() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("tests")

    try:
        with tracer.start_as_current_span("recovery.turn") as span:
            try:
                raise ValueError("raw value=super-secret")
            except ValueError as exc:
                record_exception(
                    span, exc, message="Invalid recovery payload: fields=['task_name']"
                )
    finally:
        provider.force_flush()
        provider.shutdown()

    span = exporter.get_finished_spans()[0]
    assert span.status.status_code.name == "ERROR"
    event = next(event for event in span.events if event.name == "exception")
    assert event.attributes is not None
    assert (
        event.attributes["exception.message"]
        == "Invalid recovery payload: fields=['task_name']"
    )
    assert "super-secret" not in str(event.attributes["exception.stacktrace"])


def test_server_side_http_exception_is_recorded() -> None:
    def register(app: FastAPI) -> None:
        @app.get("/unavailable")
        async def unavailable() -> None:
            raise HTTPException(status_code=503, detail="nope")

    harness = _build(register)
    try:
        response = harness.client.get("/unavailable")
        harness.provider.force_flush()
        spans = harness.exported.get_finished_spans()
    finally:
        harness.handle.shutdown()

    assert response.status_code == 503
    assert response.json()["detail"] == "nope"
    assert spans[0].status.status_code.name == "ERROR"


def test_client_error_is_not_marked_as_span_error() -> None:
    def register(app: FastAPI) -> None:
        @app.get("/missing")
        async def missing() -> None:
            raise HTTPException(status_code=404, detail="missing")

    harness = _build(register)
    try:
        response = harness.client.get("/missing")
        harness.provider.force_flush()
        spans = harness.exported.get_finished_spans()
    finally:
        harness.handle.shutdown()

    assert response.status_code == 404
    assert spans[0].status.status_code.name == "UNSET"


def test_validation_error_hides_input_values() -> None:
    def register(app: FastAPI) -> None:
        @app.post("/items")
        async def create(payload: Payload) -> dict[str, int]:
            return {"count": payload.count}

    harness = _build(register)
    try:
        response = harness.client.post("/items", json={"count": "super-secret-value"})
    finally:
        harness.handle.shutdown()

    assert response.status_code == 422
    assert "super-secret-value" not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "count"]
