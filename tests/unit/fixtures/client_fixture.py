import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from database.general import get_session
from main import app


@pytest.fixture(scope="session", name="client")
def client(engine: Engine):
    def _get_session():
        yield Session(engine)

    app.dependency_overrides[get_session] = _get_session

    yield TestClient(app)
    app.dependency_overrides.clear()
