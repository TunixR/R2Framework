import uuid
from collections.abc import Callable

from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.agents.models import Agent, AgentCreate, AgentType, AgentUpdate
from database.auth.models import User
from database.provider.models import Router
from tests.unit.shared.auth_helpers import make_auth_headers


def make_agent_payload(
    router_id: uuid.UUID,
    input_type: Agent.InputType = Agent.InputType.TEXT,
) -> AgentCreate:
    return AgentCreate(
        name="My Agent",
        description="Test agent description",
        prompt="You are a helpful assistant.",
        input_type=input_type,
        enabled=True,
        router_id=router_id,
        type=AgentType.Agent,
    )


def test_agents_list_requires_auth(client: TestClient):
    response = client.get("/agents/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_agents_get_requires_auth(mock_agent: Agent, client: TestClient):
    response = client.get(f"/agents/{mock_agent.id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_agents_list_allows_any_user(
    session: Session, mock_user: User, mock_agent: Agent, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get("/agents/", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    assert any(a["id"] == str(mock_agent.id) for a in payload)


def test_agents_get_allows_any_user(
    session: Session, mock_user: User, mock_agent: Agent, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.get(f"/agents/{mock_agent.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(mock_agent.id)


def test_agents_get_not_found(session: Session, mock_user: User, client: TestClient):
    headers = make_auth_headers(mock_user, session)
    missing_id = uuid.uuid4()
    response = client.get(f"/agents/{missing_id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_agents_create_requires_admin(
    session: Session, mock_user: User, mock_router: Router, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.post(
        "/agents/",
        json=make_agent_payload(mock_router.id).model_dump(mode="json"),
        headers=headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_agents_update_requires_admin(
    session: Session, mock_user: User, mock_agent: Agent, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.patch(
        f"/agents/{mock_agent.id}",
        json=AgentUpdate(description="new description").model_dump(exclude_unset=True),
        headers=headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_agents_delete_requires_admin(
    session: Session, mock_user: User, mock_agent: Agent, client: TestClient
):
    headers = make_auth_headers(mock_user, session)
    response = client.delete(f"/agents/{mock_agent.id}", headers=headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_agents_admin_create_update_delete(
    session: Session,
    mock_admin: User,
    mock_router: Router,
    client: TestClient,
):
    headers = make_auth_headers(mock_admin, session)

    # Create
    create_response = client.post(
        "/agents/",
        json=make_agent_payload(mock_router.id).model_dump(mode="json"),
        headers=headers,
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    created = create_response.json()
    agent_id = created["id"]

    # Update
    update_response = client.patch(
        f"/agents/{agent_id}",
        json=AgentUpdate(description="updated").model_dump(exclude_unset=True),
        headers=headers,
    )
    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["description"] == "updated"

    # Delete
    delete_response = client.delete(f"/agents/{agent_id}", headers=headers)
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    assert session.get(Agent, uuid.UUID(agent_id)) is None


##############################
# -- Router capability alignment
##############################


def test_agents_create_rejects_missing_router(
    session: Session,
    mock_admin: User,
    client: TestClient,
):
    headers = make_auth_headers(mock_admin, session)
    payload = make_agent_payload(uuid.uuid4())

    response = client.post(
        "/agents/", json=payload.model_dump(mode="json"), headers=headers
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_agents_update_rejects_missing_router(
    session: Session,
    mock_admin: User,
    mock_agent: Agent,
    client: TestClient,
):
    headers = make_auth_headers(mock_admin, session)

    response = client.patch(
        f"/agents/{mock_agent.id}",
        json={"router_id": str(uuid.uuid4())},
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_agents_create_rejects_router_missing_required_capability(
    session: Session,
    mock_admin: User,
    client: TestClient,
    make_router: Callable[..., Router],
):
    router = make_router()
    headers = make_auth_headers(mock_admin, session)
    payload = make_agent_payload(router.id, Agent.InputType.IMAGETEXT)

    response = client.post(
        "/agents/", json=payload.model_dump(mode="json"), headers=headers
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "VISION" in response.json()["detail"]


def test_agents_create_allows_vision_agent_on_vision_router(
    session: Session,
    mock_admin: User,
    client: TestClient,
    mock_vision_router: Router,
):
    headers = make_auth_headers(mock_admin, session)
    payload = make_agent_payload(
        mock_vision_router.id,
        Agent.InputType.IMAGETEXT,
    )

    response = client.post(
        "/agents/", json=payload.model_dump(mode="json"), headers=headers
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["input_type"] == Agent.InputType.IMAGETEXT.value


def test_agents_update_rejects_input_type_not_supported_by_router(
    session: Session,
    mock_admin: User,
    client: TestClient,
    make_agent: Callable[..., Agent],
    make_router: Callable[..., Router],
):
    router = make_router()
    agent = make_agent(router=router)
    headers = make_auth_headers(mock_admin, session)

    response = client.patch(
        f"/agents/{agent.id}",
        json={"input_type": Agent.InputType.IMAGETEXT.value},
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "VISION" in response.json()["detail"]


def test_agents_update_rejects_router_missing_required_capability(
    session: Session,
    mock_admin: User,
    client: TestClient,
    make_agent: Callable[..., Agent],
    make_router: Callable[..., Router],
    mock_vision_router: Router,
):
    text_router = make_router()
    agent = make_agent(
        router=mock_vision_router,
        input_type=Agent.InputType.IMAGETEXT,
    )
    headers = make_auth_headers(mock_admin, session)

    response = client.patch(
        f"/agents/{agent.id}",
        json={"router_id": str(text_router.id)},
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "VISION" in response.json()["detail"]


def test_agents_update_allows_compatible_router(
    session: Session,
    mock_admin: User,
    client: TestClient,
    make_agent: Callable[..., Agent],
    make_router: Callable[..., Router],
):
    first_router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION]
    )
    second_router = make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION]
    )
    agent = make_agent(
        router=first_router,
        input_type=Agent.InputType.IMAGETEXT,
    )
    headers = make_auth_headers(mock_admin, session)

    response = client.patch(
        f"/agents/{agent.id}",
        json={"router_id": str(second_router.id)},
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["router_id"] == str(second_router.id)
