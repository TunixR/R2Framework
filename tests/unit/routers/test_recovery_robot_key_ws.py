from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.keys.models import RobotKey
from security.utils import robot_key_hash


def test_recovery_ws_requires_robot_key_header(client: TestClient):
    with pytest.raises(Exception):
        with client.websocket_connect("/recovery/robot_exception/ws"):
            pass


def test_recovery_ws_rejects_invalid_robot_key(client: TestClient):
    headers = [("X-ROBOT-KEY", "not-a-real-key")]
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/recovery/robot_exception/ws", headers=headers
        ) as ws:
            ws.send_json({"foo": "bar"})


def test_recovery_ws_rejects_disabled_robot_key(session: Session, client: TestClient):
    key_raw = "test-robot-key-0001"
    key = RobotKey(
        name="Disabled",
        description=None,
        enabled=False,
        key_hash=robot_key_hash(key_raw),
        key_last4=key_raw[-4:],
    )
    session.add(key)
    session.commit()

    headers = [("X-ROBOT-KEY", key_raw)]
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/recovery/robot_exception/ws", headers=headers
        ) as ws:
            ws.send_json({"foo": "bar"})
