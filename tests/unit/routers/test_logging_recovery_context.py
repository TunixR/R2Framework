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
    ],
)
def test_logging_recovery_context_endpoints_require_auth(
    client: TestClient,
    path: str,
):
    response = client.get(path)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_recovery_context(
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
    data = response.json()

    # Verify v2 field names in response
    assert "ui_log" in data
    assert len(data["ui_log"]) == 1
    ui_log_entry = data["ui_log"][0]
    assert "activity_id" in ui_log_entry
    assert "event_name" in ui_log_entry
    assert "case_id" in ui_log_entry
    assert "event_id" in ui_log_entry
    # Verify old field names are not present
    assert "model_act_id" not in ui_log_entry
    # Verify new field names are present
    assert "activity_name" in ui_log_entry

    # Verify errored_act has v2 field names
    assert "errored_act" in data
    errored_act = data["errored_act"]
    assert "activity_id" in errored_act
    assert "event_name" in errored_act
    assert "case_id" in errored_act
    assert "event_id" in errored_act
    # Verify old field names are not present
    assert "model_act_id" not in errored_act
    # Verify new field names are present
    assert "activity_name" in errored_act

    # Verify id fields are strings
    assert isinstance(ui_log_entry["activity_id"], str | type(None))
    assert isinstance(ui_log_entry["case_id"], str)
    assert isinstance(ui_log_entry["event_id"], str)
    assert isinstance(errored_act["activity_id"], str | type(None))
    assert isinstance(errored_act["case_id"], str)
    assert isinstance(errored_act["event_id"], str)


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
