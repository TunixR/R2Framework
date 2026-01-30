import pytest
from pydantic import ValidationError

from agent_tools.utils import compute_continuation_activity

"""
Tests assert the intended behavior:

- The function returns the index of the first False after the last True in executed_status.
- If there is no True at all, the "last True" is conceptually before the list, so the first False is at index 0 (if any).
- If all entries are True, return -1.
- If all entries are False (i.e., none executed yet), return 0.
- Empty lists should return 0 (start from the first activity).
- It raises ValidationError when the lengths of the two lists differ.
"""


def test_length_mismatch_raises_validation_error():
    future = ["a", "b", "c"]
    executed = [True, False]  # mismatched length
    with pytest.raises(ValidationError):
        _ = compute_continuation_activity(future, executed)


def test_empty_lists_return_zero():
    # No activities -> start from 0
    assert compute_continuation_activity([], []) == 0


def test_all_true_returns_minus_one():
    future = ["t0", "t1", "t2"]
    executed = [True, True, True]
    assert compute_continuation_activity(future, executed) == -1


def test_all_false_returns_zero():
    # No True present; first False after conceptual "last True" is index 0
    future = ["t0", "t1", "t2"]
    executed = [False, False, False]
    assert compute_continuation_activity(future, executed) == 0


@pytest.mark.parametrize(
    "executed, expected_index",
    [
        # No True present; choose first False at index 0
        ([False], 0),
        ([False, False], 0),
        (
            [False, True, False],
            2,
        ),
        (
            [False, False, True],
            -1,
        ),
    ],
)
def test_no_true_present_or_false_before_true(executed, expected_index):  # pyright: ignore[reportMissingParameterType]
    future = [f"task{i}" for i in range(len(executed))]
    assert compute_continuation_activity(future, executed) == expected_index


@pytest.mark.parametrize(
    "executed, expected_index",
    [
        # Last True at index 0; first False after that is index 1
        ([True, False, False], 1),
        # Last True at index 1; first False after that is index 2
        ([False, True, False], 2),
        # Last True at index 2; first False after that is index 3
        ([False, False, True, False], 3),
        # Mixed with leading falses; last True at index 3; next False at 4
        ([False, False, True, True, False], 4),
        # When multiple Trues, pick the first False after the last True
        ([True, True, False, False], 2),
    ],
)
def test_first_false_after_last_true(executed, expected_index):  # pyright: ignore[reportMissingParameterType]
    future = [f"task{i}" for i in range(len(executed))]
    assert compute_continuation_activity(future, executed) == expected_index


def test_handles_single_item_cases():
    # Single executed item -> -1 (no False after last True)
    assert compute_continuation_activity(["task"], [True]) == -1
    # Single unexecuted item -> 0 (no True; first False is index 0)
    assert compute_continuation_activity(["task"], [False]) == 0
