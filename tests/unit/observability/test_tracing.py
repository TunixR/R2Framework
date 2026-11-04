import re

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability.config import ObservabilitySettings
from observability.tracing import (
    EXCLUDED_URLS,
    build_resource,
    create_tracer_provider,
)


def test_resource_uses_settings() -> None:
    settings = ObservabilitySettings.from_settings(
        service_name="svc", environment="test"
    )
    resource = build_resource(settings)

    assert resource.attributes["service.name"] == "svc"
    assert resource.attributes["deployment.environment"] == "test"
    assert resource.attributes["service.namespace"] == "r2framework"


def test_provider_exports_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = create_tracer_provider(
        ObservabilitySettings.from_settings(), exporter=exporter
    )
    tracer = provider.get_tracer(__name__)

    with tracer.start_as_current_span("unit"):
        pass
    provider.force_flush()

    assert [span.name for span in exporter.get_finished_spans()] == ["unit"]


def test_health_url_is_excluded() -> None:
    pattern = re.compile("|".join(EXCLUDED_URLS.split(",")))

    assert pattern.search("http://testserver/health")
    assert not pattern.search("http://testserver/agents/")
