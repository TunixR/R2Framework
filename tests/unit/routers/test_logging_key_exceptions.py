from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.auth.models import User
from database.keys.models import RobotKey
from database.logging.models import RobotException
from security.utils import robot_key_hash
from tests.unit.shared.auth_helpers import make_auth_headers


def _make_key(*, name: str, raw_key: str) -> RobotKey:
    return RobotKey(
        name=name,
        description=None,
        enabled=True,
        key_hash=robot_key_hash(raw_key),
        key_last4=raw_key[-4:],
    )


def test_logging_key_robot_exceptions_requires_auth(client: TestClient):
    response = client.get("/logging/key/00000000-0000-0000-0000-000000000000")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_logging_key_robot_exceptions_filters_by_robot_key_id(
    session: Session, mock_user: User, client: TestClient
):
    key_1 = _make_key(name="key-1", raw_key="key-1-plaintext-0001")
    key_2 = _make_key(name="key-2", raw_key="key-2-plaintext-0002")
    session.add(key_1)
    session.add(key_2)
    session.commit()
    session.refresh(key_1)
    session.refresh(key_2)

    rex_1a = RobotException(exception_details={"msg": "k1-a"}, robot_key_id=key_1.id)
    rex_1b = RobotException(exception_details={"msg": "k1-b"}, robot_key_id=key_1.id)
    rex_2 = RobotException(exception_details={"msg": "k2"}, robot_key_id=key_2.id)
    rex_none = RobotException(exception_details={"msg": "none"}, robot_key_id=None)
    session.add(rex_1a)
    session.add(rex_1b)
    session.add(rex_2)
    session.add(rex_none)
    session.commit()
    session.refresh(rex_1a)
    session.refresh(rex_1b)
    session.refresh(rex_2)
    session.refresh(rex_none)

    headers = make_auth_headers(mock_user, session)
    response = client.get(f"/logging/key/{key_1.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()

    got_ids = {item["id"] for item in payload}
    assert got_ids == {str(rex_1a.id), str(rex_1b.id)}
    assert all(item["robot_key_id"] == str(key_1.id) for item in payload)
