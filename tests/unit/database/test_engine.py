import pytest
from fastapi import HTTPException
from sqlmodel import Session

from database.engine import commit_or_500


class _FailingSession:
    def __init__(self) -> None:
        self.rolled_back = False

    def commit(self) -> None:
        raise RuntimeError("db password=hunter2")

    def rollback(self) -> None:
        self.rolled_back = True


def test_commit_or_500_rolls_back_and_hides_the_cause() -> None:
    session = _FailingSession()

    with pytest.raises(HTTPException) as excinfo:
        commit_or_500(session, "create agent")  # pyright: ignore[reportArgumentType]

    assert session.rolled_back
    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "Failed to create agent."
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_commit_or_500_commits(session: Session) -> None:
    commit_or_500(session, "noop")
