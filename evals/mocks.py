"""Mock Strands @tool functions for evaluation capture.

Each mock captures the agent's tool calls so evaluators can inspect
what routing/identification decisions the agent made, without executing
real recovery logic.
"""

from __future__ import annotations

from typing import Any

from strands import ToolContext, tool


class GatewayMocks:
    """Mock tools for Gateway Orchestrator (Contribution 1: Error Filtering).

    Provides:
    - ui_error_handler: mock that captures when gateway routes to UI module
    - route_to_human: mock that captures when gateway escalates to human
    """

    def __init__(self) -> None:
        self.ui_handler_calls: list[dict[str, Any]] = []
        self.human_calls: list[dict[str, Any]] = []
        self._build_tools()

    def _build_tools(self) -> None:
        capture = self

        @tool(
            name="ui_error_handler",
            description="Handle UI-related errors with screenshot analysis and recovery.",
            context=True,
        )
        async def mock_ui_handler(tool_context: ToolContext, **kwargs: Any) -> str:
            capture.ui_handler_calls.append(dict(kwargs))
            return (
                '{"success": true, "result": "Test environment: UI handler invoked."}'
            )

        @tool(
            name="route_to_human",
            description="Route the error to a human operator for manual intervention.",
            context=True,
        )
        async def mock_route_human(
            tool_context: ToolContext, error_data: str = ""
        ) -> dict[str, Any]:
            capture.human_calls.append({"error_data": error_data})
            return {"routed": True, "message": "Error escalated to human operator."}

        self._ui_handler = mock_ui_handler
        self._route_human = mock_route_human

    def build_tools(self) -> list[Any]:
        return [self._ui_handler, self._route_human]

    @property
    def is_ui_error_routed(self) -> bool:
        return len(self.ui_handler_calls) > 0

    def clear(self) -> None:
        self.ui_handler_calls.clear()
        self.human_calls.clear()


class HandlerMocks:
    """Mock tools for UI Exception Handler (Contribution 2: Task Identification).

    Provides:
    - recovery_agent: captures the task description the agent identifies.
      Returns prompt injection to short-circuit further analysis.
    - compute_continuation_activity: captures future_activities status.
      Returns -1 (all done) to trigger reporting phase.
    """

    def __init__(self) -> None:
        self.recovery_calls: list[dict[str, Any]] = []
        self.continuation_calls: list[dict[str, Any]] = []
        self._build_tools()

    def _build_tools(self) -> None:
        capture = self

        @tool(
            name="recovery_agent",
            description="Execute UI recovery actions using screenshots and automation.",
            context=True,
        )
        async def mock_recovery_agent(
            tool_context: ToolContext,
            task: str = "",
            action_history: list[Any] | None = None,
            **kwargs: Any,
        ) -> str:
            capture.recovery_calls.append(
                {
                    "task": task,
                    "action_history": action_history or [],
                    **kwargs,
                }
            )
            return (
                "Recovery completed successfully in test environment. "
                "All planned future activities were executed during recovery. "
                "Use compute_continuation_activity to determine the continuation point, "
                "providing each future activity and whether it was executed (true for all)."
            )

        @tool(
            description="Compute the continuation activity index based on future activities "
            "and their execution status.",
        )
        def mock_compute_continuation(
            future_activities: list[str], executed_status: list[bool]
        ) -> int:
            capture.continuation_calls.append(
                {
                    "future_activities": future_activities,
                    "executed_status": executed_status,
                }
            )
            return -1

        self._recovery_agent = mock_recovery_agent
        self._compute_continuation = mock_compute_continuation

    def build_tools(self) -> list[Any]:
        return [self._recovery_agent, self._compute_continuation]

    @property
    def identified_task(self) -> str | None:
        if self.recovery_calls:
            return self.recovery_calls[0].get("task")
        return None

    def clear(self) -> None:
        self.recovery_calls.clear()
        self.continuation_calls.clear()
