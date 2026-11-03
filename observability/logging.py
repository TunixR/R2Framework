"""Structured JSON logging with trace correlation and secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
import warnings
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk._logs import LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

from observability.config import DEFAULT_SERVICE_NAME, ObservabilitySettings
from observability.correlation import get_request_id
from observability.events import EVENT_FIELDS_ATTR
from observability.tracing import build_resource

if TYPE_CHECKING:
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import LogRecordExporter
    from opentelemetry.util.types import Attributes

# Marks handlers installed by ``configure_logging`` so reconfiguring replaces
# them without touching handlers owned by anyone else.
_MANAGED_HANDLER_FLAG = "_observability_managed"
_REDACTED = "[REDACTED]"

_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|secret|password|passwd|token|authorization|robot[_-]?key)"
    r"\b(\s*[:=]\s*)(\S+)"
)
_TOKEN_PATTERN = re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]{8,})")


def redact(value: str) -> str:
    """Mask bearer/OpenAI-style tokens and secret assignments."""
    tokenless = _TOKEN_PATTERN.sub(_REDACTED, value)
    return _SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}", tokenless
    )


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - logging must never raise
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        span_context = trace.get_current_span().get_span_context()
        record.trace_id = (
            format(span_context.trace_id, "032x") if span_context.is_valid else None
        )
        record.span_id = (
            format(span_context.span_id, "016x") if span_context.is_valid else None
        )
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str = DEFAULT_SERVICE_NAME) -> None:
        super().__init__()
        self.service_name = service_name

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
        event_fields: tuple[str, ...] = getattr(record, EVENT_FIELDS_ATTR, ())
        for key in ("trace_id", "span_id", "request_id", *event_fields):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class RedactingLoggingHandler(LoggingHandler):
    """OTel log handler that redacts exception fields before they are exported.

    The SDK handler reads ``record.exc_info`` directly, so the logging
    ``RedactionFilter`` (which only rewrites the rendered message) is not
    enough: secrets inside an exception message or traceback would still reach
    SigNoz.
    """

    @staticmethod
    def _get_attributes(record: logging.LogRecord) -> Attributes:
        attributes = LoggingHandler._get_attributes(record) or {}
        return {
            key: redact(value) if isinstance(value, str) else value
            for key, value in attributes.items()
            if key != EVENT_FIELDS_ATTR
        }


class _ExcludeExporterLogs(logging.Filter):
    """Prevent exporter failures from re-entering the OTLP handler."""

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
        text_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )

    _install(root, logging.StreamHandler(stream=sys.stdout), formatter=text_formatter)

    if settings.log_file:
        file_handler = RotatingFileHandler(
            settings.log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
        )
        _install(root, file_handler, formatter=text_formatter)

    if logger_provider is not None:
        with warnings.catch_warnings():
            # The SDK handler is deprecated in favour of the logging
            # instrumentation package, which is not installed.
            warnings.simplefilter("ignore", DeprecationWarning)
            otel_handler = RedactingLoggingHandler(
                level=logging.NOTSET, logger_provider=logger_provider
            )
        _install(root, otel_handler, _ExcludeExporterLogs())

    # uvicorn installs its own handlers; fold them into the root JSON stream.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    logging.getLogger("strands").setLevel(logging.INFO)
