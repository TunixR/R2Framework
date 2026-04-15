from __future__ import annotations

from typing import Any, Callable

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.auth.models import User
from database.logging.models import RecoveryContext, RobotException
from tests.unit.shared.auth_helpers import make_auth_headers


@pytest.mark.parametrize(
    "path",
    [
        "/logging/recovery_context/00000000-0000-0000-0000-000000000000",
        "/logging/recovery_context/00000000-0000-0000-0000-000000000000/dot",
    ],
)
def test_logging_recovery_context_endpoints_require_auth(
    client: TestClient,
    path: str,
):
    response = client.get(path)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_recovery_context_graph_json(
    session: Session,
    mock_user: User,
    client: TestClient,
    valid_recovery_payload: dict[str, Any],
    make_robot_exception: Callable[..., RobotException],
):
    robot_exception = make_robot_exception(exception_details={"message": "boom"})

    recovery_context = RecoveryContext.from_payload(payload=valid_recovery_payload)
    recovery_context.robot_exception_id = robot_exception.id
    session.add(recovery_context)
    session.commit()

    headers = make_auth_headers(mock_user, session)
    response = client.get(
        f"/logging/recovery_context/{robot_exception.id}",
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == recovery_context.to_payload()


def test_get_recovery_context_dot_export(
    session: Session,
    mock_user: User,
    client: TestClient,
    valid_recovery_payload: dict[str, Any],
    make_robot_exception: Callable[..., RobotException],
):
    robot_exception = make_robot_exception(exception_details={"message": "boom"})

    recovery_context = RecoveryContext.from_payload(payload=valid_recovery_payload)
    recovery_context.robot_exception_id = robot_exception.id
    session.add(recovery_context)
    session.commit()

    headers = make_auth_headers(mock_user, session)
    response = client.get(
        f"/logging/recovery_context/{robot_exception.id}/dot",
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == recovery_context.to_dot()


def test_get_recovery_context_returns_404_when_exception_missing(
    session: Session,
    mock_user: User,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        "/logging/recovery_context/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "RobotException not found"


def test_get_recovery_context_dot_returns_404_when_exception_missing(
    session: Session,
    mock_user: User,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        "/logging/recovery_context/00000000-0000-0000-0000-000000000000/dot",
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "RobotException not found"


def test_get_recovery_context_returns_404_when_context_missing(
    session: Session,
    mock_user: User,
    client: TestClient,
    make_robot_exception: Callable[..., RobotException],
):
    robot_exception = make_robot_exception(exception_details={"message": "boom"})

    headers = make_auth_headers(mock_user, session)
    response = client.get(
        f"/logging/recovery_context/{robot_exception.id}",
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "RecoveryContext not found"


def test_get_recovery_context_dot_returns_404_when_context_missing(
    session: Session,
    mock_user: User,
    client: TestClient,
    make_robot_exception: Callable[..., RobotException],
):
    robot_exception = make_robot_exception(exception_details={"message": "boom"})

    headers = make_auth_headers(mock_user, session)
    response = client.get(
        f"/logging/recovery_context/{robot_exception.id}/dot",
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "RecoveryContext not found"
