"""Task functions that wire R2Framework agents to Strands Evals.

Each function creates a real Strands Agent with the original system prompt
and mock tools, invokes it with the test case input, and returns a dict
that includes both evaluation fields and full model responses for traceability.
"""

from __future__ import annotations

import json
from typing import Any

from strands import Agent as StrandsAgent
from strands.models.openai import OpenAIModel
from strands_evals import Case

from evals.mocks import GatewayMocks, HandlerMocks
import settings


def _build_model(model_name: str | None = None) -> OpenAIModel:
    """Create an OpenAIModel from environment config (no DB/SQLModel needed)."""
    return OpenAIModel(
        client_args={
            "api_key": settings.FREE_PROVIDER_API_KEY or settings.PROVIDER_API_KEY,
            "base_url": settings.PROVIDER_API_BASE,
        },
        model_id=model_name or settings.PROVIDER_MODEL,
    )


def _extract_agent_messages(agent: StrandsAgent) -> list[dict[str, Any]]:
    """Extract agent messages as serializable dicts."""
    messages = []
    for msg in agent.messages:
        serializable: dict[str, Any] = {"role": msg.get("role", "unknown")}
        content = msg.get("content", [])
        if isinstance(content, list):
            serializable["content"] = content
        elif isinstance(content, str):
            serializable["content"] = [{"text": content}]
        else:
            serializable["content"] = str(content)
        messages.append(serializable)
    return messages


def gateway_task(case: Case[str, str], mocks: GatewayMocks) -> dict[str, Any]:
    """Invoke the Gateway Orchestrator for error filtering evaluation.

    Returns a dict with:
    - is_ui_error: bool (for evaluator)
    - model_messages: full conversation trace (for debuggability)
    - tool_calls: which mock tools were called and with what args
    - raw_instruction: what was sent to the model
    """
    from gateway.prompts import GATEWAY_ORCHESTRATOR_PROMPT

    mocks.clear()
    error_input = json.loads(case.input)
    model = _build_model()

    agent = StrandsAgent(
        model=model,
        tools=mocks.build_tools(),
        system_prompt=GATEWAY_ORCHESTRATOR_PROMPT,
        callback_handler=None,
    )

    instruction = (
        f"Error code: {error_input.get('code', 'UNKNOWN')}\n"
        f"Variables: {json.dumps(error_input.get('variables', {}))}\n"
        f"Details: {json.dumps(error_input.get('details', {}))}\n\n"
        f"Analyze this error and route it to the appropriate handler."
    )

    agent(instruction)

    return {
        "is_ui_error": mocks.is_ui_error_routed,
        "model_messages": _extract_agent_messages(agent),
        "tool_calls": {
            "ui_handler": mocks.ui_handler_calls,
            "route_to_human": mocks.human_calls,
        },
        "raw_instruction": instruction,
    }


def handler_task(case: Case[str, str], mocks: HandlerMocks) -> dict[str, Any]:
    """Invoke the UI Exception Handler for task identification evaluation.

    Returns a dict with:
    - identified_task: str (for evaluator)
    - model_messages: full conversation trace
    - tool_calls: which mock tools were called and with what args
    - raw_instruction: what was sent to the model
    """
    from modules.uierror.prompts import UI_EXCEPTION_HANDLER

    mocks.clear()
    error_input = json.loads(case.input)
    model = _build_model()

    agent = StrandsAgent(
        model=model,
        tools=mocks.build_tools(),
        system_prompt=UI_EXCEPTION_HANDLER,
        callback_handler=None,
    )

    instruction = (
        f"Task: {error_input.get('task', 'Unknown task')}\n"
        f"Action history: {json.dumps(error_input.get('action_history', []))}\n"
        f"Failed activity: {json.dumps(error_input.get('failed_activity', {}))}\n"
        f"Future activities: {json.dumps(error_input.get('future_activities', []))}\n"
        f"Variables: {json.dumps(error_input.get('variables', {}))}\n\n"
        f"Analyze this error and identify the recovery action needed."
    )

    agent(instruction)

    return {
        "identified_task": mocks.identified_task,
        "model_messages": _extract_agent_messages(agent),
        "tool_calls": {
            "recovery_agent": mocks.recovery_calls,
            "compute_continuation": mocks.continuation_calls,
        },
        "raw_instruction": instruction,
    }
