from collections.abc import Sequence
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from database.auth.models import User
from database.general import SessionDep
from database.provider.models import (
    Router,
    RouterCreate,
    RouterPublic,
    RouterUpdate,
)
from middlewares.auth import get_current_user, require_admin

router = APIRouter(
    prefix="/provider", tags=["Provider"], dependencies=[Depends(get_current_user)]
)


@router.get(
    "/", response_model=Sequence[RouterPublic], summary="List all provider routers"
)
def list_routers(
    session: SessionDep,
) -> Sequence[RouterPublic]:
    routers = session.exec(select(Router)).all()
    return [RouterPublic.model_validate(r) for r in routers]


@router.get(
    "/{router_id}", response_model=RouterPublic, summary="Get provider router by ID"
)
def get_router(
    router_id: UUID,
    session: SessionDep,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> RouterPublic:
    router_obj = session.get(Router, router_id)
    if not router_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Router not found"
        )
    return RouterPublic.model_validate(router_obj)


@router.post(
    "/",
    response_model=RouterPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create provider router",
)
def create_router(
    payload: RouterCreate,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> RouterPublic:
    router_obj = Router(**payload.model_dump())
    session.add(router_obj)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create router: {str(e)}",
        )
    session.refresh(router_obj)
    return RouterPublic.model_validate(router_obj)


@router.put(
    "/{router_id}",
    response_model=RouterPublic,
    summary="Replace provider router",
)
def replace_router(
    router_id: UUID,
    payload: RouterCreate,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> RouterPublic:
    router_obj = session.get(Router, router_id)
    if not router_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Router not found"
        )

    router_obj.api_key = payload.api_key
    router_obj.model_name = payload.model_name
    router_obj.api_endpoint = payload.api_endpoint
    router_obj.provider_type = payload.provider_type
    router_obj.updated_at = datetime.now()

    try:
        session.add(router_obj)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update router: {str(e)}",
        )
    session.refresh(router_obj)
    return RouterPublic.model_validate(router_obj)


@router.patch(
    "/{router_id}",
    response_model=RouterPublic,
    summary="Update provider router",
)
def update_router(
    router_id: UUID,
    payload: RouterUpdate,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> RouterPublic:
    router_obj = session.get(Router, router_id)
    if not router_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Router not found"
        )

    if payload.api_key is not None:
        router_obj.api_key = payload.api_key
    if payload.model_name is not None:
        router_obj.model_name = payload.model_name
    if payload.api_endpoint is not None:
        router_obj.api_endpoint = payload.api_endpoint
    if payload.provider_type is not None:
        router_obj.provider_type = payload.provider_type

    router_obj.updated_at = datetime.now()

    try:
        session.add(router_obj)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update router: {str(e)}",
        )
    session.refresh(router_obj)
    return RouterPublic.model_validate(router_obj)


@router.delete(
    "/{router_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete provider router",
)
def delete_router(
    router_id: UUID,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> None:
    router_obj = session.get(Router, router_id)
    if not router_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Router not found"
        )

    session.delete(router_obj)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete router: {str(e)}",
        )
    return
