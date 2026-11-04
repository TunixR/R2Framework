"""Happy paths against the real Postgres: version, schema and a write round trip."""

from __future__ import annotations

import uuid

from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel, select

import database.general  # noqa: F401 - registers every table on SQLModel.metadata
from database.keys.models import RobotKey

MIN_SERVER_VERSION = 180000  # docker/postgres pins Postgres 18


def test_server_is_the_pinned_major_version(pg_engine: Engine) -> None:
    with pg_engine.connect() as connection:
        version = connection.execute(text("SHOW server_version_num")).scalar_one()

    assert int(version) >= MIN_SERVER_VERSION


def test_database_has_a_table_for_every_model(pg_engine: Engine) -> None:
    existing = set(inspect(pg_engine).get_table_names())

    missing = set(SQLModel.metadata.tables) - existing
    assert not missing, f"tables missing from the database: {sorted(missing)}"


def test_model_round_trip_inside_a_transaction(
    pg_engine: Engine, pg_session: Session
) -> None:
    name = f"it-{uuid.uuid4().hex[:12]}"
    pg_session.add(RobotKey(name=name, key_hash=uuid.uuid4().hex, key_last4="abcd"))
    pg_session.flush()

    stored = pg_session.exec(select(RobotKey).where(RobotKey.name == name)).one()
    assert stored.enabled is True  # server-side defaults and types round-trip

    # Not committed: other connections do not see it, and the fixture rolls it back.
    with Session(pg_engine) as other:
        assert other.exec(select(RobotKey).where(RobotKey.name == name)).first() is None


def test_monitoring_role_is_read_only(pg_engine: Engine) -> None:
    """The otel-agent's role (docker/postgres/initdb) can read stats and nothing more."""
    with pg_engine.connect() as connection:
        role = connection.execute(
            text(
                "SELECT r.rolsuper, r.rolcreaterole, r.rolcreatedb, "
                "pg_has_role(r.oid, 'pg_monitor', 'member') AS monitor "
                "FROM pg_roles r WHERE r.rolname = 'otel_monitor'"
            )
        ).one_or_none()

    assert role is not None, "otel_monitor role missing (created on first init)"
    assert role.monitor is True
    assert (role.rolsuper, role.rolcreaterole, role.rolcreatedb) == (
        False,
        False,
        False,
    )
