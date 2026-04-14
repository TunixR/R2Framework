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
        "activities": {
            "nodes": [],
            "edges": [],
        },
    }


def test_from_payload_rejects_non_selector_visual_without_descriptor() -> None:
    payload = _base_payload()
    payload["activities"]["nodes"] = [
        {
            "id": "n1",
            "node_type": "activity",
            "attributes": {
                "state": "errored",
                "has_visual_ref": True,
                "selector_type": "ocr",
                "activity_name": "",
            },
        }
    ]

    with pytest.raises(NotImplementedError, match="visual-data-not-supported"):
        _ = RecoveryContext.from_payload(payload=payload)


def test_from_payload_accepts_selector_based_visual_with_descriptor() -> None:
    payload = _base_payload()
    payload["activities"]["nodes"] = [
        {
            "id": "n1",
            "node_type": "activity",
            "attributes": {
                "state": "past",
                "has_visual_ref": True,
                "selector_type": "selector",
                "selector_value": "#submit",
                "visual_ref_type": "screenshot",
                "visual_ref_value": "base64://abc",
                "activity_name": "Click Submit",
            },
        }
    ]

    context = RecoveryContext.from_payload(payload=payload)

    assert len(context.nodes) == 1
    assert context.nodes[0].node_type == "activity"
    assert context.nodes[0].selector_type == "selector"
    assert context.nodes[0].has_visual_ref is True


def test_to_payload_roundtrip_preserves_gate_condition_and_activity_state() -> None:
    payload = _base_payload()
    payload["activities"]["nodes"] = [
        {
            "id": "a1",
            "node_type": "activity",
            "attributes": {
                "state": "errored",
                "activity_name": "Type Amount",
            },
        },
        {
            "id": "g1",
            "node_type": "gate",
            "attributes": {
                "gate_type": "if",
                "condition_statement": "amount > 0",
            },
        },
    ]
    payload["activities"]["edges"] = [
        {
            "source": "a1",
            "target": "g1",
            "attributes": {"condition_statement": "on_error"},
        }
    ]

    context = RecoveryContext.from_payload(payload=payload)
    converted_payload = context.to_payload()

    assert (
        converted_payload["activities"]["nodes"][0]["attributes"]["state"] == "errored"
    )
    assert (
        converted_payload["activities"]["nodes"][1]["attributes"]["condition_statement"]
        == "amount > 0"
    )
    assert (
        converted_payload["activities"]["edges"][0]["attributes"]["condition_statement"]
        == "on_error"
    )


def test_to_dot_escapes_quotes_and_backslashes() -> None:
    payload = _base_payload()
    payload["activities"]["nodes"] = [
        {
            "id": "a1",
            "node_type": "activity",
            "attributes": {
                "state": "past",
                "activity_name": 'Open "Dialog"',
                "selector_type": "selector",
                "selector_value": r"C:\temp\dialog",
            },
        }
    ]
    payload["activities"]["edges"] = [
        {
            "source": "a1",
            "target": "a1",
            "attributes": {"condition_statement": 'path == "C:\\temp"'},
        }
    ]

    context = RecoveryContext.from_payload(payload=payload)
    dot = context.to_dot()

    assert 'activity_name="Open \\"Dialog\\""' in dot
    assert 'selector_value="C:\\\\temp\\\\dialog"' in dot
    assert 'condition_statement="path == \\"C:\\\\temp\\""' in dot


def test_to_dot_emits_node_then_outgoing_edges_for_source() -> None:
    payload = _base_payload()
    payload["activities"]["nodes"] = [
        {
            "id": "a",
            "node_type": "activity",
            "attributes": {"state": "past", "activity_name": "A"},
        },
        {
            "id": "b",
            "node_type": "activity",
            "attributes": {"state": "future", "activity_name": "B"},
        },
    ]
    payload["activities"]["edges"] = [
        {"source": "a", "target": "b", "attributes": {"condition_statement": "next"}},
        {"source": "b", "target": "a", "attributes": {}},
    ]

    context = RecoveryContext.from_payload(payload=payload)
    lines = context.to_dot().splitlines()

    node_a_idx = next(
        index for index, line in enumerate(lines) if line.startswith('    "a" [')
    )
    edge_a_b_idx = next(
        index
        for index, line in enumerate(lines)
        if line.startswith('    "a" -> "b" [condition_statement="next"]')
    )
    node_b_idx = next(
        index for index, line in enumerate(lines) if line.startswith('    "b" [')
    )

    assert node_a_idx < edge_a_b_idx < node_b_idx


def test_from_payload_edge_condition_fallback_is_deterministic() -> None:
    payload = _base_payload()
    payload["activities"]["nodes"] = [
        {
            "id": "a",
            "node_type": "activity",
            "attributes": {"state": "past", "activity_name": "A"},
        },
        {
            "id": "b",
            "node_type": "activity",
            "attributes": {"state": "future", "activity_name": "B"},
        },
    ]
    payload["activities"]["edges"] = [
        {
            "source": "a",
            "target": "b",
            "attributes": {
                "condition_statement": "primary",
                "condition": "secondary",
                "label": "fallback",
            },
        },
        {
            "source": "b",
            "target": "a",
            "attributes": {
                "condition": "secondary-only",
                "label": "fallback",
            },
        },
        {
            "source": "a",
            "target": "a",
            "attributes": {
                "label": "label-only",
            },
        },
    ]

    context = RecoveryContext.from_payload(payload=payload)

    assert [edge.condition for edge in context.edges] == [
        "primary",
        "secondary-only",
        "label-only",
    ]
