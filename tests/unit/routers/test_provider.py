from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.auth.models import User
from database.provider.models import Router, RouterCreate, RouterPublic, RouterUpdate
from tests.unit.shared.auth_helpers import make_auth_headers


def make_router_create() -> RouterCreate:
    return RouterCreate(
        api_key="super-secret",
        model_name="gpt-4o-mini",
        api_endpoint="https://example.test/v1",
        provider_type=Router.Provider.OPENAI,
    )


def persist_router(session: Session) -> Router:
    router_obj = Router(**make_router_create().model_dump())
    session.add(router_obj)
    session.commit()
    session.refresh(router_obj)
    return router_obj


##############################
# -- Permissions
##############################


def test_router_create_requires_admin(
    session: Session, mock_user: User, client: TestClient
):
    payload = make_router_create()
    headers = make_auth_headers(mock_user, session)

    response = client.post("/provider/", json=payload.model_dump(), headers=headers)

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_router_update_requires_admin(
    session: Session, mock_user: User, client: TestClient
):
    router_obj = persist_router(session)
    payload = RouterUpdate(model_name="different")
    headers = make_auth_headers(mock_user, session)

    response = client.patch(
        f"/provider/{router_obj.id}",
        json=payload.model_dump(exclude_unset=True),
        headers=headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_router_replace_requires_admin(
    session: Session, mock_user: User, client: TestClient
):
    router_obj = persist_router(session)
    payload = make_router_create()
    headers = make_auth_headers(mock_user, session)

    response = client.put(
        f"/provider/{router_obj.id}",
        json=payload.model_dump(exclude_unset=True),
        headers=headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_router_delete_requires_admin(
    session: Session, mock_user: User, client: TestClient
):
    router_obj = persist_router(session)
    headers = make_auth_headers(mock_user, session)

    response = client.delete(f"/provider/{router_obj.id}", headers=headers)

    assert response.status_code == status.HTTP_403_FORBIDDEN


##############################
# -- Security + Happy path
##############################


def test_router_get_returns_public_fields(session: Session):
    router_obj = persist_router(session)
    public = RouterPublic.model_validate(router_obj)

    assert public.id == router_obj.id
    assert not hasattr(public, "api_key")


def test_router_admin_update_does_not_leak_api_key(
    session: Session, mock_admin: User, client: TestClient
):
    router_obj = persist_router(session)
    headers = make_auth_headers(mock_admin, session)

    response = client.patch(
        f"/provider/{router_obj.id}",
        json=RouterUpdate(model_name="new-model").model_dump(exclude_unset=True),
        headers=headers,
    )
    obj = RouterPublic.model_validate_json(response.content)

    assert obj.model_name == "new-model"
    assert not hasattr(obj, "api_key")


def test_router_admin_create_does_not_leak_api_key(
    session: Session, mock_admin: User, client: TestClient
):
    headers = make_auth_headers(mock_admin, session)
    response = client.post(
        "/provider/", json=make_router_create().model_dump(), headers=headers
    )
    obj = RouterPublic.model_validate_json(response.content)

    assert response.status_code == status.HTTP_201_CREATED
    assert not hasattr(obj, "api_key")


##############################
# -- More happy path
##############################


def test_router_admin_delete_removes_router(
    session: Session, mock_admin: User, client: TestClient
):
    router_obj = persist_router(session)
    router_id = router_obj.id
    headers = make_auth_headers(mock_admin, session)

    response = client.delete(f"/provider/{router_id}", headers=headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert session.get(Router, router_id) is None


def test_router_admin_replace_replaces(
    session: Session, mock_admin: User, client: TestClient
):
    router_obj = persist_router(session)
    before = router_obj.updated_at
    headers = make_auth_headers(mock_admin, session)
    new_router = RouterCreate(
        api_key="another-secret",
        model_name="gpt-4o",
        api_endpoint="https://example.test/v2",
        provider_type=Router.Provider.OPENROUTER,
    )

    response = client.put(
        f"/provider/{router_obj.id}",
        json=new_router.model_dump(),
        headers=headers,
    )
    obj = RouterPublic.model_validate_json(response.content)

    assert obj.updated_at >= before
    assert obj.model_name == "gpt-4o"
    assert obj.api_endpoint == "https://example.test/v2"
    assert obj.provider_type == Router.Provider.OPENROUTER


def test_router_admin_patch_patches(
    session: Session, mock_admin: User, client: TestClient
):
    router_obj = persist_router(session)
    before = router_obj.updated_at
    headers = make_auth_headers(mock_admin, session)

    response = client.patch(
        f"/provider/{router_obj.id}",
        json=RouterUpdate(api_endpoint="https://example.test/v2").model_dump(
            exclude_unset=True
        ),
        headers=headers,
    )
    obj = RouterPublic.model_validate_json(response.content)

    assert obj.updated_at >= before
    assert obj.api_endpoint == "https://example.test/v2"
    assert obj.model_name == router_obj.model_name  # Unchanged
    assert obj.provider_type == router_obj.provider_type  # Unchanged
