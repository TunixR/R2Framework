from datetime import datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from sqlmodel import Session

from database.auth.models import User, UserRole
from middlewares.auth import get_current_user, require_admin
from security.token import TokenData
from security.utils import generate_session_token
from settings import ALGORITHM, SECRET_KEY
from tests.unit.shared.auth_helpers import make_access_token, persist_user_session


def _make_token(*, username: str, session_id: str) -> str:
    return generate_session_token(TokenData(username=username, session_id=session_id))


def test_get_current_user_valid_token(session: Session, mock_user: User):
    token = make_access_token(session, mock_user)
    current_user = get_current_user(session=session, token=token)
    assert current_user.id == mock_user.id


def test_get_current_user_invalid_token(session: Session):
    with pytest.raises(HTTPException) as exc:
        _ = get_current_user(session=session, token="not-a-jwt")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Not authenticated"


def test_get_current_user_missing_claims(session: Session):
    payload = {
        "username": "dev",
        "exp": datetime.now() + timedelta(minutes=5),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        _ = get_current_user(session=session, token=token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Could not validate credentials"


def test_get_current_user_invalid_session(session: Session):
    token = _make_token(username="dev", session_id=str(uuid4()))
    with pytest.raises(HTTPException) as exc:
        _ = get_current_user(session=session, token=token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid session"


def test_get_current_user_expired_session(session: Session, mock_user: User):
    token = make_access_token(session, mock_user, valid_duration=timedelta(seconds=-1))
    with pytest.raises(HTTPException) as exc:
        _ = get_current_user(session=session, token=token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Session expired"


def test_get_current_user_disabled_user(session: Session, mock_user_disabled: User):
    token = make_access_token(session, mock_user_disabled)
    with pytest.raises(HTTPException) as exc:
        _ = get_current_user(session=session, token=token)
    assert exc.value.status_code == 403
    assert exc.value.detail == "User account is disabled"


def test_get_current_user_username_mismatch(session: Session):
    user = User(
        id=uuid4(),
        username="dev",
        password="hashed",
        role=UserRole.DEVELOPER,
        enabled=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    user_session = persist_user_session(session, user)

    data = TokenData(username="notdev", session_id=str(user_session.id))
    token = generate_session_token(data)
    with pytest.raises(HTTPException) as exc:
        _ = get_current_user(session=session, token=token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Could not validate credentials"


def test_require_admin_allows_admin(mock_admin: User):
    assert require_admin(current_user=mock_admin).id == mock_admin.id


def test_require_admin_blocks_non_admin(mock_user: User):
    with pytest.raises(HTTPException) as exc:
        _ = require_admin(current_user=mock_user)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Administrator role required"
