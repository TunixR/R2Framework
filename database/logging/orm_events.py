from typing import Any

from sqlalchemy import Connection, event
from sqlmodel import (
    Session,
    select,
)

from database.logging.models import GUITrace, SubAgentTrace
from s3.utils import S3Client


@event.listens_for(SubAgentTrace, "before_insert")
@event.listens_for(SubAgentTrace, "before_update")
def _validate_sub_agent_trace(_, connection: Connection, target: SubAgentTrace) -> None:  # pyright: ignore[reportUnusedFunction]
    if target.parent_trace_id == target.child_trace_id:
        raise ValueError("A trace cannot be a sub-trace of itself.")

    session = Session(bind=connection)

    if session.exec(
        select(SubAgentTrace).where(
            SubAgentTrace.child_trace_id == target.child_trace_id
        )
    ).first():
        raise ValueError("One trace cannot have multiple parent traces.")

    if session.exec(
        select(SubAgentTrace).where(
            (SubAgentTrace.parent_trace_id == target.parent_trace_id)
            & (SubAgentTrace.child_trace_id == target.child_trace_id)
        )
    ).first():
        raise ValueError("This sub-trace relationship already exists.")

    if session.exec(
        select(SubAgentTrace).where(
            (SubAgentTrace.child_trace_id == target.parent_trace_id)
            & (SubAgentTrace.parent_trace_id == target.child_trace_id)
        )
    ).first():
        raise ValueError("Circular sub-trace relationships are not allowed.")


@event.listens_for(GUITrace, "before_delete")
async def _cascade_delete_gui_trace_screenshot(_, __: Any, target: GUITrace):  # pyright: ignore[reportUnusedFunction,reportUnusedParameter]
    if target.screenshot_key:
        await S3Client.delete_object(target.screenshot_key)
