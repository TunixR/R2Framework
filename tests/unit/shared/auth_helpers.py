from datetime import datetime, timedelta

from httpx import Headers
from sqlmodel import Session

from database.auth.models import User, UserSession


def make_user_session(user: User) -> UserSession:
    return UserSession(
        user_id=user.id,
        valid_until=datetime.now() + timedelta(hours=1),
    )


def persist_user_session(session: Session, user: User) -> UserSession:
    user_session = make_user_session(user)
    session.add(user_session)
    session.commit()
    session.refresh(user_session)
    return user_session


def make_auth_headers(user: User, session: Session) -> Headers:
    user_session = persist_user_session(session, user)
    return Headers({"Authorization": f"Bearer {user_session.id}"})
