"""Telemetry for a GUI agent task: one Strands tool call driving the robot.

The agent loop reports milestones (screenshot taken, action sent, retry...)
and this module turns them into spans, span attributes and log events.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from opentelemetry import trace

from observability import attributes as attrs
from observability.events import brief, error_type, log_event
from observability.exceptions import record_exception

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.trace import Span

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class GuiActionTelemetry:
    def __init__(self, span: Span) -> None:
        self._span = span

    def result(self, success: bool) -> None:
        self._span.set_attribute(attrs.GUI_ACTION_SUCCESS, success)

    def failed(self, error: BaseException) -> None:
        """Record a client-side failure; ``error`` must not carry user input."""
        record_exception(self._span, error)


class GuiScreenshotTelemetry:
    def __init__(self, span: Span) -> None:
        self._span = span

    def taken(self, image: bytes, width: int, height: int) -> None:
        self._span.set_attributes(
            {
                attrs.GUI_SCREENSHOT_WIDTH: width,
                attrs.GUI_SCREENSHOT_HEIGHT: height,
                attrs.GUI_SCREENSHOT_SIZE: len(image),
            }
        )


class GuiTaskTelemetry:
    """Describes the task on the current span (Strands ``execute_tool``).

    The tool call already has a span, so the task enriches it instead of
    opening a redundant one; actions and screenshots get child spans.

    Two loops use it: UI-TARS, which parses free text and counts iterations
    itself, and ``TooledGuiAgent``, whose actions are Strands tools and which
    reads ``actions`` and ``outcome`` back.
    """

    def __init__(
        self, *, task: str, model: str, ui_log: list[Any], errored_act: Any
    ) -> None:
        self._span = trace.get_current_span()
        self.actions = 0
        self.outcome: str | None = None
        self._span.set_attributes(
            {
                attrs.GUI_TASK_NAME: brief(task),
                attrs.GUI_TASK_PROCESS_MODEL: brief(model),
                attrs.GUI_TASK_UI_LOG_COUNT: len(ui_log),
                attrs.GUI_TASK_HAS_ERRORED_ACTIVITY: bool(errored_act),
            }
        )

    @contextmanager
    def screenshot(self) -> Iterator[GuiScreenshotTelemetry]:
        """Child span around one screenshot round trip to the robot."""
        with tracer.start_as_current_span(attrs.SPAN_GUI_SCREENSHOT) as span:
            yield GuiScreenshotTelemetry(span)

    @contextmanager
    def action(self, iteration: int, action_type: str) -> Iterator[GuiActionTelemetry]:
        """Child span around sending one action and waiting for its result."""
        self.actions += 1
        with tracer.start_as_current_span(
            attrs.SPAN_GUI_ACTION,
            attributes={
                attrs.GUI_ACTION_ITERATION: iteration,
                attrs.GUI_ACTION_TYPE: action_type,
            },
            # Only client-side failures are recorded, via ``failed``.
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            yield GuiActionTelemetry(span)

    def retry(self, iteration: int, exc: BaseException) -> None:
        """The model's step could not be parsed or executed and is retried."""
        log_event(
            logger,
            attrs.EVENT_GUI_ACTION_RETRY,
            {
                attrs.GUI_ACTION_ITERATION: iteration,
                attrs.ERROR_TYPE: error_type(exc),
                attrs.EXCEPTION_MESSAGE: brief(exc),
            },
            logging.WARNING,
        )

    def done(self, iterations: int) -> None:
        self._finish(iterations, "done")

    def max_actions_exceeded(self, iterations: int, max_actions: int) -> None:
        self._finish(iterations, "max_actions_exceeded")
        log_event(
            logger,
            attrs.EVENT_GUI_MAX_ACTIONS_EXCEEDED,
            {attrs.GUI_TASK_MAX_ACTIONS: max_actions},
            logging.WARNING,
        )

    def stopped(self, iterations: int) -> None:
        """The model reply had no parsable content; the loop ended early."""
        self._finish(iterations, "unparseable_response")

    def model_stopped(self, iterations: int) -> None:
        """The agent loop returned without the model calling the ``finished`` tool.

        Call it once, after the loop: turns that end in a tool call keep it running.
        """
        self._finish(iterations, "model_stopped")

    def client_disconnected(self, iterations: int) -> None:
        self._finish(iterations, "client_disconnected")

    def failed(
        self, iterations: int, exc: BaseException, *, escaped: bool = False
    ) -> None:
        """An unexpected error ended the task (raised if ``escaped``, else returned)."""
        self._finish(iterations, "error")
        record_exception(self._span, exc, escaped=escaped)

    def _finish(self, iterations: int, outcome: str) -> None:
        self.outcome = outcome
        self._span.set_attributes(
            {attrs.GUI_TASK_ITERATIONS: iterations, attrs.GUI_TASK_OUTCOME: outcome}
        )
