"""
Session fixture for unit tests.

Provides a clean in-memory SQLite database session for each test.
"""

import subprocess
import time

import psycopg2
import pytest
from sqlmodel import Session, SQLModel, create_engine

POSTGRES_CONTAINER = "test-postgres"


def start_postgres():
    _ = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            POSTGRES_CONTAINER,
            "-e",
            "POSTGRES_PASSWORD=postgres",
            "-e",
            "POSTGRES_DB=testdb",
            "-p",
            "54329:5432",
            "postgres:16",
        ],
        check=True,
    )

    for _ in range(30):
        try:
            psycopg2.connect(
                "postgresql://postgres:postgres@localhost:54329/testdb"
            ).close()
            print("Postgres is up and running")
            return
        except Exception:
            time.sleep(0.5)

    raise RuntimeError("Postgres did not start")


def stop_postgres():
    _ = subprocess.run(["docker", "stop", POSTGRES_CONTAINER], check=False)


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
    start_postgres()
    engine = create_engine(
        "postgresql+psycopg2://postgres:postgres@localhost:54329/testdb"
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    stop_postgres()
