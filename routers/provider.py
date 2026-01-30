from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlmodel import Field, SQLModel, select

from database.general import SessionDep
from database.provider.models import Router, RouterPublic

router = APIRouter(prefix="/provider", tags=["Provider"])


class RouterCreate(SQLModel):
    api_key: str = Field(description="API key for accessing the router service.")
    model_name: str = Field(description="Name of the model used by the router.")
    api_endpoint: str = Field(description="API endpoint of the provider.")
    provider_type: Router.Provider = Field(
        default=Router.Provider.OPENAI,
        description="The provider type backing this router.",
    )


class RouterUpdate(SQLModel):
    api_key: str | None = Field(
        default=None, description="API key for accessing the router service."
    )
    model_name: str | None = Field(
        default=None, description="Name of the model used by the router."
    )
    api_endpoint: str | None = Field(
        default=None, description="API endpoint of the provider."
    )
    provider_type: Router.Provider | None = Field(
        default=None, description="The provider type backing this router."
    )


@router.get(
    "/", response_model=Sequence[RouterPublic], summary="List all provider routers"
)
def list_routers(session: SessionDep) -> Sequence[Router]:
    routers = session.exec(select(Router)).all()
    return routers


@router.get(
    "/{router_id}", response_model=RouterPublic, summary="Get provider router by ID"
)
def get_router(router_id: UUID, session: SessionDep) -> Router:
    router_obj = session.get(Router, router_id)
    if not router_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Router not found"
        )
    return router_obj


@router.post(
    "/",
    response_model=Router,
    status_code=status.HTTP_201_CREATED,
    summary="Create provider router",
)
def create_router(payload: RouterCreate, session: SessionDep) -> Router:
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
    return router_obj


@router.put("/{router_id}", response_model=Router, summary="Replace provider router")
def replace_router(
    router_id: UUID, payload: RouterCreate, session: SessionDep
) -> Router:
    router_obj = session.get(Router, router_id)
    if not router_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Router not found"
        )

    router_obj.api_key = payload.api_key
    router_obj.model_name = payload.model_name
    router_obj.api_endpoint = payload.api_endpoint
    router_obj.provider_type = payload.provider_type

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
    return router_obj


@router.patch("/{router_id}", response_model=Router, summary="Update provider router")
def update_router(
    router_id: UUID, payload: RouterUpdate, session: SessionDep
) -> Router:
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
    return router_obj


@router.delete(
    "/{router_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete provider router",
)
def delete_router(router_id: UUID, session: SessionDep) -> None:
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
