import pytest
from datetime import datetime, timedelta, timezone

from security.utils import is_session_valid


def test_is_session_valid_rejects_naive_datetime():
    naive_future = datetime.now() + timedelta(minutes=5)
    naive_past = datetime.now() - timedelta(minutes=5)
    with pytest.raises(ValueError, match="timezone-aware"):
        _ = is_session_valid(naive_future)
    with pytest.raises(ValueError, match="timezone-aware"):
        _ = is_session_valid(naive_past)


def test_is_session_valid_with_aware_utc_datetime():
    future_valid_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    past_valid_until = datetime.now(timezone.utc) - timedelta(minutes=5)

    assert is_session_valid(future_valid_until) is True
    assert is_session_valid(past_valid_until) is False


def test_is_session_valid_with_non_utc_timezone_aware_datetime():
    ist = timezone(timedelta(hours=5, minutes=30))
    future_valid_until = datetime.now(ist) + timedelta(minutes=5)
    past_valid_until = datetime.now(ist) - timedelta(minutes=5)

    assert is_session_valid(future_valid_until) is True
    assert is_session_valid(past_valid_until) is False
