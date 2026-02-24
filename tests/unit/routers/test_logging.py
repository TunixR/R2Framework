from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.auth.models import User
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
