import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from opentelemetry import trace
from pydantic import ValidationError
from sqlmodel import select

import database.general as database
from database.agents.models import Agent, AgentType
from database.keys.models import RobotKey
from database.logging.models import RecoveryContext, RobotException
from observability import attributes as attrs
from observability.instrumentation import recovery as telemetry
from security.utils import robot_key_hash
from templates.common import TemplateModel
from templates.recovery_payload import RecoveryPayload

router = APIRouter(prefix="/recovery")
tracer = trace.get_tracer(__name__)


ROBOT_KEY_HEADER = "X-ROBOT-KEY"


class RecoveryWsDomainError(Exception):
    def __init__(self, code: str, content: str):
        super().__init__(content)
        self.code = code
        self.content = content


class RecoveryWsErrorResponse(TemplateModel):
    type: str = "error"
    code: str
    content: str


def find_enabled_robot_key(
    session: database.SessionDep, key_raw: str | None
) -> RobotKey | None:
    """Return the enabled robot key matching a raw key, if any."""
    if not key_raw:
        return None

    robot_key = session.exec(
        select(RobotKey).where(RobotKey.key_hash == robot_key_hash(key_raw))
    ).first()
    if not robot_key or not robot_key.enabled:
        return None

    return robot_key


def _get_gateway_agent(session: database.SessionDep):
    return session.exec(
        select(database.Agent).where(database.Agent.type == AgentType.GatewayAgent)
    ).first()


def _build_recovery_context_or_raise(data: dict[str, Any]):
    try:
        payload = RecoveryPayload.model_validate(data)
        return RecoveryContext.from_payload(payload=payload)
    except ValidationError as exc:
        raise RecoveryWsDomainError(
            code="INVALID_RECOVERY_PAYLOAD",
            content=str(exc),
        ) from exc


def _persist_exception_with_context(
    session: database.SessionDep,
    data: dict[str, Any],
    robot_key: RobotKey,
    recovery_context: RecoveryContext,
):
    exception = RobotException(
        exception_details=data,
        robot_key_id=robot_key.id,
    )
    exception.recovery_context = recovery_context
    session.add(exception)
    session.commit()
    session.refresh(exception)
    return exception


async def _invoke_gateway_agent(
    agent: Agent,
    websocket: WebSocket,
    exception: RobotException,
    recovery_context: RecoveryContext,
):
    invocation_state = {
        "websocket": websocket,
        "robot_exception_id": exception.id,
    }

    ui_log = [
        {
            "case_id": entry.case_id,
            "activity_id": entry.activity_id,
            "activity_name": entry.activity_name,
            "event_id": entry.event_id,
            "event_name": entry.event_name,
            "action_type": entry.action_type,
            "application": entry.application,
            "input": entry.input,
            "ui_element_target": entry.ui_element_target,
            "ui_group": entry.ui_group,
            "timestamp": entry.timestamp,
            "previous_state": entry.previous_state,
            "current_state": entry.current_state,
        }
        for entry in recovery_context.ui_log_entries
    ]

    errored_act = None
    if recovery_context.errored_activity:
        act = recovery_context.errored_activity
        errored_act = {
            "case_id": act.case_id,
            "activity_id": act.activity_id,
            "event_id": act.event_id,
            "event_name": act.event_name,
            "action_type": act.action_type,
            "application": act.application,
            "input": act.input,
            "error_code": act.error_code,
            "error_description": act.error_description,
        }

    return await agent(
        invocation_state=invocation_state,
        task_name=recovery_context.task_name,
        platform=recovery_context.platform,
        os=recovery_context.os,
        variables=recovery_context.variables,
        ui_log=ui_log,
        errored_act=errored_act,
        model=recovery_context.model,
    )


@router.websocket("/robot_exception/ws")
async def handle_robot_exception(websocket: WebSocket, session: database.SessionDep):
    """
    Passes the exception to the robot exception handler for processing.
    """
    robot_key = find_enabled_robot_key(session, websocket.headers.get(ROBOT_KEY_HEADER))
    if not robot_key:
        telemetry.auth_failed(websocket.client)
        raise WebSocketDisconnect(code=1008, reason="Invalid robot key")

    await websocket.accept()

    with telemetry.recovery_turn(tracer, robot_key.id) as turn:

        async def keep_alive():
            try:
                while True:
                    await asyncio.sleep(10)
                    await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                return
            except Exception as exc:  # noqa: BLE001 - keep-alive must not crash the turn
                turn.keep_alive_failed(exc)
                return

        async def handle_exception():
            # Will only accept one exception per connection. Read the raw text
            # so the payload size is known without re-serializing it.
            raw = await websocket.receive_text()
            data = json.loads(raw)
            turn.payload_received(raw, data)

            agent = _get_gateway_agent(session)

            if not agent:
                turn.no_gateway_agent()
                await websocket.send_json(
                    {
                        "type": "done",
                        "content": "No GatewayAgent found in the database.",
                    }
                )
                await websocket.close()
                return

            turn.agent_selected(agent.id)

            try:
                recovery_context = _build_recovery_context_or_raise(data)
                turn.context_built(recovery_context)

                with turn.persisting():
                    exception = _persist_exception_with_context(
                        session, data, robot_key, recovery_context
                    )
                turn.persisted(exception.id)

                # Strands traces the agent run as a child span of this turn.
                response = await _invoke_gateway_agent(
                    agent, websocket, exception, recovery_context
                )
                success = bool(response.get("success", False))

                await websocket.send_json(
                    {"type": "done", "content": response, "id": str(exception.id)}
                )
                await websocket.close()

                exception.infered_success = success
                session.add(exception)
                session.commit()
                turn.completed(success)
            except WebSocketDisconnect:
                turn.client_disconnected()
            except RecoveryWsDomainError as exc:
                turn.invalid_payload(exc)
                await websocket.send_json(
                    RecoveryWsErrorResponse(
                        code=exc.code,
                        content=exc.content,
                    ).model_dump()
                )
                await websocket.close(code=1003, reason=exc.content)
            except Exception as exc:  # noqa: BLE001 - reported to the client and the span
                turn.failed(exc)
                await websocket.send_json(
                    {"type": "error", "content": "Internal server error"}
                )
                await websocket.close()

        keep = asyncio.create_task(keep_alive())
        work = asyncio.create_task(handle_exception())
        _, pending = await asyncio.wait(
            {keep, work}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            _ = task.cancel()


@router.post("/report_result/{recovery_id}")
async def report_recovery_result(
    request: Request, recovery_id: str, session: database.SessionDep
):
    # Rejections below are logged by the global HTTP exception handler.
    try:
        recovery_uuid = UUID(recovery_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid recovery ID format. Must be a UUID."
        ) from exc

    key_raw = request.headers.get(ROBOT_KEY_HEADER)
    if not key_raw:
        raise HTTPException(status_code=401, detail="No robot key provided")

    robot_key = find_enabled_robot_key(session, key_raw)
    if not robot_key:
        raise HTTPException(status_code=403, detail="Invalid robot key")

    body = await request.json()
    success = body.get("success", False)

    exception = session.get(RobotException, recovery_uuid)
    if not exception:
        raise HTTPException(status_code=404, detail="Recovery ID not found")

    exception.reported_success = success
    session.add(exception)
    session.commit()
    trace.get_current_span().set_attributes(
        {
            attrs.RECOVERY_ID: str(recovery_uuid),
            attrs.ROBOT_KEY_ID: str(robot_key.id),
            attrs.RECOVERY_SUCCESS: bool(success),
        }
    )
    return Response(status_code=204)
