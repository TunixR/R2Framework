"""RecoveryBench dataset loader."""

import json
from pathlib import Path
from typing import Literal

from strands_evals import Case

DATA_DIR = Path(__file__).parent / "data"


def load_cases(
    category: Literal["error_filtering", "task_identification"],
) -> list[Case[str, str]]:
    """Load RecoveryBench test cases for a given category.

    Returns Strands Case objects with:
      - name: test case ID
      - input: JSON string of the RecoveryPayload (task_identification)
              or error_input dict (error_filtering)
      - expected_output: JSON string of the relevant ground truth fields
      - metadata: category + source info
    """
    if category == "task_identification":
        return _load_task_identification_cases()
    return _load_error_filtering_cases()


def _load_task_identification_cases() -> list[Case[str, str]]:
    """Load task identification cases from payloads.json + ground_truth.json."""
    payloads_path = DATA_DIR / "payloads.json"
    gt_path = DATA_DIR / "ground_truth.json"

    if not payloads_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {payloads_path}")
    if not gt_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {gt_path}")

    with open(payloads_path, encoding="utf-8") as f:
        payloads = json.load(f)
    with open(gt_path, encoding="utf-8") as f:
        ground_truths = json.load(f)

    cases: list[Case[str, str]] = []
    for payload, gt in zip(payloads, ground_truths):
        expected = json.dumps(
            {
                "validity": gt.get("validity", True),
                "extensiveness": gt.get("extensiveness", "optimal"),
                "explanation": gt.get("explanation", ""),
            }
        )

        cases.append(
            Case[str, str](
                name=gt["id"],
                input=json.dumps(payload),
                expected_output=expected,
                metadata={
                    "category": "task_identification",
                    "task_name": gt.get("task_name", payload.get("task_name", "")),
                },
            )
        )

    return cases


def _load_error_filtering_cases() -> list[Case[str, str]]:
    """Load error filtering cases (unchanged from original format)."""
    filename = "sample_error_filtering.json"
    filepath = DATA_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Dataset file not found: {filepath}")

    with open(filepath, encoding="utf-8") as f:
        raw_cases = json.load(f)

    cases: list[Case[str, str]] = []
    for entry in raw_cases:
        gt = entry["ground_truth"]
        expected = json.dumps({"is_ui_error": gt["is_ui_error"]})

        cases.append(
            Case[str, str](
                name=entry["id"],
                input=json.dumps(entry["error_input"]),
                expected_output=expected,
                metadata={
                    "category": "error_filtering",
                    "source_trace": entry.get("source_trace"),
                    "corruption": entry.get("corruption_description"),
                    "task": entry.get(
                        "task", entry.get("error_input", {}).get("task", "")
                    ),
                },
            )
        )

    return cases
