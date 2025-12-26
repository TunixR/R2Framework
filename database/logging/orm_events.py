from sqlalchemy import event
from sqlmodel import (
    Session,
    select,
)

from database.logging.models import SubAgentTrace


@event.listens_for(Session, "before_flush")
def _validate_sub_agent_traces(
    session: Session,
    _,
    _2,
) -> None:
    for obj in session.new:
        if not isinstance(obj, SubAgentTrace):
            continue

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
