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
      - input: JSON string of the error_input
      - expected_output: JSON string of the relevant ground truth fields
      - metadata: category + source info
    """
    filename = f"sample_{category}.json"
    filepath = DATA_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Dataset file not found: {filepath}")

    with open(filepath, encoding="utf-8") as f:
        raw_cases = json.load(f)

    cases: list[Case[str, str]] = []
    for entry in raw_cases:
        gt = entry["ground_truth"]

        if category == "error_filtering":
            expected = json.dumps({"is_ui_error": gt["is_ui_error"]})
        elif category == "task_identification":
            expected = json.dumps(
                {
                    "recovery_task": gt["recovery_task"],
                    "recovery_subtasks": gt.get("recovery_subtasks", []),
                    "minimum_recovery": gt.get("minimum_recovery", ""),
                }
            )
        else:
            expected = json.dumps(gt)

        cases.append(
            Case[str, str](
                name=entry["id"],
                input=json.dumps(entry["error_input"]),
                expected_output=expected,
                metadata={
                    "category": category,
                    "source_trace": entry.get("source_trace"),
                    "corruption": entry.get("corruption_description"),
                    "task": entry.get(
                        "task", entry.get("error_input", {}).get("task", "")
                    ),
                },
            )
        )

    return cases
