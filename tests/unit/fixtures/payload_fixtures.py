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
        "activities": {
            "nodes": [
                {
                    "id": "A1",
                    "node_type": "activity",
                    "attributes": {
                        "state": "errored",
                        "activity_name": "Click Submit",
                        "selector_type": "selector",
                        "selector_value": "#submit",
                    },
                },
                {
                    "id": "G1",
                    "node_type": "gate",
                    "attributes": {
                        "gate_type": "if",
                        "condition_statement": "invoice_id != ''",
                    },
                },
            ],
            "edges": [
                {
                    "source": "A1",
                    "target": "G1",
                    "attributes": {"condition_statement": "next"},
                }
            ],
        },
    }
