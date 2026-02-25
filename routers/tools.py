from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from database.auth.models import User
from database.general import SessionDep
from database.tools.models import Tool
from middlewares.auth import get_current_user

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get("/", response_model=Sequence[Tool], summary="List all tools")
def list_tools(
    session: SessionDep,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> Sequence[Tool]:
    tools = session.exec(select(Tool)).unique().all()
    return tools


@router.get("/{tool_id}", response_model=Tool, summary="Get tool by ID")
def get_tool(
    tool_id: UUID,
    session: SessionDep,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> Tool:
    tool = session.get(Tool, tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found"
        )
    return tool
