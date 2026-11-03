"""Observability wiring: traces, logs, correlation, and exception recording."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from observability.config import ObservabilitySettings
from observability.correlation import RequestContextMiddleware
from observability.exceptions import (
    UnhandledExceptionMiddleware,
    register_exception_handlers,
)
from observability.logging import configure_logging, create_logger_provider
from observability.tracing import EXCLUDED_URLS, create_tracer_provider

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import LogRecordExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter


@dataclass(slots=True)
class Observability:
    settings: ObservabilitySettings
    tracer_provider: TracerProvider | None = None
    logger_provider: LoggerProvider | None = None

    def shutdown(self) -> None:
        if self.tracer_provider is not None:
            self.tracer_provider.force_flush()
            self.tracer_provider.shutdown()
        if self.logger_provider is not None:
            self.logger_provider.force_flush()
            self.logger_provider.shutdown()


_current: Observability | None = None


def configure_observability(
    app: FastAPI,
    *,
    settings: ObservabilitySettings | None = None,
    span_exporter: SpanExporter | None = None,
    log_exporter: LogRecordExporter | None = None,
    set_global: bool = True,
) -> Observability:
    """Configure traces, logs, correlation, and exception handlers for an app."""
    global _current

    settings = settings or ObservabilitySettings.from_env()
    tracer_provider: TracerProvider | None = None
    logger_provider: LoggerProvider | None = None

    if settings.enabled:
        logger_provider = create_logger_provider(
            settings, log_exporter, set_global=set_global
        )
        tracer_provider = create_tracer_provider(settings, span_exporter)
        if set_global:
            trace.set_tracer_provider(tracer_provider)

    configure_logging(settings, logger_provider)

    # Order matters: RequestContextMiddleware is added last so it wraps the
    # exception middleware and can stamp X-Request-ID on error responses.
    app.add_middleware(UnhandledExceptionMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        excluded_urls=EXCLUDED_URLS,
        exclude_spans=["receive", "send"],
    )

    _current = Observability(
        settings=settings,
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
    )
    return _current


def setup_strands_telemetry() -> None:
    """Share the app tracer provider with Strands so spans stay in one trace."""
    observability = _current
    if observability is None or observability.tracer_provider is None:
        return

    from strands.telemetry import StrandsTelemetry

    _ = StrandsTelemetry(tracer_provider=observability.tracer_provider).setup_meter(
        enable_otlp_exporter=True
    )


def shutdown_observability() -> None:
    global _current
    if _current is not None:
        _current.shutdown()
        _current = None
