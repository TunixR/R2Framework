"""Fixtures for the Postgres integration tests.

The suite needs the Postgres configured in ``settings.py`` / ``.env`` (in
development, ``docker/compose.dev.yaml``) and is skipped when it is not
reachable. Tests never commit: each one runs in a transaction that is rolled
back, so the database is left as it was.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

import settings


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    engine = create_engine(settings.POSTGRES_URL, connect_args={"connect_timeout": 3})
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(
            f"Postgres not reachable at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}: {exc}"
        )
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back at the end of the test."""
    with pg_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as session:
            yield session
        transaction.rollback()
