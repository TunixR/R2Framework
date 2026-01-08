from fastapi import APIRouter, Response, status
from sqlmodel import Session, select

from database.general import general_engine
from database.logging.models import AgentTrace

router = APIRouter(prefix="/logging")


@router.get(
    "/markdown/",
    description="Retrieve the markdown log for a given agent trace ID.",
    summary="Get Agent Trace Markdown Log",
    responses={
        404: {"description": "AgentTrace not found"},
        200: {"content": {"text/markdown": {}}},
    },
    tags=["Logging"],
)
async def get_agent_trace_markdown(agent_trace_id: str):
    """
    Endpoint to retrieve the markdown log for a given agent trace ID.
    """

    with Session(general_engine) as session:
        agent_trace = session.exec(
            select(AgentTrace).where(AgentTrace.id == agent_trace_id)
        ).first()

        if not agent_trace:
            return Response(
                content=f"AgentTrace with ID {agent_trace_id} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        markdown_log = await agent_trace.get_makdown_log()
        return Response(content=markdown_log, media_type="text/plain")
