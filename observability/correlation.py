"""Request correlation: one id shared by logs, spans, and responses."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING

from opentelemetry import trace
from starlette.datastructures import Headers, MutableHeaders

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the request id for the current task, if any."""
    return _request_id.get()


class RequestContextMiddleware:
    """Attach a request id to the scope, the active span, and the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = _request_id.set(request_id)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("request.id", request_id)

        async def send_with_request_id(message: Message) -> None:
            if scope["type"] == "http" and message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _request_id.reset(token)
