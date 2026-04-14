from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from templates.recovery_payload import RecoveryPayload


def _valid_payload() -> dict[str, Any]:
    return {
        "schema_version": "3.0",
        "task_name": "Submit invoice",
        "platform": "uipath",
        "os": "windows",
        "variables": {"invoice_id": "INV-123"},
        "activities": {
            "nodes": [
                {
                    "id": "n1",
                    "node_type": "activity",
                    "attributes": {
                        "state": "errored",
                        "activity_name": "Type Into",
                    },
                }
            ],
            "edges": [],
        },
    }


def test_payload_requires_schema_version():
    payload = _valid_payload()
    payload.pop("schema_version")

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_rejects_unknown_top_level_field():
    payload = _valid_payload()
    payload["unknown"] = "value"

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_rejects_invalid_edge_reference():
    payload = _valid_payload()
    payload["activities"] = {
        "nodes": [
            {
                "id": "n1",
                "node_type": "activity",
                "attributes": {"state": "errored"},
            }
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_rejects_duplicate_activity_node_ids():
    payload = _valid_payload()
    payload["activities"] = {
        "nodes": [
            {"id": "n1", "node_type": "activity", "attributes": {"state": "errored"}},
            {"id": "n1", "node_type": "activity", "attributes": {"state": "errored"}},
        ],
        "edges": [],
    }

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_requires_activity_state():
    payload = _valid_payload()
    payload["activities"]["nodes"][0]["attributes"].pop("state")

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_rejects_unknown_activity_attribute():
    payload = _valid_payload()
    payload["activities"]["nodes"][0]["attributes"]["unexpected_attr"] = "x"

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_rejects_visual_pipeline_not_supported_activity():
    payload = _valid_payload()
    payload["activities"]["nodes"][0]["attributes"] = {
        "state": "errored",
        "has_visual_ref": True,
        "visual_ref_type": "screenshot",
        "visual_ref_value": "base64://placeholder",
        "activity_name": "",
    }

    with pytest.raises(ValidationError, match="visual-data-not-supported"):
        _ = RecoveryPayload.model_validate(payload)


def test_payload_supports_gate_nodes():
    payload = _valid_payload()
    payload["activities"]["nodes"].append(
        {
            "id": "n2",
            "node_type": "gate",
            "attributes": {
                "gate_type": "if",
                "condition_statement": "invoice_id != ''",
            },
        }
    )
    payload["activities"]["edges"] = [{"source": "n1", "target": "n2"}]

    parsed = RecoveryPayload.model_validate(payload)

    assert parsed.activities.nodes[1].node_type == "gate"


def test_payload_rejects_invalid_gate_attributes():
    payload = _valid_payload()
    payload["activities"]["nodes"].append(
        {
            "id": "n2",
            "node_type": "gate",
            "attributes": {
                "gate_type": "if",
                "condition_statement": "invoice_id != ''",
                "unexpected_attr": "x",
            },
        }
    )

    with pytest.raises(ValidationError):
        _ = RecoveryPayload.model_validate(payload)
