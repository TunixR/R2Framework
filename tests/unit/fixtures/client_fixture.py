import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.general import get_session
from main import app


@pytest.fixture(scope="session", name="client")
def client(session: Session):
    def _get_session():
        yield session

    app.dependency_overrides[get_session] = _get_session

    yield TestClient(app)
    app.dependency_overrides.clear()
