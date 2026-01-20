import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

import database.general as database
from database.logging.models import RobotException

router = APIRouter(prefix="/recovery")


@router.websocket("/robot_exception/ws")
async def handle_robot_exception(websocket: WebSocket):
    """
    Passes the exception to the robot exception handler for processing.
    """
    await websocket.accept()

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
        with Session(database.general_engine) as session:
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
                exception = RobotException(exception_details=data)
                session.add(exception)
                session.commit()
                session.refresh(exception)

                invocation_state = {
                    "websocket": websocket,
                    "robot_exception_id": exception.id,
                }
                response = await agent(invocation_state=invocation_state, **data)
                await websocket.send_json({"type": "done", "content": response})
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
    _, pending = await asyncio.wait({keep, work}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()

    return
