from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def valid_recovery_payload() -> dict[str, Any]:
    return {
        "task_name": "Invoice Processing",
        "platform": "uipath",
        "os": "windows",
        "variables": {"invoice_id": "INV-100", "retry": 1},
        "ui_log": [
            {
                "case_id": "1",
                "activity_id": None,
                "activity_name": "Type invoice id",
                "event_id": "0",
                "event_name": "Type invoice id",
                "action_type": "type",
                "application": "SAP",
                "input": "INV-100",
                "ui_element_target": "Invoice ID",
                "ui_group": None,
                "timestamp": "2026-04-17T10:00:00Z",
                "previous_state": "",
                "current_state": "INV-100",
            }
        ],
        "errored_act": {
            "case_id": "1",
            "activity_id": None,
            "activity_name": "Click Submit",
            "event_id": "2",
            "event_name": None,
            "action_type": "click",
            "application": "SAP",
            "input": "",
            "error_code": "E500",
            "error_description": "Submit button disabled",
        },
        "model": '<process id="invoice-processing"></process>',
    }


@pytest.fixture
def minimal_recovery_ui_log_entry() -> dict[str, str | None]:
    return {
        "case_id": "1",
        "activity_id": None,
        "activity_name": "Type invoice id",
        "event_id": "0",
        "event_name": "Type invoice id",
        "action_type": "type",
        "application": "SAP",
        "input": "INV-100",
        "ui_element_target": "Invoice ID",
        "ui_group": None,
        "timestamp": "2026-04-17T10:00:00Z",
        "previous_state": "",
        "current_state": "INV-100",
    }
