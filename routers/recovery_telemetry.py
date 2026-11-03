"""Telemetry for one recovery websocket turn.

The router describes what happened (payload received, record persisted,
turn failed...) and this module decides how that becomes spans, span
attributes and log events, so the handler reads as the business flow.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from opentelemetry.trace import Status, StatusCode
from pydantic import ValidationError

from observability import attributes as attrs
from observability.events import brief, error_type, field_paths, log_event
from observability.exceptions import record_exception

if TYPE_CHECKING:
    from collections.abc import Iterator
    from uuid import UUID

    from opentelemetry.trace import Span, Tracer
    from starlette.datastructures import Address

    from database.logging.models import RecoveryContext

logger = logging.getLogger(__name__)


def auth_failed(client: Address | None) -> None:
    """A robot connected with a missing, unknown or disabled key."""
    log_event(
        logger,
        attrs.EVENT_RECOVERY_AUTH_FAILED,
        {
            attrs.ERROR_TYPE: "invalid_robot_key",
            attrs.CLIENT_ADDRESS: client.host if client else None,
        },
        logging.WARNING,
    )


def invalid_field_paths(exc: BaseException) -> list[str]:
    """Field paths of the validation error behind ``exc``, without values."""
    cause = exc.__cause__
    return field_paths(cause.errors()) if isinstance(cause, ValidationError) else []


@contextmanager
def recovery_turn(
    tracer: Tracer, robot_key_id: UUID
) -> Iterator[RecoveryTurnTelemetry]:
    """Open the ``recovery.turn`` span for one websocket connection."""
    with tracer.start_as_current_span(
        attrs.SPAN_RECOVERY_TURN,
        attributes={attrs.ROBOT_KEY_ID: str(robot_key_id)},
        # Failures are classified by RecoveryTurnTelemetry, not by the SDK.
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        yield RecoveryTurnTelemetry(tracer, span)


class RecoveryTurnTelemetry:
    """Milestones of a recovery turn, recorded on its span and as log events.

    Call one method per milestone. The outcome is set exactly once, by
    ``completed`` or by one of the failure methods.
    """

    def __init__(self, tracer: Tracer, span: Span) -> None:
        self._tracer = tracer
        self.span = span
        self._recovery_id: str | None = None

    # --- Milestones ----------------------------------------------------------

    def payload_received(self, raw: str, data: Any) -> None:
        """Describe the raw payload by size and shape, never by content."""
        ui_log = data.get("ui_log") if isinstance(data, dict) else None
        self.span.set_attributes(
            {
                attrs.RECOVERY_PAYLOAD_SIZE: len(raw.encode()),
                attrs.RECOVERY_PAYLOAD_UI_LOG_COUNT: (
                    len(ui_log) if isinstance(ui_log, list) else 0  # pyright: ignore[reportUnknownArgumentType]
                ),
                attrs.RECOVERY_PAYLOAD_HAS_ERRORED_ACTIVITY: (
                    isinstance(data, dict) and bool(data.get("errored_act"))
                ),
            }
        )

    def agent_selected(self, agent_id: UUID) -> None:
        self.span.set_attribute(attrs.AGENT_ID, str(agent_id))

    def context_built(self, context: RecoveryContext) -> None:
        self.span.set_attributes(
            {
                attrs.RECOVERY_TASK_NAME: brief(context.task_name),
                attrs.RECOVERY_PLATFORM: context.platform,
                attrs.RECOVERY_OS: context.os,
                attrs.RECOVERY_PROCESS_MODEL: brief(context.model),
            }
        )

    @contextmanager
    def persisting(self) -> Iterator[None]:
        """Child span around the RobotException/RecoveryContext insert."""
        with self._tracer.start_as_current_span(attrs.SPAN_RECOVERY_PERSIST):
            yield

    def persisted(self, recovery_id: UUID) -> None:
        self._recovery_id = str(recovery_id)
        self.span.set_attribute(attrs.RECOVERY_ID, self._recovery_id)

    def completed(self, success: bool) -> None:
        self.span.set_attributes(
            {
                attrs.RECOVERY_SUCCESS: success,
                attrs.RECOVERY_OUTCOME: (
                    "success" if success else "completed_unsuccessful"
                ),
            }
        )

    # --- Failures ------------------------------------------------------------

    def no_gateway_agent(self) -> None:
        log_event(logger, attrs.EVENT_RECOVERY_NO_GATEWAY_AGENT, None, logging.ERROR)
        self._fail("no_gateway_agent")

    def client_disconnected(self) -> None:
        self.span.set_attribute(attrs.RECOVERY_OUTCOME, "client_disconnected")

    def invalid_payload(self, exc: BaseException) -> None:
        """Log and record the failing field paths only, never submitted values."""
        paths = invalid_field_paths(exc)
        log_event(
            logger,
            attrs.EVENT_RECOVERY_PAYLOAD_INVALID,
            {attrs.RECOVERY_PAYLOAD_INVALID_FIELDS: paths},
            logging.WARNING,
        )
        self.span.set_attributes(
            {
                attrs.RECOVERY_OUTCOME: "invalid_payload",
                attrs.RECOVERY_PAYLOAD_INVALID_FIELDS: paths,
            }
        )
        record_exception(
            self.span,
            exc,
            escaped=False,
            message=f"Invalid recovery payload: fields={paths}",
        )

    def failed(self, exc: BaseException) -> None:
        """An unexpected error ended the turn."""
        log_event(
            logger,
            attrs.EVENT_RECOVERY_TURN_FAILED,
            {attrs.RECOVERY_ID: self._recovery_id, attrs.ERROR_TYPE: error_type(exc)},
            logging.ERROR,
            exc_info=exc,
        )
        self.span.set_attribute(attrs.RECOVERY_OUTCOME, "internal_error")
        record_exception(self.span, exc, escaped=False)

    def keep_alive_failed(self, exc: BaseException) -> None:
        log_event(
            logger,
            attrs.EVENT_RECOVERY_KEEP_ALIVE_FAILED,
            {attrs.ERROR_TYPE: error_type(exc)},
            logging.WARNING,
        )

    def _fail(self, outcome: str) -> None:
        self.span.set_attribute(attrs.RECOVERY_OUTCOME, outcome)
        self.span.set_status(Status(StatusCode.ERROR, outcome))
