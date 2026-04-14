from sqlmodel import Session, select

from database.logging.models import (
    RecoveryContext,
    RecoveryGraphEdge,
    RecoveryGraphNode,
    RobotException,
)


def test_recovery_context_links_to_robot_exception(session: Session):
    robot_exception = RobotException(exception_details={"message": "failed"})
    session.add(robot_exception)
    session.commit()
    session.refresh(robot_exception)

    recovery_context = RecoveryContext(
        task_name="Invoice Recovery",
        platform="uipath",
        os="windows",
        variables={"invoice_id": "INV-001"},
    )
    recovery_context.robot_exception = robot_exception
    session.add(recovery_context)
    session.commit()
    session.refresh(recovery_context)

    assert recovery_context.robot_exception_id == robot_exception.id
    assert recovery_context.robot_exception is not None
    assert recovery_context.robot_exception.id == robot_exception.id


def test_recovery_context_persists_nodes_and_edges(session: Session):
    robot_exception = RobotException(exception_details={"message": "failed"})
    session.add(robot_exception)
    session.commit()
    session.refresh(robot_exception)

    recovery_context = RecoveryContext.from_payload(
        payload={
            "task_name": "Invoice Recovery",
            "platform": "uipath",
            "os": "windows",
            "variables": {"invoice_id": "INV-001"},
            "activities": {
                "nodes": [
                    {
                        "id": "n1",
                        "node_type": "activity",
                        "attributes": {
                            "state": "past",
                            "activity_name": "OpenInvoice",
                            "selector_type": "selector",
                            "selector_value": "#open-btn",
                        },
                    },
                    {
                        "id": "n2",
                        "node_type": "gate",
                        "attributes": {
                            "gate_type": "xor",
                            "condition_statement": "invoice_id != ''",
                        },
                    },
                ],
                "edges": [
                    {
                        "source": "n1",
                        "target": "n2",
                        "attributes": {"condition_statement": "on_error"},
                    }
                ],
            },
        },
    )
    recovery_context.robot_exception = robot_exception
    session.add(recovery_context)
    session.commit()

    stored_context = session.exec(
        select(RecoveryContext).where(RecoveryContext.id == recovery_context.id)
    ).one()
    stored_nodes = stored_context.nodes
    stored_edges = stored_context.edges

    assert stored_context.robot_exception_id == robot_exception.id
    assert len(stored_nodes) == 2
    assert len(stored_edges) == 1
    assert all(
        stored_edge.recovery_context_id == stored_context.id
        for stored_edge in stored_edges
    )
    assert all(
        stored_node.recovery_context_id == stored_context.id
        for stored_node in stored_nodes
    )
    assert stored_nodes[0].node_type == "activity"
    assert stored_nodes[1].node_type == "gate"


def test_recovery_context_to_payload_returns_structured_shape():
    recovery_context = RecoveryContext(
        task_name="Invoice Recovery",
        platform="uipath",
        os="windows",
        variables={"invoice_id": "INV-001"},
    )
    recovery_context.nodes = [
        RecoveryGraphNode(
            node_key="n1",
            node_type="activity",
            state="past",
            activity_name="OpenInvoice",
        )
    ]
    recovery_context.edges = [
        RecoveryGraphEdge(
            source_node_key="n1",
            target_node_key="n1",
            condition="loop",
        )
    ]

    payload = recovery_context.to_payload()

    assert payload["activities"]["nodes"][0]["node_type"] == "activity"
    assert payload["activities"]["edges"][0]["source"] == "n1"
    assert (
        payload["activities"]["edges"][0]["attributes"]["condition_statement"] == "loop"
    )


def test_recovery_context_from_payload_rejects_visual_not_supported():
    recovery_payload = {
        "task_name": "Invoice Recovery",
        "platform": "uipath",
        "os": "windows",
        "variables": {},
        "activities": {
            "nodes": [
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
            ],
            "edges": [],
        },
    }

    try:
        _ = RecoveryContext.from_payload(payload=recovery_payload)
        assert False, "Expected NotImplementedError for unsupported visual payload."
    except NotImplementedError:
        assert True


