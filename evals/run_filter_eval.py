"""Run Contribution 1 evaluation: Error Filtering.

Evaluates whether the Gateway Orchestrator correctly routes UI errors
to the UI handler and non-UI errors to human escalation.

Usage:
    uv run python -m evals.run_filter_eval
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strands_evals.evaluators import OutputEvaluator
from strands_evals.types.evaluation import EvaluationData

import settings
from evals.agents import build_model, gateway_task
from evals.dataset import load_cases
from evals.evaluators import RoutingEvaluator
from evals.mocks import GatewayMocks

OUTPUT_DIR = Path("experiment_files")


def run_evaluation() -> dict[str, Any]:
    """Run the error filtering evaluation and return full results."""
    cases = load_cases("error_filtering")
    print(f"Loaded {len(cases)} test cases for error filtering evaluation.\n")

    judge_model = build_model()
    mocks = GatewayMocks()
    routing_eval = RoutingEvaluator()
    rubric_eval = OutputEvaluator(
        model=judge_model,
        rubric="""
        Evaluate whether the Gateway Orchestrator correctly classified this error.

        Score 1.0 if:
        - The agent correctly determined whether this is a UI-related error or not
        - The routing decision (to UI handler vs human escalation) is appropriate

        Score 0.5 if:
        - The agent's reasoning is sound but the final routing decision is debatable
          given the ambiguity of the error message

        Score 0.0 if:
        - The agent clearly misclassified a clear-cut error
        - The agent could not make a routing decision

        Consider the error message, activity context, and application involved.
        """,
        include_inputs=True,
    )

    case_results: list[dict[str, Any]] = []

    for i, case in enumerate(cases):
        print(f"[{i + 1}/{len(cases)}] Running {case.name}...")

        # Run task function to get model response
        task_output = gateway_task(case, mocks)

        # Build EvaluationData for each evaluator
        eval_data = EvaluationData[str, str](
            input=case.input,
            actual_output=json.dumps(task_output),
            expected_output=case.expected_output,
            name=case.name,
            metadata=case.metadata,
        )

        # Run evaluators
        routing_results = routing_eval.evaluate(eval_data)
        rubric_results = rubric_eval.evaluate(eval_data)

        routing_result = routing_results[0] if routing_results else None
        rubric_result = rubric_results[0] if rubric_results else None

        # Parse ground truth
        gt = json.loads(case.expected_output or "{}")

        result_entry = {
            "case_id": case.name,
            "task": (case.metadata or {}).get("task", ""),
            "ground_truth": gt,
            "agent_output": {
                "is_ui_error": task_output.get("is_ui_error"),
                "tool_calls": deepcopy(
                    task_output.get("tool_calls", {})
                ),  # Deepcopy to avoid mutation issues
                "raw_instruction": task_output.get("raw_instruction", ""),
                "model_messages": task_output.get("model_messages", []),
            },
            "evaluations": {
                "routing": {
                    "score": routing_result.score if routing_result else None,
                    "pass": routing_result.test_pass if routing_result else None,
                    "label": routing_result.label if routing_result else None,
                    "reason": routing_result.reason if routing_result else None,
                },
                "rubric": {
                    "score": rubric_result.score if rubric_result else None,
                    "pass": rubric_result.test_pass if rubric_result else None,
                    "reason": rubric_result.reason if rubric_result else None,
                },
            },
        }
        case_results.append(result_entry)

        status = "PASS" if (routing_result and routing_result.test_pass) else "FAIL"
        print(
            f"  [{status}] routing={task_output.get('is_ui_error')}, expected={gt.get('is_ui_error')}"
        )

    # Compute aggregate metrics
    routing_scores = [
        r["evaluations"]["routing"]["score"]
        for r in case_results
        if r["evaluations"]["routing"]["score"] is not None
    ]
    rubric_scores = [
        r["evaluations"]["rubric"]["score"]
        for r in case_results
        if r["evaluations"]["rubric"]["score"] is not None
    ]

    tp = fp = tn = fn = 0
    for r in case_results:
        gt_ui = r["ground_truth"].get("is_ui_error", False)
        correct = r["evaluations"]["routing"]["pass"] is True
        if gt_ui and correct:
            tp += 1
        elif gt_ui and not correct:
            fn += 1
        elif not gt_ui and correct:
            tn += 1
        else:
            fp += 1

    total = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    full_results = {
        "experiment": "error_filtering_eval",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_id": settings.PROVIDER_MODEL,
        "metrics": {
            "routing": {
                "accuracy": (tp + tn) / total if total > 0 else 0.0,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "tp": tp,
                "fp": fp,
                "tn": tn,
                "fn": fn,
                "avg_score": sum(routing_scores) / len(routing_scores)
                if routing_scores
                else 0.0,
            },
            "rubric": {
                "avg_score": sum(rubric_scores) / len(rubric_scores)
                if rubric_scores
                else 0.0,
            },
        },
        "case_results": case_results,
    }

    return full_results


def main() -> None:
    results = run_evaluation()

    m = results["metrics"]["routing"]
    print("\n" + "=" * 60)
    print("  CONTRIBUTION 1: Error Filtering Evaluation")
    print("=" * 60 + "\n")

    # Per-case results
    for r in results["case_results"]:
        gt = r["ground_truth"].get("is_ui_error", False)
        pred = r["agent_output"].get("is_ui_error")
        correct = r["evaluations"]["routing"]["pass"]
        status = "PASS" if correct else "FAIL"
        gt_label = "UI" if gt else "NON-UI"
        pred_label = "UI" if pred else ("NON-UI" if pred is not None else "?")
        print(f"  [{status}] {r['case_id']}")
        print(f"         GT={gt_label}  Pred={pred_label}  | {r['task']}")

    print()
    print("  --- Classification Metrics ---")
    print(
        f"  Accuracy:  {m['accuracy']:.2%}  ({m['tp'] + m['tn']}/{m['tp'] + m['fp'] + m['tn'] + m['fn']})"
    )
    print(
        f"  Precision: {m['precision']:.2%}  ({m['tp']}/{m['tp'] + m['fp']})"
        if (m["tp"] + m["fp"]) > 0
        else "  Precision: N/A"
    )
    print(
        f"  Recall:    {m['recall']:.2%}  ({m['tp']}/{m['tp'] + m['fn']})"
        if (m["tp"] + m["fn"]) > 0
        else "  Recall: N/A"
    )
    print(f"  F1 Score:  {m['f1']:.2%}")
    print(f"  Confusion: TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}")
    print(f"  Rubric avg: {results['metrics']['rubric']['avg_score']:.2f}")
    print()

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "error_filtering_eval.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"Full results (with model responses) saved to {output_path}")


if __name__ == "__main__":
    main()
