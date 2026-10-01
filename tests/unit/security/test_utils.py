from datetime import datetime, timedelta, timezone

from security.utils import is_session_valid


def test_is_session_valid_accepts_naive_future_datetime():
    valid_until = datetime.now() + timedelta(minutes=5)
    assert is_session_valid(valid_until) is True


def test_is_session_valid_accepts_naive_past_datetime():
    valid_until = datetime.now() - timedelta(minutes=5)
    assert is_session_valid(valid_until) is False


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
