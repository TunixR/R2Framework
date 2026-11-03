"""Single choke point for keeping secrets and personal data out of telemetry.

Every exported span and log record passes through a processor defined here,
so tightening the privacy policy means changing this module only.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, override

from opentelemetry.sdk._logs import LogRecordProcessor
from opentelemetry.sdk.trace import SpanProcessor

from observability.events import EVENT_FIELDS_ATTR

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.sdk._logs import ReadWriteLogRecord
    from opentelemetry.sdk.trace import ReadableSpan, Span

_REDACTED = "[REDACTED]"

# Best effort only: matches ``key=value`` / ``key: value`` and bearer or
# OpenAI-style tokens. Quoted keys (JSON, Python reprs) are not matched yet.
_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|secret|password|passwd|token|authorization|robot[_-]?key)"
    r"\b(\s*[:=]\s*)(\S+)"
)
_TOKEN_PATTERN = re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]{8,})")

# Record attributes that only make sense in the stdout formatter: the OTLP
# LogRecord already carries the trace and span ids natively.
_LOCAL_ONLY_ATTRIBUTES = frozenset({EVENT_FIELDS_ATTR, "trace_id", "span_id"})


def redact(value: str) -> str:
    """Mask bearer/OpenAI-style tokens and secret assignments."""
    tokenless = _TOKEN_PATTERN.sub(_REDACTED, value)
    return _SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}", tokenless
    )


class RedactionFilter(logging.Filter):
    """Redact the rendered message of every record a handler emits."""

    @override
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


class RedactingLogRecordProcessor(LogRecordProcessor):
    """Redact log bodies and string attributes before the exporting processor.

    Register it ahead of the batch processor: processors run in order on the
    same mutable record. The logging handler copies ``exc_info`` into
    ``exception.message``/``exception.stacktrace`` attributes itself, so the
    ``RedactionFilter`` on the message alone would not be enough.
    """

    @override
    def on_emit(self, log_record: ReadWriteLogRecord) -> None:
        record = log_record.log_record
        if isinstance(record.body, str):
            record.body = redact(record.body)
        attributes = record.attributes
        if attributes is None:
            return
        for key in list(attributes):
            value = attributes[key]
            if key in _LOCAL_ONLY_ATTRIBUTES or value is None:
                del attributes[key]  # pyright: ignore[reportIndexIssue] - BoundedAttributes is mutable here
            elif isinstance(value, str):
                attributes[key] = redact(value)  # pyright: ignore[reportIndexIssue]

    @override
    def shutdown(self) -> None:
        return None

    @override
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class RedactingSpanProcessor(SpanProcessor):
    """Route finished spans through a redaction step before exporting them.

    TODO(privacy, TunixR/R2Framework#202): not implemented yet; spans are
    forwarded unchanged. Strands exports prompts and completions (task, UI
    log, variables, user-typed input) as ``gen_ai.*`` span data, so those
    currently reach SigNoz in clear text. Implement here by exporting a
    sanitized copy of the span (``ReadableSpan`` is immutable) or by
    disabling Strands content capture. Exception events recorded through
    ``observability.exceptions`` are already redacted.
    """

    def __init__(self, delegate: SpanProcessor) -> None:
        self._delegate = delegate

    @override
    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        self._delegate.on_start(span, parent_context=parent_context)

    @override
    def on_end(self, span: ReadableSpan) -> None:
        self._delegate.on_end(span)

    @override
    def shutdown(self) -> None:
        self._delegate.shutdown()

    @override
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._delegate.force_flush(timeout_millis)
