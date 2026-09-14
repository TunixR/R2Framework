from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from opentelemetry import trace
from pydantic import BaseModel, ValidationError
from sqlmodel import select
from strands import Agent as StrandsAgent
from strands.models.openai import OpenAIModel

import database.general as database
from database.keys.models import RobotKey
from evals.advanced_agents.tooled_gui_agent import standalone_tooled_guiagent
from security.utils import robot_key_hash
from settings import PROVIDER_API_BASE, PROVIDER_API_KEY, PROVIDER_MODEL
from templates.recovery_payload import RecoveryPayload

router = APIRouter(prefix="/evals")
tracer = trace.get_tracer(__name__)

logger = logging.getLogger(__name__)


class ContinuationOutput(BaseModel):
    continuation: int
    loop_iteration: int


CONTINUATION_INFERRER_PROMPT = """
You are a very knowledgable BPM expert. You are provided with a process model and a recovery trace from a failed instanciation of the process.

This recovery most likely does not cover the entirety of the process, and has left it with some activities still pending.

Your task is to analye the following information and determine which activity should be executed next, given by an integer index.

The activity may be contained in a loop, in which case you should specify the loop iteration as well.

The index should be calculated by order of execution, and not by order of the xml itself.

The recovery will most likely not line up with the process model exactly, as the original process had failed. To determine the next activity, you must identify or infer the state of the process the recovery has left it in. For example, after the submission of an specific for or after having reached a certain screen in the software.

You will be provided with:
1. The recovery task that was attempted
2. The trace information from the recovery attempt
3. The error information from the failed activity
4. The process model (BPMN XML)

Based on this information, determine:
- If the recovery task has been fulfilled: set continuation to the index of the next activity that should be executed (0-based index of activities in the process model)
- If the recovery task has NOT been fulfilled: set continuation to -1
- If the activity is within a loop: specify which iteration of the loop it should be (integer, 0-based). If not in a loop or loop iteration is irrelevant, set loop to 0."""


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


def _validate_payload(data: dict[str, Any]) -> None:
    try:
        _ = RecoveryPayload.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid recovery payload: {exc}") from exc


async def _run_standalone_recovery(
    websocket: WebSocket,
    payload: dict[str, Any],
    recovery_task: str,
) -> dict[str, Any]:
    variables = payload.get("variables", {})
    ui_log = payload.get("ui_log", [])
    errored_act = payload.get("errored_act", {})
    model = payload.get("model", "")

    guiagent_result = await standalone_tooled_guiagent(
        task=recovery_task,
        variables=variables,
        ui_log=ui_log,
        errored_act=errored_act,
        model=model,
        websocket=websocket,
    )
    # guiagent_result = await standalone_uitars(
    #     task=recovery_task,
    #     variables=variables,
    #     ui_log=ui_log,
    #     errored_act=errored_act,
    #     model=model,
    #     websocket=websocket,
    # )

    if isinstance(guiagent_result, str):
        trace_text = guiagent_result
    else:
        trace_text = str(guiagent_result)

    agent_model = OpenAIModel(
        client_args={"api_key": PROVIDER_API_KEY, "base_url": PROVIDER_API_BASE},
        model_id=PROVIDER_MODEL,
    )

    continuation_inferrer = StrandsAgent(
        model=agent_model,
        system_prompt=CONTINUATION_INFERRER_PROMPT,
        callback_handler=None,
    )

    inferrer_prompt = f"""Recovery Task: {recovery_task}

Trace Information:
{trace_text}

Error Information:
{errored_act}

Process Model:
{model}"""

    result: ContinuationOutput = continuation_inferrer(
        inferrer_prompt, structured_output_model=ContinuationOutput
    ).structured_output  # pyright: ignore[reportAssignmentType]

    return result.model_dump()


@router.websocket("/recovery/ws")
async def handle_recovery_eval(
    websocket: WebSocket, session: database.SessionDep
) -> None:
    robot_key = _get_valid_robot_key(websocket, session)
    if robot_key:
        await websocket.accept()
    else:
        raise WebSocketDisconnect(code=1008, reason="Invalid robot key")
    print("connected")

    with tracer.start_as_current_span(
        "handle_recovery_eval",
        attributes={
            "ws.path": "/evals/recovery/eval/ws",
            "ws.client": str(websocket.client),
        },
    ):
        logger.info("Eval WebSocket connected")

        try:
            payload = await websocket.receive_json()
            print("received 1")
            _validate_payload(payload)
            print("valid payload")

            recovery_task_msg = await websocket.receive_json()
            print("received 2")
            recovery_task = recovery_task_msg.get("recovery_task", "")
            if not recovery_task:
                raise ValueError("recovery_task must be a non-empty string")

            print("running")
            result = await _run_standalone_recovery(websocket, payload, recovery_task)
            print("ran")

            await websocket.send_json({"type": "eval_result", "content": result})
            await websocket.close()
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected during eval.")
        except ValueError as exc:
            logger.error(f"Validation error during eval: {exc}")
            try:
                await websocket.send_json(
                    {"type": "error", "code": "VALIDATION_ERROR", "content": str(exc)}
                )
                await websocket.close(code=1003, reason=str(exc))
            except Exception:  # nosec
                pass
        except Exception as e:
            logger.error(f"Error during eval: {e}")
            try:
                await websocket.send_json({"type": "error", "content": str(e)})
                await websocket.close()
            except Exception:  # nosec
                pass
