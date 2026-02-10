from datetime import datetime, timedelta

from httpx import Headers
from sqlmodel import Session

from database.auth.models import User, UserSession
from security.token import TokenData
from security.utils import generate_session_token


def make_user_session(
    user: User, valid_duration: timedelta = timedelta(hours=1)
) -> UserSession:
    return UserSession(
        user_id=user.id,
        valid_until=datetime.now() + valid_duration,
    )


def persist_user_session(
    session: Session, user: User, valid_duration: timedelta = timedelta(hours=1)
) -> UserSession:
    user_session = make_user_session(user, valid_duration)
    session.add(user_session)
    session.commit()
    session.refresh(user_session)
    return user_session


def make_access_token(
    session: Session, user: User, valid_duration: timedelta = timedelta(hours=1)
) -> str:
    user_session = persist_user_session(session, user, valid_duration)
    data = TokenData(username=user.username, session_id=str(user_session.id))
    return generate_session_token(data)


def make_auth_headers(
    user: User, session: Session, valid_duration: timedelta = timedelta(hours=1)
) -> Headers:
    access_token = make_access_token(session, user, valid_duration)
    return Headers({"Authorization": f"Bearer {access_token}"})
