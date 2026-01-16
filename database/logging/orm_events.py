from sqlalchemy import event
from sqlmodel import (
    Session,
    select,
)

from database.logging.models import GUITrace, SubAgentTrace
from s3.utils import S3Client


@event.listens_for(Session, "before_flush")
def _validate_sub_agent_trace(
    session: Session,
    _,
    _2,
) -> None:
    for obj in session.new:
        if obj.parent_trace_id == obj.child_trace_id:
            raise ValueError("A trace cannot be a sub-trace of itself.")

        if session.exec(
            select(SubAgentTrace).where(
                SubAgentTrace.child_trace_id == obj.child_trace_id
            )
        ).first():
            raise ValueError("One trace cannot have multiple parent traces.")

        if session.exec(
            select(SubAgentTrace).where(
                (SubAgentTrace.parent_trace_id == obj.parent_trace_id)
                & (SubAgentTrace.child_trace_id == obj.child_trace_id)
            )
        ).first():
            raise ValueError("This sub-trace relationship already exists.")

        if session.exec(
            select(SubAgentTrace).where(
                (SubAgentTrace.child_trace_id == obj.parent_trace_id)
                & (SubAgentTrace.parent_trace_id == obj.child_trace_id)
            )
        ).first():
            raise ValueError("Circular sub-trace relationships are not allowed.")


@event.listens_for(GUITrace, "before_delete")
async def _cascade_delete_gui_trace_screenshot(_, _2, target: GUITrace):
    if target.screenshot_key:
        await S3Client.delete_object(target.screenshot_key)
