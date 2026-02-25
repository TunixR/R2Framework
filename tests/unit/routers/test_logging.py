from typing import Callable

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.agents.models import Agent
from database.auth.models import User
from database.logging.models import AgentTrace, GUITrace, RobotException, ToolTrace
from tests.unit.shared.auth_helpers import make_auth_headers
from tests.unit.shared.mock_s3 import MockS3Client


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


def test_logging_gui_traces_requires_auth(client: TestClient):
    response = client.get("/logging/gui_traces")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_logging_gui_traces_allows_authenticated_user(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/gui_traces", headers=headers)
    assert response.status_code == status.HTTP_200_OK


def test_logging_gui_traces_lists_existing_traces(
    session: Session,
    mock_user: User,
    mock_gui_trace: GUITrace,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/gui_traces", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    got_ids = {item["id"] for item in payload}
    assert str(mock_gui_trace.id) in got_ids


def test_logging_get_gui_trace_returns_404_for_missing_id(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        "/logging/gui_traces/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_get_gui_trace_returns_trace(
    session: Session,
    mock_user: User,
    mock_gui_trace: GUITrace,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(f"/logging/gui_traces/{mock_gui_trace.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(mock_gui_trace.id)


@pytest.mark.asyncio
async def test_logging_delete_gui_trace_deletes_trace(
    session: Session,
    mock_user: User,
    mock_agent_trace: AgentTrace,
    make_gui_trace: Callable[..., GUITrace],
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)

    # Check screenshot-1 exists in mock S3 before deletion
    key = await MockS3Client.upload_bytes(
        file_bytes=b"jpeg-bytes",
        content_type="image/jpeg",
    )

    mock_gui_trace = make_gui_trace(agent_trace=mock_agent_trace, screenshot_key=key)
    _ = await MockS3Client.download_bytes(key)

    response = client.delete(
        f"/logging/gui_traces/{mock_gui_trace.id}", headers=headers
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    with pytest.raises(KeyError):
        _ = await MockS3Client.download_bytes(key)

    response = client.get(f"/logging/gui_traces/{mock_gui_trace.id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_tool_traces_requires_auth(client: TestClient):
    response = client.get("/logging/tool_traces")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_logging_tool_traces_allows_authenticated_user(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/tool_traces", headers=headers)
    assert response.status_code == status.HTTP_200_OK


def test_logging_tool_traces_lists_existing_traces(
    session: Session,
    mock_user: User,
    mock_tool_trace: ToolTrace,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/tool_traces", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    got_ids = {item["id"] for item in payload}
    assert str(mock_tool_trace.id) in got_ids


def test_logging_get_tool_trace_returns_404_for_missing_id(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        "/logging/tool_traces/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_get_tool_trace_returns_trace(
    session: Session,
    mock_user: User,
    mock_tool_trace: ToolTrace,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(f"/logging/tool_traces/{mock_tool_trace.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(mock_tool_trace.id)


def test_logging_delete_tool_trace_deletes_trace(
    session: Session,
    mock_user: User,
    mock_tool_trace: ToolTrace,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.delete(
        f"/logging/tool_traces/{mock_tool_trace.id}", headers=headers
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    response = client.get(f"/logging/tool_traces/{mock_tool_trace.id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_agent_traces_lists_existing_traces(
    session: Session,
    mock_user: User,
    mock_agent_trace: AgentTrace,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/agent_traces", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    got_ids = {item["id"] for item in payload}
    assert str(mock_agent_trace.id) in got_ids


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
    session: Session,
    mock_user: User,
    mock_agent_trace: AgentTrace,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        f"/logging/agent_traces/{mock_agent_trace.id}", headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(mock_agent_trace.id)


def test_logging_delete_agent_trace_deletes_trace(
    session: Session,
    mock_user: User,
    mock_agent_trace: AgentTrace,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.delete(
        f"/logging/agent_traces/{mock_agent_trace.id}", headers=headers
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    response = client.get(
        f"/logging/agent_traces/{mock_agent_trace.id}", headers=headers
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_robot_exceptions_lists_existing_exceptions(
    session: Session,
    mock_user: User,
    mock_robot_exception: RobotException,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/logging/robot_exceptions", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert any(item["id"] == str(mock_robot_exception.id) for item in response.json())


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
    session: Session,
    mock_user: User,
    mock_robot_exception: RobotException,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        f"/logging/robot_exceptions/{mock_robot_exception.id}", headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(mock_robot_exception.id)


def test_logging_delete_robot_exception_deletes_exception(
    session: Session,
    mock_user: User,
    mock_robot_exception: RobotException,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.delete(
        f"/logging/robot_exceptions/{mock_robot_exception.id}", headers=headers
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    response = client.get(
        f"/logging/robot_exceptions/{mock_robot_exception.id}", headers=headers
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_logging_agent_trace_markdown_returns_markdown(
    session: Session,
    mock_user: User,
    mock_agent_trace: AgentTrace,
    client: TestClient,
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        f"/logging/markdown/?agent_trace_id={mock_agent_trace.id}", headers=headers
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


@pytest.mark.asyncio
async def test_logging_exception_ui_log_returns_zip(
    session: Session,
    mock_user: User,
    mock_agent: Agent,
    mock_robot_exception: RobotException,
    make_agent_trace: Callable[..., AgentTrace],
    make_gui_trace: Callable[..., GUITrace],
    client: TestClient,
):
    trace = make_agent_trace(
        agent=mock_agent, robot_exception_id=mock_robot_exception.id
    )

    key = await MockS3Client.upload_bytes(
        file_bytes=b"jpeg-bytes",
        content_type="image/jpeg",
    )

    _ = make_gui_trace(agent_trace=trace, screenshot_key=key)

    headers = make_auth_headers(mock_user, session)
    response = client.get(
        f"/logging/ui_log/?exception_id={mock_robot_exception.id}", headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("application/zip")

    import zipfile
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(response.content)) as zipf:
        names = set(zipf.namelist())
        assert "ui_log.csv" in names
        assert f"screenshots/{key}.jpeg" in names


def test_logging_exception_ui_log_returns_404_for_missing_id(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(
        "/logging/ui_log/?exception_id=00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
