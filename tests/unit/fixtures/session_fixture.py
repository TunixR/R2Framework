import pytest
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


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


@pytest.fixture(name="engine", scope="session")
def engine_fixture():
    """
    Create an in-memory SQLite database for testing.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    SQLModel.metadata.create_all(engine)
    yield engine


@pytest.fixture(name="session", scope="session")
def session_fixture(engine: Engine):
    """
    This fixture provides a clean database session the test session.
    """
    with Session(engine) as session:
        yield session
