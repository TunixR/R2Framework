import numpy as np
from pydantic import ValidationError
from strands import tool


@tool(
    description="Compute the continuation activity index based on future activities and their execution status."
)
def compute_continuation_activity(
    future_activities: list[str], executed_status: list[bool]
) -> int:
    if len(future_activities) != len(executed_status):
        raise ValidationError(
            "Length of future_activities and executed_status must be the same.",
            [],
        )

    arr = np.array(executed_status)
    if not arr.any():  # None executed
        return 0

    rev_idx = int(np.argmax(arr[::-1]))

    if rev_idx == 0:  # All executed
        return -1

    return arr.size - rev_idx
