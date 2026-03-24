"""Custom evaluators for R2Framework RecoveryBench."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from strands import Agent as StrandsAgent
from strands_evals.evaluators import Evaluator
from strands_evals.types.evaluation import EvaluationData, EvaluationOutput


def _parse_output(output: Any) -> dict[str, Any] | None:
    """Parse task function output (may be str JSON or dict)."""
    if isinstance(output, dict):
        return output
    try:
        return json.loads(str(output))
    except (json.JSONDecodeError, TypeError):
        return None


class RoutingEvaluator(Evaluator[str, str]):
    """Deterministic evaluator for Contribution 1: Error Filtering.

    The task function returns {"is_ui_error": bool} based on which mock
    tool the Gateway Orchestrator called. Compares against GT directly.

    Metrics (at experiment level): precision, recall, F1 on is_ui_error.
    """

    def evaluate(
        self, evaluation_case: EvaluationData[str, str]
    ) -> list[EvaluationOutput]:
        expected = json.loads(evaluation_case.expected_output or "{}")
        actual = _parse_output(evaluation_case.actual_output)

        if actual is None:
            return [
                EvaluationOutput(
                    score=0.0,
                    test_pass=False,
                    reason=f"Could not parse agent output: {str(evaluation_case.actual_output)[:200]}",
                    label="UNPARSEABLE",
                )
            ]

        expected_val = expected.get("is_ui_error")
        actual_val = actual.get("is_ui_error")

        if actual_val is None:
            return [
                EvaluationOutput(
                    score=0.0,
                    test_pass=False,
                    reason="Agent output missing 'is_ui_error' field.",
                    label="MISSING",
                )
            ]

        match = actual_val == expected_val
        return [
            EvaluationOutput(
                score=1.0 if match else 0.0,
                test_pass=match,
                reason=f"Expected is_ui_error={expected_val}, got {actual_val}",
                label="CORRECT" if match else "WRONG",
            )
        ]

    async def evaluate_async(
        self, evaluation_case: EvaluationData[str, str]
    ) -> list[EvaluationOutput]:
        return self.evaluate(evaluation_case)


class TaskIdentificationEvaluator(Evaluator[str, str]):
    """LLM-as-judge evaluator for Contribution 2: Task Identification.

    Evaluates on two axes:
    - Validity: Is the identified task actionable by a GUI agent without
      knowing the original task? (self-contained)
    - Minimality: How minimal is the recovery path?
      1 = full remaining task (redo everything from the failed point)
      2 = mid-level subtask (covers several future robot actions)
      3 = minimal single action (just enough to unblock the robot)

    Score = 0.0 if invalid, else minimality / 3.0.
    This rewards minimal but valid identifications.
    """

    def __init__(self, judge_model: Any = None) -> None:
        super().__init__()
        self.judge_model = judge_model

    def evaluate(
        self, evaluation_case: EvaluationData[str, str]
    ) -> list[EvaluationOutput]:
        expected = json.loads(evaluation_case.expected_output or "{}")
        actual = _parse_output(evaluation_case.actual_output)

        if actual is None:
            return [
                EvaluationOutput(
                    score=0.0,
                    test_pass=False,
                    reason=f"Could not parse agent output: {str(evaluation_case.actual_output)[:200]}",
                    label="UNPARSEABLE",
                )
            ]

        identified = actual.get("identified_task", "")

        if not identified:
            return [
                EvaluationOutput(
                    score=0.0,
                    test_pass=False,
                    reason="No task identified by agent.",
                    label="EMPTY",
                )
            ]

        class JudgeOutput(BaseModel):
            reason: str
            valid: bool
            minimality: int

        judge = StrandsAgent(
            model=self.judge_model,
            system_prompt=(
                "You are evaluating an RPA error recovery agent's output. "
                "The agent identified a recovery task that will be passed to a GUI automation agent "
                "for execution. You must evaluate on TWO axes:\n\n"
                "AXIS 1 — VALIDITY (self-contained & actionable):\n"
                "The identified task will be handed to a GUI agent that has limited context about the "
                "original task and the error, or the application state. It sees the identified task text."
                "It is also given the the failed point in the original task and past actions, as well as current application"
                "The GUI Agent will be able to get screenshots and interact with the screen to see the application,"
                "so we prefer self-contained instructions without referencing concrete individual input actions."
                "It is very important for you to understand that the GUI agent is capable of iteratively navigating the interfaces and explore options to fulfill the given task."
                "This is a key point because sometimes we don't know what the specific ui flow needs to be to unblock the robot, "
                "but the instruction need to be valid enough for the GUI agent to figure it out on its own. So you should not penalize an identified task that requires "
                "the GUI agent to explore and figure out the details, as long as the instruction is valid and actionable for the GUI agent to execute.\n"
                "- valid=true: The task contains enough information for a GUI agent to execute it."
                "It must specify WHAT to do, WHERE, and "
                "any concrete values (e.g., 'Enter =HORA(D3)*F3 in cell E3' not just 'Fix the formula'). Except variables, which are provided separately\n"
                "- valid=false: The task is vague, refers to unknown context, or a GUI agent "
                "couldn't act on it alone (e.g., 'Find the correct menu', 'Fix the error').\n\n"
                "AXIS 2 — MINIMALITY (recovery path scope):\n"
                "Rate 1-3 based on how much of the remaining work the identified task covers:\n"
                "- 1: Full task — describes the full task the original robot was tasked with\n"
                "- 2: Mid-level — covers a chunk of remaining actions (2+ future robot steps)\n"
                "- 3: Minimal — single action or smallest step to unblock the robot and let it continue\n\n"
                "IMPORTANT: A valid identification at ANY minimality level is acceptable. "
                "But prefer MORE MINIMAL identifications when valid. "
                "An identification that is both valid and minimal (level 3) is ideal.\n\n"
                'Respond ONLY with JSON: {"reason": "...", "valid": true|false, "minimality": 1|2|3}'
            ),
            callback_handler=None,
        )

        prompt = (
            f"Ground truth reference (for context only — judge based on the agent's output):\n"
            f"- Full recovery: {expected.get('recovery_task', '')}\n"
            f"- Subtask breakdown: {json.dumps(expected.get('recovery_subtasks', []))}\n"
            f"- Minimal unblock: {expected.get('minimum_recovery', '')}\n\n"
            f'Agent\'s identified task: "{identified}"\n\n'
            f"Evaluate validity and minimality."
        )

        result = judge(prompt, structured_output_model=JudgeOutput).structured_output

        valid = result.valid  # pyright: ignore[reportOptionalMemberAccess,reportAttributeAccessIssue]
        minimality = result.minimality  # pyright: ignore[reportOptionalMemberAccess,reportAttributeAccessIssue]
        reason = result.reason  # pyright: ignore[reportOptionalMemberAccess,reportAttributeAccessIssue]

        # Clamp minimality
        minimality = max(1, min(3, int(minimality)))
        print(minimality)

        if not valid:
            score = 0.0
            label = "INVALID"
        else:
            score = minimality / 3.0
            label = f"VALID-L{minimality}"
        print(label)

        return [
            EvaluationOutput(
                score=score,
                test_pass=valid,
                reason=f"[{label}] minimality={minimality}. {reason}",
                label=label,
            )
        ]

    async def evaluate_async(
        self, evaluation_case: EvaluationData[str, str]
    ) -> list[EvaluationOutput]:
        return self.evaluate(evaluation_case)
