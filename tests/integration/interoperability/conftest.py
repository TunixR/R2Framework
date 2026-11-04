"""Fixtures for the interoperability tests.

These check that the services talk to each other: calls to Postgres and S3 must
show up in SigNoz through the otel-agent (docker/observability/agent). They need
the whole development stack (``docker/compose.dev.yaml``) and are skipped when
any piece is missing.

Infrastructure metrics are scraped every 60 s, so polls wait longer than the
SigNoz suite's default.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from dataclasses import dataclass

import botocore.exceptions as bex
import pytest
import pytest_asyncio
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import OperationalError

import settings
from s3.utils import S3Client
from tests.integration.observability.signoz import SignozClickHouse

# One scrape interval (60 s) plus the agent's and the collector's batching.
INFRA_POLL_TIMEOUT_S = max(settings.SIGNOZ_POLL_TIMEOUT, 150.0)
POLL_INTERVAL_S = 2.0


def wait_until[T](fetch: Callable[[], T], done: Callable[[T], bool]) -> T:
    """Poll ``fetch`` until ``done`` accepts its result or the timeout passes."""
    deadline = time.monotonic() + INFRA_POLL_TIMEOUT_S
    while True:
        result = fetch()
        if done(result) or time.monotonic() > deadline:
            return result
        time.sleep(POLL_INTERVAL_S)


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class Counter:
    """A cumulative metric in SigNoz, read as increments rather than totals.

    Totals are meaningless across restarts (the service's counter starts again
    from zero), so tests take a ``baseline`` before acting and then ask for the
    ``increase`` since, treating a drop as a restart like Prometheus does.
    """

    clickhouse: SignozClickHouse
    metric: str
    labels: Mapping[str, str]

    def _latest(self, time_filter: str) -> dict[str, float]:
        """Latest sample of each series matching ``labels``, by fingerprint."""
        label_filter = " AND ".join(
            f"JSONExtractString(labels, '{key}') = '{value}'"
            for key, value in self.labels.items()
        )
        rows = self.clickhouse.rows(
            "SELECT toString(fingerprint) AS series, "
            "argMax(value, unix_milli) AS value "
            "FROM signoz_metrics.distributed_samples_v4 "
            f"WHERE metric_name = '{self.metric}' AND {time_filter} "
            "AND fingerprint IN ("
            "SELECT fingerprint FROM signoz_metrics.distributed_time_series_v4 "
            f"WHERE metric_name = '{self.metric}' AND {label_filter}) "
            "GROUP BY fingerprint"
        )
        return {row["series"]: float(row["value"]) for row in rows}

    def baseline(self, at_ms: int) -> dict[str, float]:
        return self._latest(f"unix_milli <= {at_ms}")

    def increase(self, baseline: Mapping[str, float], since_ms: int) -> float:
        total = 0.0
        for series, value in self._latest(f"unix_milli > {since_ms}").items():
            previous = baseline.get(series, 0.0)
            total += value - previous if value >= previous else value  # reset
        return total

    def wait_for_increase(
        self, baseline: Mapping[str, float], since_ms: int, at_least: float
    ) -> float:
        return wait_until(
            lambda: self.increase(baseline, since_ms), lambda grown: grown >= at_least
        )


@pytest.fixture(scope="session", autouse=True)
def _announce_wait(request: pytest.FixtureRequest) -> None:
    """Say up front why this folder is slow (shown even with ``-q``)."""
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.ensure_newline()
        reporter.write_line(
            "interoperability: waiting for infrastructure telemetry, up to "
            f"{INFRA_POLL_TIMEOUT_S:.0f} s per test (metrics are scraped every 60 s; "
            "usually 1.5-3 min for the folder)",
            yellow=True,
        )


@pytest.fixture(scope="session")
def clickhouse() -> SignozClickHouse:
    # Raw queries only: the service-scoped helpers and cleanup are not used here.
    client = SignozClickHouse("interoperability")
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 - any failure means "no SigNoz here"
        pytest.skip(f"SigNoz ClickHouse not reachable: {exc}")
    return client


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    engine = create_engine(settings.POSTGRES_URL, connect_args={"connect_timeout": 3})
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"Postgres not reachable: {exc}")
    yield engine
    engine.dispose()


@pytest_asyncio.fixture
async def s3_bucket() -> AsyncIterator[str]:
    try:
        async with S3Client._client() as s3c:  # pyright: ignore[reportGeneralTypeIssues,reportPrivateUsage]
            try:
                await s3c.head_bucket(Bucket=settings.S3_BUCKET)
            except bex.ClientError:
                await s3c.create_bucket(Bucket=settings.S3_BUCKET)
    except Exception as exc:  # noqa: BLE001 - any failure means "no S3 here"
        pytest.skip(f"S3 not reachable at {settings.S3_URL}: {exc}")
    yield settings.S3_BUCKET
