from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.auth.models import User
from database.logging.models import AgentTrace, GUITrace, RobotException
from tests.unit.shared import mock_s3
from tests.unit.shared.auth_helpers import make_auth_headers


def test_logging_agent_traces_requires_auth(client: TestClient):
    response = client.get("/logging/agent_traces")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_logging_agent_traces_allows_authenticated_user(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/agent_traces", headers=headers)
    assert response.status_code == status.HTTP_200_OK


def test_logging_robot_exceptions_requires_auth(client: TestClient):
    response = client.get("/logging/robot_exceptions")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_logging_robot_exceptions_allows_authenticated_user(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/robot_exceptions", headers=headers)
    assert response.status_code == status.HTTP_200_OK


def test_logging_agent_traces_lists_existing_traces(
    session: Session, mock_user: User, mock_agent, client: TestClient
):
    trace = AgentTrace(agent_id=mock_agent.id, inputs={})
    session.add(trace)
    session.commit()
    session.refresh(trace)

    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/agent_traces", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    got_ids = {item["id"] for item in payload}
    assert str(trace.id) in got_ids


def test_logging_get_agent_trace_returns_404_for_missing_id(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        "/logging/agent_traces/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_get_agent_trace_returns_trace(
    session: Session, mock_user: User, mock_agent, client: TestClient
):
    trace = AgentTrace(agent_id=mock_agent.id, inputs={})
    session.add(trace)
    session.commit()
    session.refresh(trace)

    headers = make_auth_headers(mock_user, session)
    response = client.get(f"/logging/agent_traces/{trace.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(trace.id)


def test_logging_delete_agent_trace_deletes_trace(
    session: Session, mock_user: User, mock_agent, client: TestClient
):
    trace = AgentTrace(agent_id=mock_agent.id, inputs={})
    session.add(trace)
    session.commit()
    session.refresh(trace)

    headers = make_auth_headers(mock_user, session)
    response = client.delete(f"/logging/agent_traces/{trace.id}", headers=headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT

    response = client.get(f"/logging/agent_traces/{trace.id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_robot_exceptions_lists_existing_exceptions(
    session: Session, mock_user: User, client: TestClient
):
    rex = RobotException(exception_details={"msg": "boom"}, robot_key_id=None)
    session.add(rex)
    session.commit()
    session.refresh(rex)

    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/robot_exceptions", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert any(item["id"] == str(rex.id) for item in response.json())


def test_logging_get_robot_exception_returns_404_for_missing_id(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        "/logging/robot_exceptions/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_get_robot_exception_returns_exception(
    session: Session, mock_user: User, client: TestClient
):
    rex = RobotException(exception_details={"msg": "boom"}, robot_key_id=None)
    session.add(rex)
    session.commit()
    session.refresh(rex)

    headers = make_auth_headers(mock_user, session)
    response = client.get(f"/logging/robot_exceptions/{rex.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(rex.id)


def test_logging_delete_robot_exception_deletes_exception(
    session: Session, mock_user: User, client: TestClient
):
    rex = RobotException(exception_details={"msg": "boom"}, robot_key_id=None)
    session.add(rex)
    session.commit()
    session.refresh(rex)

    headers = make_auth_headers(mock_user, session)
    response = client.delete(f"/logging/robot_exceptions/{rex.id}", headers=headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT

    response = client.get(f"/logging/robot_exceptions/{rex.id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_agent_trace_markdown_returns_markdown(
    session: Session, mock_user: User, mock_agent, client: TestClient
):
    trace = AgentTrace(agent_id=mock_agent.id, inputs={})
    session.add(trace)
    session.commit()
    session.refresh(trace)

    headers = make_auth_headers(mock_user, session)
    response = client.get(
        f"/logging/markdown/?agent_trace_id={trace.id}", headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Agent Trace" in response.text


def test_logging_agent_trace_markdown_returns_404_for_missing_id(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        "/logging/markdown/?agent_trace_id=00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_exception_ui_log_returns_zip(
    session: Session, mock_user: User, mock_agent, client: TestClient
):
    rex = RobotException(exception_details={"msg": "boom"}, robot_key_id=None)
    session.add(rex)
    session.commit()
    session.refresh(rex)

    trace = AgentTrace(agent_id=mock_agent.id, inputs={}, robot_exception_id=rex.id)
    session.add(trace)
    session.commit()
    session.refresh(trace)

    gui = GUITrace(
        agent_trace_id=trace.id,
        action_type="click",
        action_content={"content": "hi", "start_box": [0.1, 0.2]},
        success=True,
        screenshot_key="screenshot-1",
    )
    session.add(gui)
    session.commit()

    mock_s3.seed_bytes(
        key="screenshot-1",
        file_bytes=b"jpeg-bytes",
        content_type="image/jpeg",
    )

    headers = make_auth_headers(mock_user, session)
    response = client.get(f"/logging/ui_log/?exception_id={rex.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("application/zip")

    import zipfile
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(response.content)) as zipf:
        names = set(zipf.namelist())
        assert "ui_log.csv" in names
        assert "screenshots/screenshot-1.jpeg" in names


def test_logging_exception_ui_log_returns_404_for_missing_id(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        "/logging/ui_log/?exception_id=00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
