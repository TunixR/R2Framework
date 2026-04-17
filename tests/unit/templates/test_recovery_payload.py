from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from templates.recovery_payload import RecoveryPayload


def _valid_payload() -> dict[str, Any]:
    return {
        "task_name": "Submit invoice",
        "platform": "uipath",
        "os": "windows",
        "variables": {"invoice_id": "INV-123"},
        "ui_log": [
            {
                "model_act_id": "A1",
                "activity_name": "Type Into",
                "action_type": "type",
                "application": "SAP",
                "input": "INV-123",
                "ui_element_target": "Invoice Field",
                "ui_group": "Invoice Form",
                "timestamp": "2026-04-17T12:00:00Z",
                "previous_state": "",
                "current_state": "INV-123",
            }
        ],
        "errored_act": {
            "model_act_id": "A2",
            "activity_name": "Click Submit",
            "action_type": "click",
            "application": "SAP",
            "input": "",
            "error_code": "E500",
            "error_description": "Button disabled",
        },
        "model": '<process id="recover"></process>',
    }


def test_payload_rejects_unknown_top_level_field():
    payload = _valid_payload()
    payload["unknown"] = "value"

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)
        _ = RecoveryPayload.model_validate(payload)


def test_payload_rejects_empty_model_string():
    payload = _valid_payload()
    payload["model"] = ""

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_accepts_non_xml_model_string():
    payload = _valid_payload()
    payload["model"] = "not xml"

    parsed = RecoveryPayload.model_validate(payload)

    assert parsed.model == "not xml"


def test_payload_allows_none_input_in_errored_act():
    payload = _valid_payload()
    payload["errored_act"]["input"] = None

    parsed = RecoveryPayload.model_validate(payload)

    assert parsed.errored_act.input is None


def test_payload_rejects_whitespace_only_model_string():
    payload = _valid_payload()
    payload["model"] = "   \n\t  "

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_rejects_unknown_ui_log_field():
    payload = _valid_payload()
    payload["ui_log"][0]["unexpected_attr"] = "x"

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_rejects_unknown_errored_act_field():
    payload = _valid_payload()
    payload["errored_act"]["unexpected_attr"] = "x"

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_requires_all_ui_log_fields():
    payload = _valid_payload()
    payload["ui_log"][0].pop("timestamp")

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_rejects_malformed_ui_log_timestamp():
    payload = _valid_payload()
    payload["ui_log"][0]["timestamp"] = "17-04-2026 12:00:00"

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_requires_errored_act():
    payload = _valid_payload()
    payload.pop("errored_act")

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_requires_model():
    payload = _valid_payload()
    payload.pop("model")

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)
