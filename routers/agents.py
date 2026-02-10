from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from database.auth.models import User
from database.agents.models import Agent, AgentCreate, AgentUpdate
from database.general import SessionDep
from middlewares.auth import get_current_user, require_admin

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("/", response_model=Sequence[Agent], summary="List all agents")
def list_agents(
    session: SessionDep,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> Sequence[Agent]:
    return session.exec(select(Agent)).unique().all()


@router.get("/{agent_id}", response_model=Agent, summary="Get agent by ID")
def get_agent(
    agent_id: UUID,
    session: SessionDep,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> Agent:
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return agent


@router.post(
    "/",
    response_model=Agent,
    status_code=status.HTTP_201_CREATED,
    summary="Create agent",
)
def create_agent(
    payload: AgentCreate,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> Agent:
    agent = Agent(**payload.model_dump())

    session.add(agent)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create agent: {str(e)}",
        )
    session.refresh(agent)
    return agent


@router.patch("/{agent_id}", response_model=Agent, summary="Update agent")
def update_agent(
    agent_id: UUID,
    payload: AgentUpdate,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> Agent:
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    for key, value in payload.model_dump(exclude_unset=True).items():
        try:
            setattr(agent, key, value)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to set field '{key}': {str(e)}",
            )

    try:
        session.add(agent)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update agent: {str(e)}",
        )
    session.refresh(agent)
    return agent


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete agent",
)
def delete_agent(
    agent_id: UUID,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> None:
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    session.delete(agent)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete agent: {str(e)}",
        )
    return
