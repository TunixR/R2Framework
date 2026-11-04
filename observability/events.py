"""Structured log events: one call yields a readable line and indexed attributes.

Use an event for something that happened at a point in time and is not
already a span: a rejection, a recovered failure, a misconfiguration, an
accounting record. Durations and nesting belong on spans instead.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from observability.attributes import OTEL_EVENT_NAME
from settings import TELEMETRY_MAX_TEXT_LENGTH

# Names of the attributes a ``log_event`` call attached to the record. The JSON
# formatter reads this instead of keeping its own allowlist; the OTel export
# pipeline drops it.
EVENT_FIELDS_ATTR = "event_fields"

type AttributeValue = str | bool | int | float | Sequence[str] | None


def brief(value: object, limit: int = TELEMETRY_MAX_TEXT_LENGTH) -> str:
    """Bound free text (task names, process models) before it reaches telemetry."""
    text = "" if value is None else str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def field_paths(errors: Iterable[Mapping[str, Any]]) -> list[str]:
    """Dotted locations of validation errors, deduplicated, without input values."""
    paths: list[str] = []
    for error in errors:
        path = ".".join(str(part) for part in error.get("loc", ()))
        if path and path not in paths:
            paths.append(path)
    return paths


def error_type(exc: BaseException | None) -> str | None:
    return type(exc).__name__ if exc is not None else None


def _normalize(value: object) -> AttributeValue:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list):
        return [str(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    # UUIDs, socket addresses (named tuples), exceptions...
    return str(value)


def log_event(
    logger: logging.Logger,
    event: str,
    attributes: Mapping[str, object] | None = None,
    /,
    level: int = logging.INFO,
    *,
    exc_info: bool | BaseException = False,
) -> None:
    """Log ``event`` with ``attributes`` both in the message and as record extras.

    The message reads ``event key=value ...`` for console output. The event
    name is attached as ``otel.event.name``, which the OTel logging handler
    promotes to the LogRecord ``event_name`` field, and each attribute is
    exported under its (dotted) key. Non-primitive values are stringified so
    every exporter sees the same value.
    """
    if not logger.isEnabledFor(level):
        return
    normalized = {key: _normalize(value) for key, value in (attributes or {}).items()}
    message = " ".join(
        [event, *(f"{key}={value}" for key, value in normalized.items())]
    )
    logger.log(
        level,
        message,
        exc_info=exc_info,
        stacklevel=2,
        extra={
            OTEL_EVENT_NAME: event,
            **normalized,
            EVENT_FIELDS_ATTR: tuple(normalized),
        },
    )
