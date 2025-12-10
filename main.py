# Initializes the FastAPI application and includes the main entry point.
# It also sets up the database connection and includes the necessary routers.
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select
from strands.telemetry import StrandsTelemetry

import database.general as database
from database.logging.models import RobotException


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler to initialize and clean up the database connection.
    """
    strands_telemetry = StrandsTelemetry()
    strands_telemetry.setup_otlp_exporter()  # Send traces to OTLP endpoint
    strands_telemetry.setup_meter(
        enable_console_exporter=False, enable_otlp_exporter=True
    )  # Setup new meter provider and sets it as global

    logging.getLogger("strands").setLevel(logging.DEBUG)
    logging.basicConfig(
        format="%(levelname)s | %(name)s | %(message)s",
        filename="strands.log",
        filemode="a",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    await database.create_db_and_tables()
    yield
    await database.drop_db_and_tables()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Welcome to the FastAPI application!"}


@app.websocket("/robot_exception/ws")
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

            exception = RobotException(exception_details=data)
            session.add(exception)
            session.commit()
            session.refresh(exception)

            invocation_state = {
                "websocket": websocket,
                "robot_exception_id": exception.id,
            }
            try:
                response = await agent(invocation_state=invocation_state, **data)
                await websocket.send_json({"type": "done", "content": response})
                await websocket.close()
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
