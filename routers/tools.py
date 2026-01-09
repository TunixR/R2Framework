from typing import Sequence
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from database.general import SessionDep
from database.tools.models import Tool

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get("/", response_model=Sequence[Tool], summary="List all tools")
def list_tools(session: SessionDep) -> Sequence[Tool]:
    tools = session.exec(select(Tool)).unique().all()
    return tools


@router.get("/{tool_id}", response_model=Tool, summary="Get tool by ID")
def get_tool(tool_id: UUID, session: SessionDep) -> Tool:
    tool = session.get(Tool, tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found"
        )
    return tool


@router.delete(
    "/{tool_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete tool"
)
def delete_tool(tool_id: UUID, session: SessionDep) -> None:
    tool = session.get(Tool, tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found"
        )
    session.delete(tool)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete tool: {str(e)}",
        )
    return
