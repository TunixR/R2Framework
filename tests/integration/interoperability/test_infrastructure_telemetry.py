"""Calls to Postgres and S3 produce telemetry in SigNoz.

Each test makes real calls, then reads SigNoz's ClickHouse until the matching
log line arrives or the matching counter has grown by at least the number of
calls: service → Docker logs / metrics endpoint → otel-agent →
signoz-collector → ClickHouse.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

import settings
from s3.utils import S3Client
from tests.integration.interoperability.conftest import Counter, now_ms, wait_until
from tests.integration.observability.signoz import Row, SignozClickHouse


def test_postgres_errors_reach_signoz_as_parsed_logs(
    pg_engine: Engine, clickhouse: SignozClickHouse
) -> None:
    marker = f"r2_interop_{uuid.uuid4().hex[:12]}"
    with pg_engine.connect() as connection, pytest.raises(ProgrammingError):
        connection.execute(text(f"SELECT {marker}"))

    query = (
        "SELECT severity_text, body, attributes_string "
        "FROM signoz_logs.distributed_logs_v2 "
        "WHERE resources_string['service.name'] = 'postgres' "
        f"AND body LIKE '%{marker}%' AND severity_text = 'ERROR'"
    )
    try:
        logs: list[Row] = wait_until(lambda: clickhouse.rows(query), bool)

        assert logs, f"no Postgres error log containing {marker} reached SigNoz"
        attributes = logs[0]["attributes_string"]
        assert attributes["db.namespace"] == settings.POSTGRES_DB
        assert attributes["db.user"] == settings.POSTGRES_USER
    finally:
        clickhouse.execute(
            "ALTER TABLE signoz_logs.logs_v2 DELETE "
            f"WHERE body LIKE '%{marker}%' SETTINGS mutations_sync = 2"
        )


# Enough activity to stand out from the background (the agent's own queries,
# other clients): the counters must grow by at least this much.
PG_TRANSACTIONS = 20
S3_PUTS = 3


def test_postgres_commits_are_counted_in_signoz(
    pg_engine: Engine, clickhouse: SignozClickHouse
) -> None:
    commits = Counter(
        clickhouse,
        "postgresql.commits",
        {"service.name": "postgres", "postgresql.database.name": settings.POSTGRES_DB},
    )
    started = now_ms()
    baseline = commits.baseline(started)
    for _ in range(PG_TRANSACTIONS):
        with pg_engine.begin() as connection:
            connection.execute(text("SELECT 1"))

    grown = commits.wait_for_increase(baseline, started, PG_TRANSACTIONS)

    assert grown >= PG_TRANSACTIONS, (
        f"postgresql.commits grew by {grown}, expected >= {PG_TRANSACTIONS}"
    )


@pytest.mark.asyncio
async def test_s3_puts_are_counted_in_signoz(
    s3_bucket: str, clickhouse: SignozClickHouse
) -> None:
    puts = Counter(
        clickhouse,
        "SeaweedFS_s3_request_total",
        {"service.name": "seaweedfs-s3", "type": "PUT", "bucket": s3_bucket},
    )
    started = now_ms()
    baseline = puts.baseline(started)
    keys = [
        await S3Client.upload_bytes(b"interop", "text/plain", bucket=s3_bucket)
        for _ in range(S3_PUTS)
    ]
    try:
        grown = puts.wait_for_increase(baseline, started, S3_PUTS)

        assert grown >= S3_PUTS, (
            f"SeaweedFS_s3_request_total (PUT) grew by {grown}, expected >= {S3_PUTS}"
        )
    finally:
        await S3Client.bulk_delete_objects(keys, bucket=s3_bucket)
