"""Task functions that wire R2Framework agents to Strands Evals.

Each function creates a real Strands Agent with the original system prompt,
invokes it with the test case input, and returns a dict that includes both
evaluation fields and full model responses for traceability.
"""

from __future__ import annotations

import asyncio
import json
import re
import regex
import time
from pathlib import Path
from typing import Any, Literal

from strands import Agent as StrandsAgent
from strands.models.openai import OpenAIModel
from strands.types.content import ContentBlock
from strands_evals import Case
from tenacity import retry, stop_after_attempt

import settings


def build_model(
    model_name: str | None = None,
    api_url: str | None = None,
) -> OpenAIModel:
    """Create an OpenAIModel from environment config or CLI overrides."""
    return OpenAIModel(
        client_args={
            "api_key": settings.PROVIDER_API_KEY or settings.FREE_PROVIDER_API_KEY,
            "base_url": api_url or settings.PROVIDER_API_BASE,
        },
        model_id=model_name or settings.PROVIDER_MODEL,
    )


def _extract_agent_messages(agent: StrandsAgent) -> list[dict[str, Any]]:
    """Extract agent messages as serializable dicts."""
    messages = []
    for msg in agent.messages:
        serializable: dict[str, Any] = {"role": msg.get("role", "unknown")}
        serializable["content"] = []
        # dont include bytes
        messages.append(serializable)
        content = msg.get("content", [])
        for block in content:
            if not ("image" in block or block.get("type", "") == "image"):
                messages[-1]["content"].append(block)
    return messages


def _extract_final_task(agent: StrandsAgent) -> str:
    """Extract the <Final task> content from the agent's last response."""
    messages = _extract_agent_messages(agent)
    if not messages:
        return ""

    last_msg = messages[-1]
    content = last_msg.get("content", [])
    if not content:
        return ""

    # Get the text from the last content block
    text = ""
    for block in reversed(content):
        if isinstance(block, dict) and "text" in block:
            text = block["text"]
            break
    if not text:
        return ""

    if match := regex.search(r'\{(?:[^{}"\\]+|"(?:\\.|[^"\\])*"|(?R))*\}', text):
        try:
            json_content = json.loads(match.group(0))
            if "final_task" in json_content:
                return json_content["final_task"].strip()
        except json.JSONDecodeError:
            pass  # If JSON parsing fails, continue to regex extraction

    # Fallback: try "final_task": ... (without closing tag)
    if match := re.search(r'"final_task":\s*(.*?)$', text, re.DOTALL):
        return match.group(1).strip()

    # Try regex for <Final task>...</Final task>
    # match = re.search(r"<Final task>(.*?)</Final task>", text, re.DOTALL)
    # if match:
    #     return match.group(1).strip()

    # # Fallback: try <Final task>: ... (without closing tag)
    # match = re.search(r"<Final task>:\s*(.*?)$", text, re.DOTALL)
    # if match:
    #     return match.group(1).strip()

    # # Last resort: grab last non-empty line
    # lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    # if lines:
    #     last_line = lines[-1]
    #     # Strip any remaining tags
    #     last_line = re.sub(r"</?Final task>:", "", last_line).strip()
    #     return last_line

    return "TASK_NOT_FOUND"


@retry(stop=stop_after_attempt(3), reraise=True)
def gateway_task(case: Case[str, str], mocks: Any) -> dict[str, Any]:
    """Invoke the Gateway Orchestrator for error filtering evaluation.

    Returns a dict with:
    - is_ui_error: bool (for evaluator)
    - model_messages: full conversation trace (for debuggability)
    - tool_calls: which mock tools were called and with what args
    - raw_instruction: what was sent to the model
    """
    from prompts.gateway import GATEWAY_ORCHESTRATOR_PROMPT

    mocks.clear()
    error_input = json.loads(case.input)
    model = build_model()

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

    _ = agent(instruction)

    return {
        "is_ui_error": mocks.is_ui_error_routed,
        "model_messages": _extract_agent_messages(agent),
        "tool_calls": {
            "ui_handler": mocks.ui_handler_calls,
            "route_to_human": mocks.human_calls,
        },
        "raw_instruction": instruction,
    }


