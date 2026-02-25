import zipfile
from collections.abc import Sequence
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlmodel import select

from database.general import SessionDep
from database.logging.models import (
    AgentTrace,
    GUITrace,
    RobotException,
    ToolTrace,
)
from middlewares.auth import get_current_user
from s3.utils import S3Client

router = APIRouter(
    prefix="/logging",
    tags=["Logging"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/markdown/",
    description="Retrieve the markdown log for a given agent trace ID.",
    summary="Get Agent Trace Markdown Log",
    responses={
        404: {"description": "AgentTrace not found"},
        200: {"content": {"text/markdown": {}}},
    },
)
async def get_agent_trace_markdown(agent_trace_id: UUID, session: SessionDep):
    """
    Endpoint to retrieve the markdown log for a given agent trace ID.
    """
    agent_trace = session.exec(
        select(AgentTrace).where(AgentTrace.id == agent_trace_id)
    ).first()

    if not agent_trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AgentTrace with ID {agent_trace_id} not found.",
        )

    markdown_log = await agent_trace.get_makdown_log()
    return Response(content=markdown_log, media_type="text/markdown")


@router.get(
    "/ui_log/",
    description="Retrieve the UI log for a given robot exception ID, alongside screenshots",
    summary="Get Robot Exception UI Log",
    responses={
        404: {"description": "RobotException not found"},
        200: {"content": {"text/csv": {}}},
    },
)
async def get_exception_ui_log(exception_id: UUID, session: SessionDep):
    """
    Retrieve the UI log for a given robot exception ID.
    """
    robot_exception = session.exec(
        select(RobotException).where(RobotException.id == exception_id)
    ).first()

    if not robot_exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RobotException with ID {exception_id} not found.",
        )
    gui_traces = (
        session.exec(
            select(GUITrace)
            .join(AgentTrace)
            .where(AgentTrace.robot_exception_id == exception_id)
            .where(GUITrace.success)
        )
        .unique()
        .all()
    )

    ui_log = "timestamp,event_type,click_x,click_y,text,screenshot\n"
    screenshots = []

    for gui_trace in gui_traces:
        timestamp = gui_trace.finished_at.isoformat() if gui_trace.finished_at else ""
        event_type = gui_trace.action_type
        click_x = ""
        click_y = ""
        text = gui_trace.action_content.get("content", "")
        screenshot = f"{gui_trace.screenshot_key}.jpeg" or "not found"

        screenshots.append(gui_trace.screenshot_key)

        coords = gui_trace.action_content.get("start_box", [])
        if coords:
            # Relative coordinates [0,1]
            click_x = str(coords[0])
            click_y = str(coords[1])

        # Special cases
        if event_type.lower() == "scroll":
            direction = gui_trace.action_content.get("direction", "")
            event_type = f"scroll_{direction}"

        # Two events: start and end
        elif event_type.lower() == "drag" or event_type.lower() == "select":
            ui_log += f"{timestamp},{event_type}_start,{click_x},{click_y},{text},{screenshot}\n"
            end_coords = gui_trace.action_content.get("end_box", [])
            if end_coords:
                click_x = str(end_coords[0])
                click_y = str(end_coords[1])
            ui_log += f"{timestamp},{event_type}_end,{click_x},{click_y},{text},{screenshot}\n"
            continue

        elif event_type.lower() == "wait" or event_type.lower() == "finish":
            continue

        ui_log += f"{timestamp},{event_type},{click_x},{click_y},{text},{screenshot}\n"

    screenshots = await S3Client.bulk_download_bytes(screenshots)

    # Construct zip file in memory
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("ui_log.csv", data=ui_log)
        # Create screenshot folder
        zipf.mkdir("screenshots")
        for key, img_bytes in screenshots.items():
            zipf.writestr(f"screenshots/{key}.jpeg", data=img_bytes)

    return StreamingResponse(iter([buffer.getvalue()]), media_type="application/zip")


@router.get(
    "/agent_traces", response_model=Sequence[AgentTrace], summary="List AgentTraces"
)
def list_agent_traces(
    session: SessionDep,
) -> Sequence[AgentTrace]:
    return session.exec(select(AgentTrace)).unique().all()


@router.get(
    "/agent_traces/{trace_id}",
    response_model=AgentTrace,
    summary="Get AgentTrace by ID",
)
def get_agent_trace(
    trace_id: UUID,
    session: SessionDep,
) -> AgentTrace:
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
def delete_agent_trace(
    trace_id: UUID,
    session: SessionDep,
) -> None:
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
def list_gui_traces(
    session: SessionDep,
) -> Sequence[GUITrace]:
    return session.exec(select(GUITrace)).unique().all()


@router.get(
    "/gui_traces/{gui_trace_id}", response_model=GUITrace, summary="Get GUITrace by ID"
)
def get_gui_trace(
    gui_trace_id: UUID,
    session: SessionDep,
) -> GUITrace:
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
def delete_gui_trace(
    gui_trace_id: UUID,
    session: SessionDep,
) -> None:
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
def list_tool_traces(
    session: SessionDep,
) -> Sequence[ToolTrace]:
    return session.exec(select(ToolTrace)).unique().all()


@router.get(
    "/tool_traces/{tool_trace_id}",
    response_model=ToolTrace,
    summary="Get ToolTrace by ID",
)
def get_tool_trace(
    tool_trace_id: UUID,
    session: SessionDep,
) -> ToolTrace:
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
def delete_tool_trace(
    tool_trace_id: UUID,
    session: SessionDep,
) -> None:
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
    "/key/{key_id}",
    response_model=Sequence[RobotException],
    summary="List RobotExceptions by RobotKey",
)
def list_robot_exceptions_by_key(
    key_id: UUID,
    session: SessionDep,
) -> Sequence[RobotException]:
    return session.exec(
        select(RobotException).where(RobotException.robot_key_id == key_id)
    ).all()


@router.get(
    "/robot_exceptions/{exception_id}",
    response_model=RobotException,
    summary="Get RobotException by ID",
)
def get_robot_exception(
    exception_id: UUID,
    session: SessionDep,
) -> RobotException:
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
def delete_robot_exception(
    exception_id: UUID,
    session: SessionDep,
) -> None:
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
