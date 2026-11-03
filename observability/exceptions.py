"""Global exception handling that records failures on the active span."""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING, cast

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from observability.correlation import get_request_id
from observability.logging import redact

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastapi import FastAPI, Request
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


def record_exception(
    span: Span,
    exc: BaseException,
    *,
    escaped: bool = True,
    message: str | None = None,
) -> None:
    """Record an exception on a span so SigNoz can index it.

    The SDK builds ``exception.message``/``exception.stacktrace`` from the raw
    exception, so we override them with redacted copies to keep secrets out of
    SigNoz. Caller-supplied attributes win over the SDK defaults.

    Args:
        span: Span that should carry the exception event.
        exc: Exception to record.
        escaped: Whether the exception propagated out of a span boundary.
        message: Optional sanitized message (e.g. field paths only). When set,
            the exported stack trace is replaced by this message so raw
            exception text cannot leak.
    """
    if not span.is_recording():
        return
    if message is None:
        safe_message = redact(str(exc))
        stacktrace = redact("".join(traceback.format_exception(exc)))
    else:
        # Validation messages can embed submitted values in both the final line
        # and the ``from exc`` cause chain, so do not export the traceback.
        safe_message = stacktrace = redact(message)
    span.record_exception(
        exc,
        attributes={
            "exception.message": safe_message,
            "exception.stacktrace": stacktrace,
        },
        escaped=escaped,
    )
    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(HTTPException, exc)
    if error.status_code >= 500:
        logger.error(
            "http_error status=%d method=%s path=%s",
            error.status_code,
            request.method,
            request.url.path,
            exc_info=exc,
        )
        record_exception(trace.get_current_span(), exc)
    else:
        logger.warning(
            "http_client_error status=%d method=%s path=%s detail=%s",
            error.status_code,
            request.method,
            request.url.path,
            error.detail,
        )
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail},
        headers=error.headers,
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    error = cast(RequestValidationError, exc)
    details: Sequence[dict[str, object]] = [
        {
            "loc": list(detail.get("loc", ())),
            "msg": detail.get("msg", ""),
            "type": detail.get("type", ""),
        }
        for detail in error.errors()
    ]
    logger.warning(
        "request_validation_failed method=%s path=%s errors=%s",
        request.method,
        request.url.path,
        details,
    )
    return JSONResponse(status_code=422, content={"detail": details})


class UnhandledExceptionMiddleware:
    """Turn unhandled exceptions into a generic 500 and record them on the span.

    This runs inside the OpenTelemetry span and outside Starlette's exception
    middleware, so the exception is recorded exactly once (the instrumentor's
    own handler never sees it).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if scope["type"] != "http" or response_started:
                raise
            logger.error(
                "unhandled_exception method=%s path=%s",
                scope.get("method"),
                scope.get("path"),
                exc_info=exc,
            )
            record_exception(trace.get_current_span(), exc)
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": get_request_id(),
                },
            )
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
