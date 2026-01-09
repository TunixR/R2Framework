from typing import Sequence
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlmodel import select

from database.general import SessionDep
from database.logging.models import AgentTrace, GUITrace, RobotException, ToolTrace

router = APIRouter(prefix="/logging", tags=["Logging"])


@router.get(
    "/markdown/",
    description="Retrieve the markdown log for a given agent trace ID.",
    summary="Get Agent Trace Markdown Log",
    responses={
        404: {"description": "AgentTrace not found"},
        200: {"content": {"text/markdown": {}}},
    },
)
async def get_agent_trace_markdown(agent_trace_id: str, session: SessionDep):
    """
    Endpoint to retrieve the markdown log for a given agent trace ID.
    """
    agent_trace = session.exec(
        select(AgentTrace).where(AgentTrace.id == agent_trace_id)
    ).first()

    if not agent_trace:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AgentTrace with ID {agent_trace_id} not found.",
        )

    markdown_log = await agent_trace.get_makdown_log()
    return Response(content=markdown_log, media_type="text/plain")


@router.get(
    "/agent_traces", response_model=Sequence[AgentTrace], summary="List AgentTraces"
)
def list_agent_traces(session: SessionDep) -> Sequence[AgentTrace]:
    return session.exec(select(AgentTrace)).unique().all()


@router.get(
    "/agent_traces/{trace_id}",
    response_model=AgentTrace,
    summary="Get AgentTrace by ID",
)
def get_agent_trace(trace_id: UUID, session: SessionDep) -> AgentTrace:
    trace = session.get(AgentTrace, trace_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AgentTrace not found"
        )
    return trace


@router.delete(
    "/agent_traces/{trace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete AgentTrace",
)
def delete_agent_trace(trace_id: UUID, session: SessionDep) -> None:
    trace = session.get(AgentTrace, trace_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AgentTrace not found"
        )
    session.delete(trace)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete AgentTrace: {e}",
        )
    return


@router.get("/gui_traces", response_model=Sequence[GUITrace], summary="List GUITraces")
def list_gui_traces(session: SessionDep) -> Sequence[GUITrace]:
    return session.exec(select(GUITrace)).all()


@router.get(
    "/gui_traces/{gui_trace_id}", response_model=GUITrace, summary="Get GUITrace by ID"
)
def get_gui_trace(gui_trace_id: UUID, session: SessionDep) -> GUITrace:
    gtrace = session.get(GUITrace, gui_trace_id)
    if not gtrace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="GUITrace not found"
        )
    return gtrace


@router.delete(
    "/gui_traces/{gui_trace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete GUITrace",
)
def delete_gui_trace(gui_trace_id: UUID, session: SessionDep) -> None:
    gtrace = session.get(GUITrace, gui_trace_id)
    if not gtrace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="GUITrace not found"
        )
    session.delete(gtrace)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete GUITrace: {e}",
        )
    return


@router.get(
    "/tool_traces", response_model=Sequence[ToolTrace], summary="List ToolTraces"
)
def list_tool_traces(session: SessionDep) -> Sequence[ToolTrace]:
    return session.exec(select(ToolTrace)).all()


@router.get(
    "/tool_traces/{tool_trace_id}",
    response_model=ToolTrace,
    summary="Get ToolTrace by ID",
)
def get_tool_trace(tool_trace_id: UUID, session: SessionDep) -> ToolTrace:
    ttrace = session.get(ToolTrace, tool_trace_id)
    if not ttrace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ToolTrace not found"
        )
    return ttrace


@router.delete(
    "/tool_traces/{tool_trace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete ToolTrace",
)
def delete_tool_trace(tool_trace_id: UUID, session: SessionDep) -> None:
    ttrace = session.get(ToolTrace, tool_trace_id)
    if not ttrace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ToolTrace not found"
        )
    session.delete(ttrace)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete ToolTrace: {e}",
        )
    return


@router.get(
    "/robot_exceptions",
    response_model=Sequence[RobotException],
    summary="List RobotExceptions",
)
def list_robot_exceptions(session: SessionDep) -> Sequence[RobotException]:
    return session.exec(select(RobotException)).all()


@router.get(
    "/robot_exceptions/{exception_id}",
    response_model=RobotException,
    summary="Get RobotException by ID",
)
def get_robot_exception(exception_id: UUID, session: SessionDep) -> RobotException:
    rex = session.get(RobotException, exception_id)
    if not rex:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="RobotException not found"
        )
    return rex


@router.delete(
    "/robot_exceptions/{exception_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete RobotException",
)
def delete_robot_exception(exception_id: UUID, session: SessionDep) -> None:
    rex = session.get(RobotException, exception_id)
    if not rex:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="RobotException not found"
        )
    session.delete(rex)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete RobotException: {e}",
        )
    return