def test_recovery_context_to_dot_returns_graph_with_nodes_and_edges():
    recovery_context = RecoveryContext(
        task_name="Invoice Recovery",
        platform="uipath",
        os="windows",
        variables={"invoice_id": "INV-001"},
    )
    recovery_context.nodes = [
        RecoveryGraphNode(
            node_key="past_1",
            node_type="activity",
            state="past",
            activity_name="Type Vendor Name",
            selector_type="selector",
            selector_value="<selector/>",
        ),
        RecoveryGraphNode(
            node_key="gate_1",
            node_type="gate",
            gate_type="xor",
            condition_statement="notification_medium",
        ),
    ]
    recovery_context.edges = [
        RecoveryGraphEdge(
            source_node_key="past_1",
            target_node_key="gate_1",
            condition="on_error",
        )
    ]

    dot = recovery_context.to_dot()

    assert "digraph Activities" in dot
    assert '"past_1" [node_type="activity"' in dot
    assert '"gate_1" [node_type="gate"' in dot
    assert '"past_1" -> "gate_1" [condition_statement="on_error"]' in dot


def test_recovery_context_to_dot_complex():
    recoveryContext = RecoveryContext(
        task_name="Complex Recovery",
        platform="uipath",
        os="windows",
        variables={},
    )
    recoveryContext.nodes = [
        RecoveryGraphNode(
            node_key="a",
            node_type="activity",
            state="past",
            activity_name="Activity A",
        ),
        RecoveryGraphNode(
            node_key="b",
            node_type="activity",
            state="past",
            activity_name="Activity B",
        ),
        RecoveryGraphNode(
            node_key="c",
            node_type="activity",
            state="errored",
            activity_name="Activity C",
        ),
        RecoveryGraphNode(
            node_key="d",
            node_type="activity",
            state="future",
            activity_name="Activity D",
        ),
        RecoveryGraphNode(
            node_key="e",
            node_type="gate",
            gate_type="xor",
            condition_statement="condition_e",
        ),
        RecoveryGraphNode(
            node_key="f",
            node_type="activity",
            state="future",
            activity_name="Activity F",
        ),
        RecoveryGraphNode(
            node_key="g",
            node_type="activity",
            state="future",
            activity_name="Activity G",
        ),
        RecoveryGraphNode(
            node_key="h",
            node_type="activity",
            state="future",
            activity_name="Activity H",
        ),
        RecoveryGraphNode(
            node_key="i",
            node_type="gate",
            gate_type="xor",
            condition_statement="condition_i",
        ),
        RecoveryGraphNode(
            node_key="j",
            node_type="activity",
            state="future",
            activity_name="Activity J",
        ),
    ]
    recoveryContext.edges = [
        RecoveryGraphEdge(
            source_node_key="a",
            target_node_key="b",
        ),
        RecoveryGraphEdge(
            source_node_key="b",
            target_node_key="c",
        ),
        RecoveryGraphEdge(
            source_node_key="c",
            target_node_key="d",
            condition="on_error",
        ),
        RecoveryGraphEdge(
            source_node_key="d",
            target_node_key="e",
        ),
        RecoveryGraphEdge(
            source_node_key="e",
            target_node_key="f",
            condition="condition_e_true",
        ),
        RecoveryGraphEdge(
            source_node_key="e",
            target_node_key="g",
            condition="condition_e_false",
        ),
        RecoveryGraphEdge(
            source_node_key="g",
            target_node_key="h",
        ),
        RecoveryGraphEdge(
            source_node_key="f",
            target_node_key="i",
        ),
        RecoveryGraphEdge(
            source_node_key="i",
            target_node_key="j",
        ),
        RecoveryGraphEdge(
            source_node_key="h",
            target_node_key="i",
        ),
    ]

    dot = recoveryContext.to_dot()

    assert "digraph Activities" in dot
    for node_key in ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]:
        assert f'"{node_key}"' in dot
    assert '"a" -> "b"' in dot
    assert '"b" -> "c"' in dot
    assert '"c" -> "d" [condition_statement="on_error"]' in dot
    assert '"d" -> "e"' in dot
    assert '"e" -> "f" [condition_statement="condition_e_true"]' in dot
    assert '"e" -> "g" [condition_statement="condition_e_false"]' in dot
    assert '"g" -> "h"' in dot
    assert '"i" -> "j"' in dot
    assert '"f" -> "i"' in dot
    assert '"h" -> "i"' in dot
