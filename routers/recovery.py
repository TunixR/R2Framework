import asyncio
import logging
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
from security.utils import robot_key_hash
from templates.common import TemplateModel
from templates.recovery_payload import RecoveryPayload

router = APIRouter(prefix="/recovery")
tracer = trace.get_tracer(__name__)

logger = logging.getLogger(__name__)


class RecoveryWsDomainError(Exception):
    def __init__(self, code: str, content: str):
        super().__init__(content)
        self.code = code
        self.content = content


class RecoveryWsErrorResponse(TemplateModel):
    type: str = "error"
    code: str
    content: str


def _get_valid_robot_key(
    websocket: WebSocket, session: database.SessionDep
) -> RobotKey | None:
    key_raw = websocket.headers.get("X-ROBOT-KEY")
    if not key_raw:
        return None

    key_hash = robot_key_hash(key_raw)
    robot_key = session.exec(
        select(RobotKey).where(RobotKey.key_hash == key_hash)
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
    robot_key = _get_valid_robot_key(websocket, session)
    if robot_key:
        await websocket.accept()
    else:
        raise WebSocketDisconnect(code=1008, reason="Invalid robot key")

    with tracer.start_as_current_span(
        "handle_robot_exception",
        attributes={
            "ws.path": "/robot_exception/ws",
            "ws.client": str(websocket.client),
        },
    ):
        logger.info("WebSocket connected")

        async def keep_alive():
            try:
                while True:
                    await asyncio.sleep(10)
                    await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect as e:
                logger.info("WebSocket disconnected during keep-alive.", exc_info=e)
                return

        async def handle_exception():
            data = (
                await websocket.receive_json()
            )  # Will only accept one exception per connection

            agent = _get_gateway_agent(session)

            if not agent:
                await websocket.send_json(
                    {
                        "type": "done",
                        "content": "No GatewayAgent found in the database.",
                    }
                )
                await websocket.close()
                return

            try:
                recovery_context = _build_recovery_context_or_raise(data)
                exception = _persist_exception_with_context(
                    session, data, robot_key, recovery_context
                )
                response = await _invoke_gateway_agent(
                    agent, websocket, exception, recovery_context
                )
                await websocket.send_json(
                    {"type": "done", "content": response, "id": str(exception.id)}
                )
                await websocket.close()

                success = response.get("success", False)
                exception.infered_success = success
                session.add(exception)
                session.commit()
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected before completion.")
            except RecoveryWsDomainError as exc:
                await websocket.send_json(
                    RecoveryWsErrorResponse(
                        code=exc.code,
                        content=exc.content,
                    ).model_dump()
                )
                await websocket.close(code=1003, reason=exc.content)
            except Exception as e:
                logger.error(f"Error handling robot exception: {e}")
                await websocket.send_json({"type": "error", "content": str(e)})
                await websocket.close()

        keep = asyncio.create_task(keep_alive())
        work = asyncio.create_task(handle_exception())
        _, pending = await asyncio.wait(
            {keep, work}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            _ = task.cancel()

        return


@router.post("/report_result/{recovery_id}")
async def report_recovery_result(
    request: Request, recovery_id: str, session: database.SessionDep
):
    try:
        recovery_uuid = UUID(recovery_id)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid recovery ID format. Must be a UUID."
        )

    key_raw = request.headers.get("X-ROBOT-KEY")
    if not key_raw:
        raise HTTPException(status_code=401, detail="No robot key provided")

    key_hash = robot_key_hash(key_raw)
    robot_key = session.exec(
        select(RobotKey).where(RobotKey.key_hash == key_hash)
    ).first()
    if not robot_key or not robot_key.enabled:
        raise HTTPException(status_code=403, detail="Invalid robot key")

    body = await request.json()
    success = body.get("success", False)

    exception = session.get(RobotException, recovery_uuid)
    if not exception:
        raise HTTPException(status_code=404, detail="Recovery ID not found")

    exception.infered_success = success
    session.add(exception)
    session.commit()
    return Response(status_code=204)
