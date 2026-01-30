from typing import Any

from strands import ToolContext, tool


@tool(
    name="route_to_human",
    description="Route the error to a human operator for manual intervention.",
    context=True,
)
async def route_to_human(error_data: str, tool_context: ToolContext) -> dict[str, Any]:  # pyright: ignore[reportUnusedParameter]
    raise NotImplementedError("This tool is a placeholder and needs to be implemented.")
