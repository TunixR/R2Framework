import logging
from uuid import UUID

import pytest

from observability.attributes import OTEL_EVENT_NAME
from observability.events import EVENT_FIELDS_ATTR, brief, log_event

LOGGER = logging.getLogger("tests.events")


def test_log_event_sets_message_and_extras(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    rid = UUID(int=1)

    log_event(LOGGER, "recovery.turn_failed", {"recovery.id": rid, "error.type": "X"})

    [record] = caplog.records
    assert record.getMessage() == f"recovery.turn_failed recovery.id={rid} error.type=X"
    assert vars(record)[OTEL_EVENT_NAME] == "recovery.turn_failed"
    assert vars(record)["recovery.id"] == str(rid)
    assert vars(record)[EVENT_FIELDS_ATTR] == ("recovery.id", "error.type")


def test_log_event_stringifies_tuples_and_list_items(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER.name)

    log_event(LOGGER, "x", {"client": ("127.0.0.1", 80), "fields": ["a", 1]})

    [record] = caplog.records
    assert vars(record)["client"] == "('127.0.0.1', 80)"
    assert vars(record)["fields"] == ["a", "1"]


def test_log_event_skips_disabled_levels(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER.name)

    log_event(LOGGER, "noisy", {"value": 1}, logging.DEBUG)

    assert caplog.records == []


def test_log_event_reports_caller_location(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER.name)

    log_event(LOGGER, "located")

    assert caplog.records[0].funcName == "test_log_event_reports_caller_location"


def test_brief_truncates_long_text() -> None:
    assert brief(None) == ""
    assert brief("short") == "short"
    assert brief("x" * 200, limit=10) == "xxxxxxx..."
