import uuid

from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.auth.models import User
from database.tools.models import Tool
from tests.unit.shared.auth_helpers import make_auth_headers


def test_tools_list_requires_auth(client: TestClient):
    response = client.get("/tools/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_tools_get_requires_auth(client: TestClient):
    missing_id = uuid.uuid4()
    response = client.get(f"/tools/{missing_id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_tools_list_allows_any_user(
    session: Session, mock_user: User, mock_tool: Tool, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/tools/", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    assert any(t["id"] == str(mock_tool.id) for t in payload)


def test_tools_get_allows_any_user(
    session: Session, mock_user: User, mock_tool: Tool, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(f"/tools/{mock_tool.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(mock_tool.id)


def test_tools_get_not_found(session: Session, mock_user: User, client: TestClient):
    headers = make_auth_headers(mock_user, session)
    missing_id = uuid.uuid4()
    response = client.get(f"/tools/{missing_id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
