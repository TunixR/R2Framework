from __future__ import annotations

from typing import Any

import pytest

from database.logging.models import RecoveryContext


def _base_payload() -> dict[str, Any]:
    return {
        "task_name": "Invoice Recovery",
        "platform": "uipath",
        "os": "windows",
        "variables": {"invoice_id": "INV-001"},
        "ui_log": [
            {
                "case_id": "CASE-1",
                "activity_id": "ACT-1",
                "event_id": "EVT-1",
                "event_name": "InvoiceOpened",
                "activity_name": "Open Invoice",
                "action_type": "click",
                "application": "SAP",
                "input": "INV-001",
                "ui_element_target": "Open Invoice",
                "ui_group": "Invoice List",
                "timestamp": "2026-04-17T10:00:00Z",
                "previous_state": "idle",
                "current_state": "opened",
            }
        ],
        "errored_act": {
            "case_id": "CASE-1",
            "activity_id": "ACT-2",
            "event_id": "EVT-2",
            "event_name": "SubmitFailed",
            "activity_name": "Submit",
            "action_type": "click",
            "application": "SAP",
            "input": "INV-001",
            "error_code": "E500",
            "error_description": "Submit button disabled",
        },
        "model": "<process id='invoice-recovery' />",
    }


def test_from_payload_maps_core_fields() -> None:
    payload = _base_payload()
    context = RecoveryContext.from_payload(payload=payload)

    assert context.task_name == "Invoice Recovery"
    assert context.platform == "uipath"
    assert context.os == "windows"
    assert context.variables == {"invoice_id": "INV-001"}


def test_from_payload_maps_ui_log_errored_act_and_model() -> None:
    payload = _base_payload()

    context = RecoveryContext.from_payload(payload=payload)

    assert len(context.ui_log_entries) == 1
    assert context.ui_log_entries[0].case_id == "CASE-1"
    assert context.ui_log_entries[0].event_id == "EVT-1"
    assert context.ui_log_entries[0].activity_name == "Open Invoice"
    assert context.errored_activity is not None
    assert context.errored_activity.case_id == "CASE-1"
    assert context.errored_activity.event_id == "EVT-2"
    assert context.errored_activity.error_code == "E500"
    assert context.model == "<process id='invoice-recovery' />"


def test_to_payload_roundtrip_preserves_normalized_shape() -> None:
    payload = _base_payload()
    payload["ui_log"][0]["activity_name"] = None
    payload["ui_log"][0]["application"] = None
    payload["ui_log"][0]["input"] = None
    payload["ui_log"][0]["ui_element_target"] = None
    payload["ui_log"][0]["ui_group"] = None
    payload["ui_log"][0]["previous_state"] = None
    payload["ui_log"][0]["current_state"] = None

    payload["errored_act"]["activity_name"] = None
    payload["errored_act"]["application"] = None
    payload["errored_act"]["input"] = None

    context = RecoveryContext.from_payload(payload=payload)
    converted_payload = context.model_dump()

    assert converted_payload["task_name"] == "Invoice Recovery"
    assert converted_payload["ui_log"][0]["case_id"] == "CASE-1"
    assert converted_payload["ui_log"][0]["event_id"] == "EVT-1"
    assert converted_payload["ui_log"][0]["activity_name"] is None
    assert converted_payload["ui_log"][0]["application"] is None
    assert converted_payload["ui_log"][0]["input"] is None
    assert converted_payload["errored_act"]["case_id"] == "CASE-1"
    assert converted_payload["errored_act"]["event_id"] == "EVT-2"
    assert converted_payload["errored_act"]["activity_name"] is None
    assert converted_payload["errored_act"]["application"] is None
    assert converted_payload["errored_act"]["input"] is None
    assert converted_payload["model"] == "<process id='invoice-recovery' />"


def test_to_payload_preserves_model_xml_text() -> None:
    payload = _base_payload()
    payload["model"] = (
        "<process id='invoice-recovery'><step id='submit'>Click</step></process>"
    )

    context = RecoveryContext.from_payload(payload=payload)
    converted_payload = context.model_dump()

    assert (
        converted_payload["model"]
        == "<process id='invoice-recovery'><step id='submit'>Click</step></process>"
    )


def test_from_payload_accepts_nullable_fields() -> None:
    payload = _base_payload()
    payload["ui_log"][0]["activity_name"] = None
    payload["ui_log"][0]["application"] = None
    payload["ui_log"][0]["input"] = None
    payload["ui_log"][0]["ui_element_target"] = None
    payload["ui_log"][0]["ui_group"] = None
    payload["ui_log"][0]["previous_state"] = None
    payload["ui_log"][0]["current_state"] = None

    payload["errored_act"]["activity_name"] = None
    payload["errored_act"]["application"] = None
    payload["errored_act"]["input"] = None

    context = RecoveryContext.from_payload(payload=payload)
    assert context.ui_log_entries[0].activity_name is None
    assert context.ui_log_entries[0].application is None
    assert context.ui_log_entries[0].input is None
    assert context.ui_log_entries[0].ui_element_target is None
    assert context.ui_log_entries[0].ui_group is None
    assert context.ui_log_entries[0].previous_state is None
    assert context.ui_log_entries[0].current_state is None
    assert context.errored_activity is not None
    assert context.errored_activity.activity_name is None
    assert context.errored_activity.application is None
    assert context.errored_activity.input is None


def test_from_payload_rejects_invalid_model_payload() -> None:
    payload = _base_payload()
    payload["model"] = "   "

    with pytest.raises(ValueError, match="model must be a non-empty string"):
        _ = RecoveryContext.from_payload(payload=payload)


def test_from_payload_normalizes_ids_to_strings() -> None:
    payload = _base_payload()
    payload["ui_log"][0]["case_id"] = 100
    payload["ui_log"][0]["event_id"] = 200
    payload["ui_log"][0]["activity_id"] = 300
    payload["errored_act"]["case_id"] = 101
    payload["errored_act"]["event_id"] = 201
    payload["errored_act"]["activity_id"] = 301

    context = RecoveryContext.from_payload(payload=payload)

    assert context.ui_log_entries[0].case_id == "100"
    assert context.ui_log_entries[0].event_id == "200"
    assert context.ui_log_entries[0].activity_id == "300"
    assert context.errored_activity is not None
    assert context.errored_activity.case_id == "101"
    assert context.errored_activity.event_id == "201"
    assert context.errored_activity.activity_id == "301"


@pytest.mark.parametrize("field", ["case_id", "event_id"])
def test_from_payload_rejects_empty_required_ids(field: str) -> None:
    payload = _base_payload()
    payload["ui_log"][0][field] = "  "

    with pytest.raises(ValueError, match="id fields must be non-empty"):
        _ = RecoveryContext.from_payload(payload=payload)


@pytest.mark.parametrize("field", ["case_id", "event_id"])
def test_from_payload_rejects_empty_required_ids_in_errored_act(
    field: str,
) -> None:
    payload = _base_payload()
    payload["errored_act"][field] = "  "

    with pytest.raises(ValueError, match="id fields must be non-empty"):
        _ = RecoveryContext.from_payload(payload=payload)
