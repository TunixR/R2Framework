"""Tracer provider setup and span naming conventions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from observability.config import ObservabilitySettings
from observability.redaction import RedactingSpanProcessor

if TYPE_CHECKING:
    from opentelemetry.sdk.trace.export import SpanExporter

# Matched against the full request URL by OpenTelemetryMiddleware.
EXCLUDED_URLS = (
    r"/health$,"
    r"/docs$,"
    r"/redoc$,"
    r"/openapi\.json$,"
    r"/scalar$,"
    r"/favicon\.ico$"
)


def build_resource(settings: ObservabilitySettings) -> Resource:
    return Resource.create(
        {
            "service.name": settings.service_name,
            "service.namespace": settings.service_namespace,
            "deployment.environment": settings.environment,
        }
    )


def create_tracer_provider(
    settings: ObservabilitySettings, exporter: SpanExporter | None = None
) -> TracerProvider:
    if exporter is None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint("traces"))

    provider = TracerProvider(
        resource=build_resource(settings),
        sampler=ParentBased(TraceIdRatioBased(settings.sample_ratio)),
    )
    # Every exported span goes through the redaction choke point.
    provider.add_span_processor(RedactingSpanProcessor(BatchSpanProcessor(exporter)))
    return provider
