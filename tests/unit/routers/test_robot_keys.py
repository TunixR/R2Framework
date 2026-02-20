from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.auth.models import User
from tests.unit.shared.auth_helpers import make_auth_headers


def test_robot_keys_list_requires_auth(client: TestClient):
    response = client.get("/keys")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_robot_keys_get_requires_auth(client: TestClient):
    response = client.get("/keys/00000000-0000-0000-0000-000000000000")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_robot_keys_create_requires_admin(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.post(
        "/keys",
        json={"name": "Proc", "description": "Does stuff", "enabled": True},
        headers=headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_robot_keys_list_requires_user(
    session: Session, mock_user: User, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/keys")
    response_auth = client.get("/keys", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response_auth.status_code == status.HTTP_200_OK


def test_robot_keys_create_returns_plaintext_once_and_masks_in_list(
    session: Session, mock_admin: User, mock_user: User, client: TestClient
):
    admin_headers = make_auth_headers(mock_admin, session)
    create = client.post(
        "/keys",
        json={"name": "Proc", "description": "Does stuff", "enabled": True},
        headers=admin_headers,
    )
    assert create.status_code == status.HTTP_201_CREATED
    created = create.json()
    assert "key" in created
    assert isinstance(created["key"], str)
    assert len(created["key"]) >= 8

    key_id = created["id"]

    dev_headers = make_auth_headers(mock_user, session)
    listing = client.get("/keys", headers=dev_headers)
    assert listing.status_code == status.HTTP_200_OK
    keys = listing.json()
    obj = next(k for k in keys if k["id"] == key_id)
    assert obj["key"].startswith("****")
    assert obj["key"] == f"****{created['key'][-4:]}"


def test_robot_keys_delete_requires_admin(
    session: Session, mock_admin: User, mock_user: User, client: TestClient
):
    admin_headers = make_auth_headers(mock_admin, session)
    create = client.post(
        "/keys",
        json={"name": "Proc", "description": "Does stuff", "enabled": True},
        headers=admin_headers,
    )
    assert create.status_code == status.HTTP_201_CREATED
    key_id = create.json()["id"]

    dev_headers = make_auth_headers(mock_user, session)
    denied = client.delete(f"/keys/{key_id}", headers=dev_headers)
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    ok = client.delete(f"/keys/{key_id}", headers=admin_headers)
    assert ok.status_code == status.HTTP_204_NO_CONTENT


def test_robot_keys_toggle_requires_admin(
    session: Session, mock_admin: User, mock_user: User, client: TestClient
):
    admin_headers = make_auth_headers(mock_admin, session)
    create = client.post(
        "/keys",
        json={"name": "Proc", "description": "Does stuff", "enabled": True},
        headers=admin_headers,
    )
    assert create.status_code == status.HTTP_201_CREATED
    key_id = create.json()["id"]

    dev_headers = make_auth_headers(mock_user, session)
    denied = client.post(f"/keys/toggle/{key_id}", headers=dev_headers)
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    toggled = client.post(f"/keys/toggle/{key_id}", headers=admin_headers)
    assert toggled.status_code == status.HTTP_200_OK
    assert toggled.json()["enabled"] is False

    toggled_back = client.post(f"/keys/toggle/{key_id}", headers=admin_headers)
    assert toggled_back.status_code == status.HTTP_200_OK
    assert toggled_back.json()["enabled"] is True
