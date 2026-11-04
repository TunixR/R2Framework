"""Read and delete test telemetry in a live SigNoz through its ClickHouse.

SigNoz has no API to delete individual spans or logs, so the tests talk to
ClickHouse directly. Every run exports under a unique ``service.name``, which
is what reads are scoped to and what cleanup deletes.

Connection, in order of preference:
- ``SIGNOZ_CLICKHOUSE_URL`` (e.g. ``http://localhost:8123``): ClickHouse HTTP.
- otherwise ``docker exec`` into ``SIGNOZ_CLICKHOUSE_CONTAINER``
  (default ``signoz-clickhouse``), which works with the stock SigNoz compose
  file where ClickHouse is not published on the host.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404 - test helper running a fixed docker command
import time
import urllib.request
from collections.abc import Callable
from typing import Any

POLL_TIMEOUT_S = float(os.getenv("SIGNOZ_POLL_TIMEOUT", "60"))
POLL_INTERVAL_S = 1.0

type Row = dict[str, Any]


class SignozClickHouse:
    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self._url = os.getenv("SIGNOZ_CLICKHOUSE_URL")
        self._container = os.getenv("SIGNOZ_CLICKHOUSE_CONTAINER", "signoz-clickhouse")

    # --- Transport -----------------------------------------------------------

    def execute(self, sql: str) -> str:
        if self._url:
            request = urllib.request.Request(
                self._url, data=sql.encode(), method="POST"
            )
            with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - test-only URL from env
                return response.read().decode()
        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError("docker not found and SIGNOZ_CLICKHOUSE_URL is unset")
        result = subprocess.run(  # nosec B603 - fixed argv, no shell
            [docker, "exec", "-i", self._container, "clickhouse-client"],
            input=sql,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ClickHouse query failed: {result.stderr.strip()}")
        return result.stdout

    def rows(self, sql: str) -> list[Row]:
        output = self.execute(f"{sql} FORMAT JSONEachRow")
        return [json.loads(line) for line in output.splitlines() if line.strip()]

    def ping(self) -> None:
        self.execute("SELECT 1")

    # --- Reads (scoped to this run's service) --------------------------------

    def spans(self, where: str = "1") -> list[Row]:
        return self.rows(
            "SELECT trace_id, span_id, parent_span_id, name, kind_string, "
            "status_code_string, has_error, duration_nano, attributes_string, "
            "attributes_number, attributes_bool, events "
            "FROM signoz_traces.distributed_signoz_index_v3 "
            f"WHERE resource_string_service$$name = {self._quote(self.service_name)} "
            f"AND ({where}) ORDER BY timestamp"
        )

    def logs(self, where: str = "1") -> list[Row]:
        return self.rows(
            "SELECT trace_id, span_id, severity_text, body, attributes_string, "
            "attributes_number, attributes_bool "
            "FROM signoz_logs.distributed_logs_v2 "
            f"WHERE resources_string['service.name'] = {self._quote(self.service_name)} "
            f"AND ({where}) ORDER BY timestamp"
        )

    def errors(self, trace_id: str) -> list[Row]:
        return self.rows(
            "SELECT exceptionType, exceptionMessage, exceptionStacktrace "
            "FROM signoz_traces.distributed_signoz_error_index_v2 "
            f"WHERE serviceName = {self._quote(self.service_name)} "
            f"AND traceID = {self._quote(trace_id)}"
        )

    def wait_for[T](
        self, fetch: Callable[[], list[T]], *, at_least: int = 1
    ) -> list[T]:
        """Poll until ``fetch`` returns ``at_least`` rows (ingestion is async)."""
        deadline = time.monotonic() + POLL_TIMEOUT_S
        while True:
            found = fetch()
            if len(found) >= at_least or time.monotonic() > deadline:
                return found
            time.sleep(POLL_INTERVAL_S)

    def wait_until_settled(self, quiet_s: float = 3.0) -> None:
        """Wait until no new rows arrive for ``quiet_s``, so cleanup sees them all."""
        deadline = time.monotonic() + POLL_TIMEOUT_S
        last = (-1, -1)
        while time.monotonic() < deadline:
            counts = (len(self.spans()), len(self.logs()))
            if counts == last:
                return
            last = counts
            time.sleep(quiet_s)

    # --- Cleanup -------------------------------------------------------------

    def delete_service_data(self) -> None:
        """Delete every span, log, exception and resource row of this service.

        Attribute key/value autocomplete metadata (``tag_attributes_v2``,
        ``*_attribute_keys``) is not scoped by service and is left to the
        SigNoz retention TTL.
        """
        service = self._quote(self.service_name)
        trace_ids = [
            row["trace_id"]
            for row in self.rows(
                "SELECT DISTINCT trace_id FROM signoz_traces.signoz_index_v3 "
                f"WHERE resource_string_service$$name = {service}"
            )
        ]
        traces = ", ".join(self._quote(trace_id) for trace_id in trace_ids) or "''"
        by_service = f"serviceName = {service}"
        by_label = f"simpleJSONExtractString(labels, 'service.name') = {service}"
        deletions = [
            ("signoz_traces.trace_summary", f"trace_id IN ({traces})"),
            ("signoz_traces.signoz_spans", f"traceID IN ({traces})"),
            (
                "signoz_traces.signoz_index_v3",
                f"resource_string_service$$name = {service}",
            ),
            ("signoz_traces.signoz_index_v2", by_service),
            ("signoz_traces.signoz_error_index_v2", by_service),
            ("signoz_traces.durationSort", by_service),
            ("signoz_traces.top_level_operations", by_service),
            ("signoz_traces.traces_v3_resource", by_label),
            ("signoz_logs.logs_v2", f"resources_string['service.name'] = {service}"),
            ("signoz_logs.logs_v2_resource", by_label),
        ]
        for table, condition in deletions:
            self.execute(
                f"ALTER TABLE {table} DELETE WHERE {condition} SETTINGS mutations_sync = 2"
            )

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
