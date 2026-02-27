import asyncio
import logging
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
from sqlmodel import select

import database.general as database
from database.keys.models import RobotKey
from database.logging.models import RobotException
from security.utils import robot_key_hash

router = APIRouter(prefix="/recovery")
tracer = trace.get_tracer(__name__)


@router.websocket("/robot_exception/ws")
async def handle_robot_exception(websocket: WebSocket, session: database.SessionDep):
    """
    Passes the exception to the robot exception handler for processing.
    """
    key_raw = websocket.headers.get("X-ROBOT-KEY")
    if not key_raw:
        await websocket.close(code=1008)
        return

    key_hash = robot_key_hash(key_raw)
    robot_key = session.exec(
        select(RobotKey).where(RobotKey.key_hash == key_hash)
    ).first()
    if not robot_key or not robot_key.enabled:
        await websocket.send_json(
            {
                "type": "error",
                "content": "Invalid robot key",
            }
        )
        await websocket.close(code=1008)
        return

    await websocket.accept()

    with tracer.start_as_current_span(
        "handle_robot_exception",
        attributes={
            "ws.path": "/robot_exception/ws",
            "ws.client": str(websocket.client),
        },
    ):

        async def keep_alive():
            try:
                while True:
                    await asyncio.sleep(10)
                    await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                return

        async def handle_exception():
            data = (
                await websocket.receive_json()
            )  # Will only accept one exception per connection

            # Grab the gatewayagent from db
            agent = session.exec(
                select(database.Agent).where(
                    database.Agent.type == database.AgentType.GatewayAgent
                )
            ).first()

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
                exception = RobotException(
                    exception_details=data,
                    robot_key_id=robot_key.id,
                )
                session.add(exception)
                session.commit()
                session.refresh(exception)

                invocation_state = {
                    "websocket": websocket,
                    "robot_exception_id": exception.id,
                }
                response = await agent(invocation_state=invocation_state, **data)
                await websocket.send_json(
                    {"type": "done", "content": response, "id": str(exception.id)}
                )
                await websocket.close()

                success = response.get("success", False)
                exception.infered_success = success
                session.add(exception)
                session.commit()
            except WebSocketDisconnect as _:
                logging.info("WebSocket disconnected before completion.")
            except Exception as e:
                logging.error(f"Error handling robot exception: {e}")
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
