from typing import Annotated

from fastapi import HTTPException, status
from fastapi.params import Depends
from sqlmodel import Session, create_engine

from settings import POSTGRES_URL

postgres_url = POSTGRES_URL

general_engine = create_engine(postgres_url)


def get_session():
    with Session(general_engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def commit_or_500(session: Session, action: str) -> None:
    """Commit, or roll back and raise a generic 500.

    The global HTTP exception handler logs the chained database error and
    records it on the request span, so callers need no logging of their own.
    """
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {action}.",
        ) from exc
