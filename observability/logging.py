"""Structured JSON logging with trace correlation and secret redaction."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, override

from opentelemetry import trace
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

from observability.attributes import OTEL_EVENT_NAME, REQUEST_ID
from observability.config import ObservabilitySettings
from observability.correlation import get_request_id
from observability.events import EVENT_FIELDS_ATTR
from observability.redaction import (
    RedactingLogRecordProcessor,
    RedactionFilter,
    redact,
)
from observability.tracing import build_resource

if TYPE_CHECKING:
    from types import TracebackType

    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import LogRecordExporter

    type ExcInfo = (
        tuple[type[BaseException], BaseException, TracebackType | None]
        | tuple[None, None, None]
    )

# Marks handlers installed by ``configure_logging`` so reconfiguring replaces
# them without touching handlers owned by anyone else.
_MANAGED_HANDLER_FLAG = "_observability_managed"


class TraceContextFilter(logging.Filter):
    """Stamp trace, span and request ids on records for the stdout formatter."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        span_context = trace.get_current_span().get_span_context()
        record.trace_id = (
            format(span_context.trace_id, "032x") if span_context.is_valid else None
        )
        record.span_id = (
            format(span_context.span_id, "016x") if span_context.is_valid else None
        )
        setattr(record, REQUEST_ID, get_request_id())
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    @override
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "service": self.service_name,
        }
        event_name = getattr(record, OTEL_EVENT_NAME, None)
        if event_name is not None:
            payload["event"] = event_name
        event_fields: tuple[str, ...] = getattr(record, EVENT_FIELDS_ATTR, ())
        for key in ("trace_id", "span_id", REQUEST_ID, *event_fields):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class RedactingFormatter(logging.Formatter):
    """Plain-text formatter that also redacts exception tracebacks.

    ``RedactionFilter`` only rewrites the message; the traceback is rendered
    later by the formatter, from ``exc_info``.
    """

    @override
    def formatException(self, ei: ExcInfo) -> str:
        return redact(super().formatException(ei))

    @override
    def formatStack(self, stack_info: str) -> str:
        return redact(super().formatStack(stack_info))


class _ExcludeExporterLogs(logging.Filter):
    """Prevent exporter failures from re-entering the OTLP handler."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("opentelemetry.exporter")


def create_logger_provider(
    settings: ObservabilitySettings,
    exporter: LogRecordExporter | None = None,
    *,
    set_global: bool = True,
) -> LoggerProvider:
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider as SdkLoggerProvider

    if exporter is None:
        exporter = OTLPLogExporter(endpoint=settings.otlp_endpoint("logs"))

    provider = SdkLoggerProvider(resource=build_resource(settings))
    # Processors run in order on the same record: redact before exporting.
    provider.add_log_record_processor(RedactingLogRecordProcessor())
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    if set_global:
        set_logger_provider(provider)
    return provider


def _remove_managed_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _MANAGED_HANDLER_FLAG, False):
            logger.removeHandler(handler)


def _install(
    logger: logging.Logger,
    handler: logging.Handler,
    *filters: logging.Filter,
    formatter: logging.Formatter | None = None,
) -> None:
    setattr(handler, _MANAGED_HANDLER_FLAG, True)
    handler.addFilter(TraceContextFilter())
    handler.addFilter(RedactionFilter())
    for extra_filter in filters:
        handler.addFilter(extra_filter)
    if formatter is not None:
        handler.setFormatter(formatter)
    logger.addHandler(handler)


def configure_logging(
    settings: ObservabilitySettings, logger_provider: LoggerProvider | None = None
) -> None:
    """Configure root logging once, replacing only handlers we own."""
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    _remove_managed_handlers(root)

    text_formatter: logging.Formatter
    if settings.log_format == "json":
        text_formatter = JsonFormatter(settings.service_name)
    else:
        text_formatter = RedactingFormatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )

    _install(root, logging.StreamHandler(stream=sys.stdout), formatter=text_formatter)

    if settings.log_file:
        file_handler = RotatingFileHandler(
            settings.log_file,
            maxBytes=settings.log_file_max_bytes,
            backupCount=settings.log_file_backup_count,
            encoding="utf-8",
        )
        _install(root, file_handler, formatter=text_formatter)

    if logger_provider is not None:
        otel_handler = LoggingHandler(
            level=logging.NOTSET, logger_provider=logger_provider
        )
        _install(root, otel_handler, _ExcludeExporterLogs())

    # uvicorn installs its own handlers; fold them into the root JSON stream.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    logging.getLogger("strands").setLevel(settings.strands_log_level)
