from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability import Observability, configure_observability
from observability.config import ObservabilitySettings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from opentelemetry.sdk.trace import TracerProvider


@dataclass
class Harness:
    client: TestClient
    exported: InMemorySpanExporter
    provider: TracerProvider
    handle: Observability


def _build(register: Callable[[FastAPI], None]) -> Harness:
    app = FastAPI()
    register(app)
    exported = InMemorySpanExporter()
    handle = configure_observability(
        app,
        settings=ObservabilitySettings(log_format="console", log_level="WARNING"),
        span_exporter=exported,
        log_exporter=InMemoryLogRecordExporter(),
        set_global=False,
    )
    assert handle.tracer_provider is not None
    return Harness(
        client=TestClient(app),
        exported=exported,
        provider=handle.tracer_provider,
        handle=handle,
    )


@pytest.fixture()
def routes_app() -> Iterator[Harness]:
    def register(app: FastAPI) -> None:
        @app.get("/health", include_in_schema=False)
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/items/{item_id}")
        async def item(item_id: str) -> dict[str, str]:
            return {"id": item_id}

    harness = _build(register)
    try:
        yield harness
    finally:
        harness.handle.shutdown()


def test_health_is_not_traced(routes_app: Harness) -> None:
    response = routes_app.client.get("/health")
    routes_app.provider.force_flush()

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert routes_app.exported.get_finished_spans() == ()


def test_span_name_uses_route_template(routes_app: Harness) -> None:
    routes_app.client.get("/items/123")
    routes_app.provider.force_flush()

    names = [span.name for span in routes_app.exported.get_finished_spans()]
    assert names == ["GET /items/{item_id}"]


def test_request_id_is_recorded_on_span(routes_app: Harness) -> None:
    response = routes_app.client.get("/items/123", headers={"X-Request-ID": "trace-me"})
    routes_app.provider.force_flush()

    span = routes_app.exported.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["request.id"] == "trace-me"
    assert response.headers["x-request-id"] == "trace-me"
