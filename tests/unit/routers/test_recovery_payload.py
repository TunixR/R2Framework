from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from database.agents.models import Agent
from database.logging.models import RecoveryContext, RobotException
from templates.recovery_payload import RecoveryPayload


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
    captured_from_payload: dict[str, Any] = {}

    original_from_payload = RecoveryContext.from_payload

    def _spy_from_payload(cls, *, payload):  # pyright: ignore[reportMissingParameterType,reportUnusedParameter]
        captured_from_payload["payload"] = payload
        return original_from_payload(payload=payload)

    monkeypatch.setattr(
        RecoveryContext,
        "from_payload",
        classmethod(_spy_from_payload),
        raising=True,
    )

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
    assert recovery_context.model == valid_recovery_payload["model"]
    assert len(recovery_context.ui_log_entries) == 1
    assert recovery_context.ui_log_entries[0].activity_id is None
    assert recovery_context.ui_log_entries[0].event_name == "Type invoice id"
    assert recovery_context.errored_activity is not None
    assert recovery_context.errored_activity.activity_id is None
    assert recovery_context.errored_activity.event_name is None
    assert recovery_context.errored_activity.error_code == "E500"

    assert isinstance(captured_from_payload["payload"], RecoveryPayload)
    assert captured_from_payload["payload"].model_dump() == valid_recovery_payload

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
    # Check that ui_log uses v2 field names with normalized ids
    ui_log = captured_invocation["kwargs"]["ui_log"]
    assert len(ui_log) == 1
    assert ui_log[0]["activity_id"] is None  # fixture has activity_id as None
    assert ui_log[0]["event_name"] == "Type invoice id"
    assert ui_log[0]["case_id"] == valid_recovery_payload["ui_log"][0]["case_id"]
    assert ui_log[0]["event_id"] == valid_recovery_payload["ui_log"][0]["event_id"]
    # Check that all id fields are strings
    assert isinstance(ui_log[0]["case_id"], str)
    assert isinstance(ui_log[0]["event_id"], str)

    # Check that errored_act uses v2 field names with normalized ids
    errored_act = captured_invocation["kwargs"]["errored_act"]
    assert errored_act["activity_id"] is None  # fixture has activity_id as None
    assert errored_act["event_name"] is None  # fixture has event_name as None
    assert errored_act["case_id"] == valid_recovery_payload["errored_act"]["case_id"]
    assert errored_act["event_id"] == valid_recovery_payload["errored_act"]["event_id"]
    # Check that all id fields are strings
    assert isinstance(errored_act["case_id"], str)
    assert isinstance(errored_act["event_id"], str)

    assert captured_invocation["kwargs"]["model"] == valid_recovery_payload["model"]
    assert set(captured_invocation["kwargs"].keys()) == {
        "task_name",
        "platform",
        "os",
        "variables",
        "ui_log",
        "errored_act",
        "model",
    }


def test_recovery_ws_ingest_rejects_invalid_payload(
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
