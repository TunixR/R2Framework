from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from database.agents.models import Agent
from database.logging.models import RecoveryContext, RobotException


@pytest.fixture
def valid_robot_key_raw(make_robot_key) -> str:  # pyright: ignore[reportMissingParameterType]
    key_raw = "test-robot-key-payload-0001"
    _ = make_robot_key(name="Enabled", enabled=True, key_raw=key_raw)
    return key_raw


def test_recovery_ws_ingest_stores_raw_payload_and_normalized_context(
    session: Session,
    client: TestClient,
    valid_robot_key_raw: str,
    valid_recovery_payload: dict[str, Any],
    gateway_agent: Agent,  # pyright: ignore[reportUnusedParameter]
    monkeypatch,  # pyright: ignore[reportMissingParameterType]
):
    captured_invocation: dict[str, Any] = {}

    async def _fake_call(_self, invocation_state=None, **kwargs):  # pyright: ignore[reportMissingParameterType]
        captured_invocation["invocation_state"] = invocation_state
        captured_invocation["kwargs"] = kwargs
        return {"success": True, "continue_from_step": 2}

    monkeypatch.setattr(Agent, "__call__", _fake_call, raising=True)

    headers = {"X-ROBOT-KEY": valid_robot_key_raw}
    with client.websocket_connect(
        "/recovery/robot_exception/ws", headers=headers
    ) as ws:
        ws.send_json(valid_recovery_payload)
        message = ws.receive_json()

    assert message["type"] == "done"
    assert message["content"]["success"] is True
    assert message["content"]["continue_from_step"] == 2

    robot_exception = session.get(RobotException, UUID(message["id"]))
    assert robot_exception is not None
    assert robot_exception.exception_details == valid_recovery_payload

    recovery_context = session.exec(
        select(RecoveryContext).where(
            RecoveryContext.robot_exception_id == robot_exception.id
        )
    ).first()
    assert recovery_context is not None
    assert recovery_context.task_name == valid_recovery_payload["task_name"]
    assert recovery_context.platform == valid_recovery_payload["platform"]
    assert recovery_context.os == valid_recovery_payload["os"]
    assert recovery_context.variables == valid_recovery_payload["variables"]
    assert len(recovery_context.nodes) == 2
    assert len(recovery_context.edges) == 1

    assert (
        captured_invocation["invocation_state"]["robot_exception_id"]
        == robot_exception.id
    )
    assert (
        captured_invocation["kwargs"]["task_name"]
        == valid_recovery_payload["task_name"]
    )
    assert (
        captured_invocation["kwargs"]["platform"] == valid_recovery_payload["platform"]
    )
    assert captured_invocation["kwargs"]["os"] == valid_recovery_payload["os"]
    assert (
        captured_invocation["kwargs"]["variables"]
        == valid_recovery_payload["variables"]
    )
    assert "graph_dot" in captured_invocation["kwargs"]
    assert "A1" in captured_invocation["kwargs"]["graph_dot"]
    assert "G1" in captured_invocation["kwargs"]["graph_dot"]
    assert set(captured_invocation["kwargs"].keys()) == {
        "task_name",
        "platform",
        "os",
        "variables",
        "graph_dot",
    }


def test_recovery_ws_ingest_rejects_invalid_v3_payload(
    client: TestClient,
    valid_robot_key_raw: str,
    gateway_agent: Agent,  # pyright: ignore[reportUnusedParameter]
):
    headers = {"X-ROBOT-KEY": valid_robot_key_raw}
    with client.websocket_connect(
        "/recovery/robot_exception/ws", headers=headers
    ) as ws:
        ws.send_json({"task_name": "missing-graph"})
        message = ws.receive_json()

    assert message["type"] == "error"
    assert message["code"] == "INVALID_RECOVERY_PAYLOAD"


def test_recovery_ws_visual_dependent_payload_returns_not_implemented_error(
    client: TestClient,
    valid_robot_key_raw: str,
    gateway_agent: Agent,  # pyright: ignore[reportUnusedParameter]
):
    payload = {
        "task_name": "Visual Case",
        "platform": "uipath",
        "os": "windows",
        "variables": {},
        "activities": {
            "nodes": [
                {
                    "id": "A1",
                    "node_type": "activity",
                    "attributes": {
                        "state": "errored",
                        "has_visual_ref": True,
                        "selector_type": "coords",
                    },
                }
            ],
            "edges": [],
        },
    }

    headers = {"X-ROBOT-KEY": valid_robot_key_raw}
    with client.websocket_connect(
        "/recovery/robot_exception/ws", headers=headers
    ) as ws:
        ws.send_json(payload)
        message = ws.receive_json()

    assert message["type"] == "error"
    assert message["code"] == "VISUAL_PIPELINE_NOT_IMPLEMENTED"
