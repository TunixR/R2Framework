from __future__ import annotations

import secrets
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from database.auth.models import User
from database.general import SessionDep
from database.keys.models import (
    RobotKey,
    RobotKeyCreate,
    RobotKeyCreated,
    RobotKeyPublic,
)
from middlewares.auth import get_current_user, require_admin
from security.utils import robot_key_hash

router = APIRouter(prefix="/keys", tags=["Keys"])


@router.get("", response_model=Sequence[RobotKeyPublic], summary="List RobotKeys")
def list_robot_keys(
    session: SessionDep,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> Sequence[RobotKeyPublic]:
    keys = session.exec(select(RobotKey)).all()
    return [
        RobotKeyPublic(
            id=k.id,
            name=k.name,
            description=k.description,
            enabled=k.enabled,
            key=f"****{k.key_last4}",
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.get("/{key_id}", response_model=RobotKeyPublic, summary="Get RobotKey by ID")
def get_robot_key(
    key_id: UUID,
    session: SessionDep,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> RobotKeyPublic:
    key = session.get(RobotKey, key_id)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
        )
    return RobotKeyPublic(
        id=key.id,
        name=key.name,
        description=key.description,
        enabled=key.enabled,
        key=f"****{key.key_last4}",
        created_at=key.created_at,
    )


@router.post(
    "",
    response_model=RobotKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create RobotKey",
)
def create_robot_key(
    payload: RobotKeyCreate,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> RobotKeyCreated:
    plaintext_key = secrets.token_urlsafe(24)
    key = RobotKey(
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
        key_hash=robot_key_hash(plaintext_key),
        key_last4=plaintext_key[-4:],
    )

    session.add(key)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create key: {str(e)}",
        )
    session.refresh(key)

    return RobotKeyCreated(
        id=key.id,
        name=key.name,
        description=key.description,
        enabled=key.enabled,
        key=plaintext_key,
        created_at=key.created_at,
    )


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete RobotKey",
)
def delete_robot_key(
    key_id: UUID,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> None:
    key = session.get(RobotKey, key_id)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
        )
    session.delete(key)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete key: {str(e)}",
        )
    return


@router.post(
    "/toggle/{key_id}",
    response_model=RobotKeyPublic,
    summary="Toggle RobotKey enabled",
)
def toggle_robot_key(
    key_id: UUID,
    session: SessionDep,
    _current_user: Annotated[User, Depends(require_admin)],
) -> RobotKeyPublic:
    key = session.get(RobotKey, key_id)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
        )

    key.enabled = not key.enabled
    session.add(key)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to toggle key: {str(e)}",
        )
    session.refresh(key)

    return RobotKeyPublic(
        id=key.id,
        name=key.name,
        description=key.description,
        enabled=key.enabled,
        key=f"****{key.key_last4}",
        created_at=key.created_at,
    )
