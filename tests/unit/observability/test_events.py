import logging
from uuid import UUID

import pytest

from observability.events import EVENT_FIELDS_ATTR, brief, log_event

LOGGER = logging.getLogger("tests.events")


def test_log_event_sets_message_and_extras(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    rid = UUID(int=1)

    log_event(LOGGER, "recovery.persisted", recovery_id=rid, duration_ms=1.5)

    [record] = caplog.records
    assert record.getMessage() == (
        f"recovery.persisted recovery_id={rid} duration_ms=1.5"
    )
    assert vars(record)["event"] == "recovery.persisted"
    assert vars(record)["recovery_id"] == str(rid)
    assert vars(record)["duration_ms"] == 1.5
    assert vars(record)[EVENT_FIELDS_ATTR] == ("event", "recovery_id", "duration_ms")


def test_log_event_stringifies_tuples_and_list_items(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER.name)

    log_event(LOGGER, "x", client=("127.0.0.1", 80), field_paths=["a", 1])

    [record] = caplog.records
    assert vars(record)["client"] == "('127.0.0.1', 80)"
    assert vars(record)["field_paths"] == ["a", "1"]


def test_log_event_skips_disabled_levels(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER.name)

    log_event(LOGGER, "noisy", logging.DEBUG, value=1)

    assert caplog.records == []


def test_log_event_reports_caller_location(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER.name)

    log_event(LOGGER, "located")

    assert caplog.records[0].funcName == "test_log_event_reports_caller_location"


def test_brief_truncates_long_text() -> None:
    assert brief(None) == ""
    assert brief("short") == "short"
    assert brief("x" * 200, limit=10) == "xxxxxxx..."
