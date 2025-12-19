from typing import Any, Dict

from strands import ToolContext, tool


@tool(
    name="route_to_human",
    description="Route the error to a human operator for manual intervention.",
    context=True,
)
async def route_to_human(error_data: str, tool_context: ToolContext) -> Dict[str, Any]:  # type: ignore
    # TODO: When cockpit
    pass
