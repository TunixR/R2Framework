from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

# NOTE:
# The actual Auth models are not clearly defined in the project at this time.
# This router is a placeholder that follows the existing router structure and
# provides CRUD endpoints which currently return HTTP 501 Not Implemented.
#
# Once the auth models (e.g., User, Role, Permission, etc.) are available in
# database.auth.models, replace the placeholder implementations with real logic:
#
# - Import your models (e.g., from database.auth.models import User, Role)
# - Use SessionDep from database.general for DB interactions
# - Implement select/get/add/commit semantics similar to other routers

router = APIRouter(prefix="/auth", tags=["Auth"])


# Users CRUD (placeholder)


@router.get("/users", summary="List all users")
def list_users() -> list[dict[str, Any]]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.get("/users/{user_id}", summary="Get user by ID")
def get_user(user_id: UUID) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
)
def create_user(payload: dict[str, Any]) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.put("/users/{user_id}", summary="Replace user")
def replace_user(user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.patch("/users/{user_id}", summary="Update user")
def update_user(user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.delete(
    "/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user"
)
def delete_user(user_id: UUID) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


# Roles CRUD (placeholder)


@router.get("/roles", summary="List all roles")
def list_roles() -> list[dict[str, Any]]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.get("/roles/{role_id}", summary="Get role by ID")
def get_role(role_id: UUID) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.post(
    "/roles",
    status_code=status.HTTP_201_CREATED,
    summary="Create role",
)
def create_role(payload: dict[str, Any]) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.put("/roles/{role_id}", summary="Replace role")
def replace_role(role_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.patch("/roles/{role_id}", summary="Update role")
def update_role(role_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )


@router.delete(
    "/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete role"
)
def delete_role(role_id: UUID) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth models not yet defined. Implement once models are available.",
    )