def _extract_agent_metrics(
    result: Any,
    first_token_time: float | None = None,
    last_token_time: float | None = None,
) -> dict[str, Any]:
    """Extract token usage and timing metrics from an AgentResult.

    Args:
        result: The AgentResult from the agent invocation.
        first_token_time: Wall-clock time when the first token was received.
        last_token_time: Wall-clock time when the last token was received.

    Returns a dict with:
    - input_tokens, output_tokens, total_tokens
    - total_duration_s: wall-clock time across all cycles
    - first_to_last_token_s: time from first token to last token
    """
    usage = result.metrics.accumulated_usage

    input_tokens = usage.get("inputTokens", 0)
    output_tokens = usage.get("outputTokens", 0)
    total_tokens = usage.get("totalTokens", 0)

    total_duration_s = sum(result.metrics.cycle_durations)

    first_to_last_token_s = 0.0
    if first_token_time and last_token_time:
        first_to_last_token_s = last_token_time - first_token_time

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "total_duration_s": round(total_duration_s, 3),
        "first_to_last_token_s": round(first_to_last_token_s, 3),
    }


def _load_image_content(image_path: Path) -> ContentBlock:
    """Load an image file and return an ImageContent dict for Strands."""
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    suffix = image_path.suffix.lower().lstrip(".")
    format_map = {
        "png": "png",
        "jpg": "jpeg",
        "jpeg": "jpeg",
        "gif": "gif",
        "webp": "webp",
    }
    img_format: Literal["png", "jpeg", "gif", "webp"] = format_map.get(suffix, "png")  # pyright: ignore[reportAssignmentType]

    return {
        "image": {
            "format": img_format,
            "source": {"bytes": image_bytes},
        }
    }


@retry(stop=stop_after_attempt(3), reraise=True)
async def _run_handler_async(
    case: Case[str, str],
    *,
    api_url: str | None = None,
    model_name: str | None = None,
    image_path: Path | None = None,
) -> tuple[dict[str, Any], Any, float | None, float | None]:
    """Run the handler agent asynchronously, tracking first/last token times.

    Uses stream_async to capture precise timing and the AgentResult (with metrics)
    from a single invocation.

    Returns (task_output, agent_result).
    """
    from prompts.task_inference import TASK_INFERENCE_ONLY

    payload = json.loads(case.input)
    model = build_model(model_name=model_name, api_url=api_url)

    agent = StrandsAgent(
        model=model,
        system_prompt=TASK_INFERENCE_ONLY,
        callback_handler=None,
    )

    instruction = (
        f"task_name: {payload.get('task_name', '')},\n"
        f"platform={payload.get('platform', '')},\n"
        f"os={payload.get('os', '')},\n"
        f"variables={json.dumps(payload.get('variables', {}))},\n"
        f"ui_log={json.dumps(payload.get('ui_log', []))},\n"
        f"errored_act={json.dumps(payload.get('errored_act', {}))},\n"
        f"model={payload.get('model', '')}"
    )

    if image_path is not None and image_path.exists():
        prompt: str | list[ContentBlock] = [
            ContentBlock(text=instruction),
            _load_image_content(image_path),
        ]
    else:
        prompt = instruction

    first_token_time: float | None = None
    last_token_time: float | None = None
    agent_result: Any = None

    async for event in agent.stream_async(prompt):
        now = time.time()
        if isinstance(event, dict):
            # Content events carry token data
            if "data" in event:
                if first_token_time is None:
                    first_token_time = now
                last_token_time = now
            # Final event carries the AgentResult with metrics
            if "result" in event:
                agent_result = event["result"]

    generated_task = _extract_final_task(agent)

    return (
        {
            "generated_task": generated_task,
            "model_messages": _extract_agent_messages(agent),
            "raw_instruction": instruction,
        },
        agent_result,
        first_token_time,
        last_token_time,
    )


def handler_task(
    case: Case[str, str],
    *,
    api_url: str | None = None,
    model_name: str | None = None,
    image_path: Path | None = None,
) -> dict[str, Any]:
    """Invoke the agent for task identification evaluation.

    Uses stream_async for precise first-to-last token timing and metrics
    from a single invocation. No mock tools — the agent generates the
    recovery task directly.

    Returns a dict with:
    - generated_task: str (the extracted recovery task)
    - model_messages: full conversation trace
    - raw_instruction: what was sent to the model
    - agent_metrics: token usage and timing metrics
    """
    task_output, agent_result, first_token_time, last_token_time = asyncio.run(
        _run_handler_async(
            case,
            api_url=api_url,
            model_name=model_name,
            image_path=image_path,
        )
    )

    if agent_result is not None:
        task_output["agent_metrics"] = _extract_agent_metrics(
            agent_result, first_token_time, last_token_time
        )
    else:
        # Fallback: no result captured (shouldn't happen)
        task_output["agent_metrics"] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "total_duration_s": 0.0,  # nosec
            "first_to_last_token_s": 0.0,  # nosec
        }

    return task_output
