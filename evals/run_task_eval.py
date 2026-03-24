"""Run Contribution 2 evaluation: Task Identification.

Evaluates whether the UI Exception Handler correctly identifies
what recovery task/action is needed to unblock the robot.

Evaluates on two axes:
- Validity: Is the identified task self-contained and actionable by a GUI agent?
- Minimality: 1=full task, 2=mid-level subtask, 3=minimal single action

Usage:
    uv run python -m evals.run_task_eval
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strands_evals.types.evaluation import EvaluationData

import settings
from evals.agents import _build_model, handler_task
from evals.dataset import load_cases
from evals.evaluators import TaskIdentificationEvaluator
from evals.mocks import HandlerMocks

OUTPUT_DIR = Path("experiment_files")


def _parse_minimality(label: str | None) -> int | None:
    """Extract minimality level from evaluator label (e.g., 'VALID-L3' -> 3)."""
    if label and label.startswith("VALID-L"):
        try:
            return int(label[-1])
        except ValueError:
            pass
    return None


def run_evaluation() -> dict[str, Any]:
    """Run the task identification evaluation and return full results."""
    cases = load_cases("task_identification")
    print(f"Loaded {len(cases)} test cases for task identification evaluation.\n")

    judge_model = _build_model()
    mocks = HandlerMocks()
    evaluator = TaskIdentificationEvaluator(judge_model=judge_model)

    case_results: list[dict[str, Any]] = []

    for i, case in enumerate(cases):
        print(f"[{i + 1}/{len(cases)}] Running {case.name}...")

        task_output = handler_task(case, mocks)

        eval_data = EvaluationData[str, str](
            input=case.input,
            actual_output=json.dumps(task_output),
            expected_output=case.expected_output,
            name=case.name,
            metadata=case.metadata,
        )

        eval_results = evaluator.evaluate(eval_data)
        eval_result = eval_results[0] if eval_results else None

        gt = json.loads(case.expected_output or "{}")
        minimality = _parse_minimality(eval_result.label if eval_result else None)

        result_entry = {
            "case_id": case.name,
            "task": (case.metadata or {}).get("task", ""),
            "ground_truth": gt,
            "agent_output": {
                "identified_task": task_output.get("identified_task"),
                "tool_calls": task_output.get("tool_calls", {}),
                "raw_instruction": task_output.get("raw_instruction", ""),
                "model_messages": task_output.get("model_messages", []),
            },
            "evaluation": {
                "score": eval_result.score if eval_result else None,
                "pass": eval_result.test_pass if eval_result else None,
                "label": eval_result.label if eval_result else None,
                "minimality": minimality,
                "reason": eval_result.reason if eval_result else None,
            },
        }
        case_results.append(result_entry)

        status = "PASS" if (eval_result and eval_result.test_pass) else "FAIL"
        minimality_str = f"L{minimality}" if minimality else "—"
        print(
            f"  [{status}] minimality={minimality_str}  task='{task_output.get('identified_task', 'NONE')}'"
        )

    # Compute metrics
    scores = [
        r["evaluation"]["score"]
        for r in case_results
        if r["evaluation"]["score"] is not None
    ]
    passes = [
        r["evaluation"]["pass"]
        for r in case_results
        if r["evaluation"]["pass"] is not None
    ]
    minimalities = [
        r["evaluation"]["minimality"]
        for r in case_results
        if r["evaluation"]["minimality"] is not None
    ]

    valid_count = sum(1 for p in passes if p)
    total_count = len(passes)

    full_results = {
        "experiment": "task_identification_eval",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_id": settings.PROVIDER_MODEL,
        "metrics": {
            "task_identification": {
                "valid_rate": valid_count / total_count if total_count > 0 else 0.0,
                "avg_score": sum(scores) / len(scores) if scores else 0.0,
                "minimality_distribution": {
                    "L1_full_task": sum(1 for m in minimalities if m == 1),
                    "L2_mid_level": sum(1 for m in minimalities if m == 2),
                    "L3_minimal": sum(1 for m in minimalities if m == 3),
                    "avg_minimality": sum(minimalities) / len(minimalities)
                    if minimalities
                    else 0.0,
                },
            },
        },
        "case_results": case_results,
    }

    return full_results


def main() -> None:
    results = run_evaluation()

    m = results["metrics"]["task_identification"]
    md = m["minimality_distribution"]
    print("\n" + "=" * 60)
    print("  CONTRIBUTION 2: Task Identification Evaluation")
    print("=" * 60 + "\n")

    # Per-case results
    for r in results["case_results"]:
        status = "PASS" if r["evaluation"]["pass"] else "FAIL"
        identified = r["agent_output"].get("identified_task") or "(none)"
        minimality = r["evaluation"].get("minimality")
        m_str = f"L{minimality}" if minimality else "—"
        print(f"  [{status}] [{m_str}] {r['case_id']}")
        print(f"         Identified: {identified}")
        print(f"         Judge:      {r['evaluation']['reason']}")
        print()

    print("  --- Metrics ---")
    print(
        f"  Valid rate:     {m['valid_rate']:.2%}  ({sum(1 for r in results['case_results'] if r['evaluation']['pass'])}/{len(results['case_results'])})"
    )
    print(f"  Avg score:      {m['avg_score']:.2f}")
    print(
        f"  Minimality:     L1(full)={md['L1_full_task']}  L2(mid)={md['L2_mid_level']}  L3(minimal)={md['L3_minimal']}"
    )
    print(f"  Avg minimality: {md['avg_minimality']:.1f}  (target: close to 3.0)")
    print()

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "task_identification_eval.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"Full results (with model responses) saved to {output_path}")


if __name__ == "__main__":
    main()
