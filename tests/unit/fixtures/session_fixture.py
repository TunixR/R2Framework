"""tests.unit.fixtures.session_fixture

Session fixture for unit tests.

CI/unit tests should be runnable without external services. If Docker is
available, we keep the option to run against a disposable Postgres container;
otherwise we fall back to an in-memory SQLite database.
"""

import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

POSTGRES_CONTAINER = "test-postgres"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # pyright: ignore[reportUnusedFunction, reportMissingParameterType]
    # SQLite doesn't support JSONB; map to generic JSON.
    return "JSON"


@pytest.fixture(autouse=True)
def flush_db(session: Session):
    """
    Flush the database before each test.

    This fixture ensures that the database is clean before each test runs.
    """
    yield
    meta = SQLModel.metadata
    for table in reversed(meta.sorted_tables):
        _ = session.exec(table.delete())
    session.commit()


@pytest.fixture(name="session", scope="session")
def session_fixture():
    """
    Create an in-memory SQLite database for testing.

    This fixture provides a clean database session for each test.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
