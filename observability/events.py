"""Structured log events: one call yields a readable line and indexed fields."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

# Names of the fields a ``log_event`` call attached to the record. Formatters
# read this instead of keeping their own allowlist of known field names.
EVENT_FIELDS_ATTR = "event_fields"

_MAX_TEXT = 120

type FieldValue = str | bool | int | float | Sequence[str] | None


def brief(value: object, limit: int = _MAX_TEXT) -> str:
    """Bound free text (task names, model context) before it reaches telemetry."""
    text = "" if value is None else str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def elapsed_ms(start: float) -> float:
    """Milliseconds since a ``time.perf_counter()`` reading, rounded to 0.1."""
    return round((time.perf_counter() - start) * 1000, 1)


def error_type(exc: BaseException | None) -> str | None:
    return type(exc).__name__ if exc is not None else None


def _normalize(value: object) -> FieldValue:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list):
        return [str(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    # UUIDs, socket addresses (named tuples), exceptions...
    return str(value)


def log_event(
    logger: logging.Logger,
    event: str,
    /,
    level: int = logging.INFO,
    *,
    exc_info: bool = False,
    **fields: object,
) -> None:
    """Log ``event`` with ``fields`` both in the message and as record extras.

    The message reads ``event key=value ...`` for console output, while the
    extras let the JSON formatter and the OTLP exporter index each field.
    Non-primitive values (UUIDs, addresses) are stringified so every exporter
    sees the same value.
    """
    if not logger.isEnabledFor(level):
        return
    normalized = {key: _normalize(value) for key, value in fields.items()}
    message = " ".join(
        [event, *(f"{key}={value}" for key, value in normalized.items())]
    )
    logger.log(
        level,
        message,
        exc_info=exc_info,
        stacklevel=2,
        extra={
            "event": event,
            **normalized,
            EVENT_FIELDS_ATTR: ("event", *normalized),
        },
    )
