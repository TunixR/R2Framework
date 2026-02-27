from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlmodel import Session

from database.keys.models import RobotKey
from database.logging.models import RobotException


def test_report_result_invalid_uuid_format(client: TestClient):
    response = client.post(
        "/recovery/report_result/not-a-uuid",
        headers={"X-ROBOT-KEY": "some-key"},
        json={"success": True},
    )
    assert response.status_code == 400
    assert "Invalid recovery ID format" in response.json()["detail"]


def test_report_result_missing_robot_key_header(client: TestClient):
    response = client.post(
        "/recovery/report_result/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


def test_report_result_invalid_robot_key(client: TestClient):
    response = client.post(
        "/recovery/report_result/00000000-0000-0000-0000-000000000001",
        headers={"X-ROBOT-KEY": "not-a-real-key"},
        json={"success": True},
    )
    assert response.status_code == 403


def test_report_result_disabled_robot_key(
    client: TestClient, make_robot_key: Callable[..., RobotKey]
):
    key_raw = "test-robot-key-report-disabled"
    _ = make_robot_key(name="Disabled", enabled=False, key_raw=key_raw)

    response = client.post(
        "/recovery/report_result/00000000-0000-0000-0000-000000000001",
        headers={"X-ROBOT-KEY": key_raw},
        json={"success": True},
    )
    assert response.status_code == 403


def test_report_result_not_found(
    client: TestClient, make_robot_key: Callable[..., RobotKey]
):
    key_raw = "test-robot-key-report-notfound"
    _ = make_robot_key(name="Valid", enabled=True, key_raw=key_raw)

    response = client.post(
        "/recovery/report_result/00000000-0000-0000-0000-000000000001",
        headers={"X-ROBOT-KEY": key_raw},
        json={"success": True},
    )
    assert response.status_code == 404
    assert "Recovery ID not found" in response.json()["detail"]


def test_report_result_updates_infered_success(
    session: Session,
    client: TestClient,
    make_robot_exception: Callable[..., RobotException],
    make_robot_key: Callable[..., RobotKey],
):
    key_raw = "test-robot-key-report-success"
    key = make_robot_key(name="Valid", enabled=True, key_raw=key_raw)

    exception = make_robot_exception(robot_key_id=key.id)

    response = client.post(
        f"/recovery/report_result/{exception.id}",
        headers={"X-ROBOT-KEY": key_raw},
        json={"success": True},
    )
    assert response.status_code == 204

    session.expire_all()
    updated = session.get(RobotException, exception.id)
    assert updated
    assert updated.infered_success is True


def test_report_result_updates_infered_success_false(
    session: Session,
    client: TestClient,
    make_robot_exception: Callable[..., RobotException],
    make_robot_key: Callable[..., RobotKey],
):
    key_raw = "test-robot-key-report-false"
    key = make_robot_key(name="Valid", enabled=True, key_raw=key_raw)

    exception = make_robot_exception(robot_key_id=key.id)

    response = client.post(
        f"/recovery/report_result/{exception.id}",
        headers={"X-ROBOT-KEY": key_raw},
        json={"success": False},
    )
    assert response.status_code == 204

    session.expire_all()
    updated = session.get(RobotException, exception.id)
    assert updated
    assert updated.infered_success is False
