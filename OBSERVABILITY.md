# Observability

The backend exports traces, logs, and exception events over OTLP to the self-hosted SigNoz
collector. No other observability backend is required.

## Architecture

```
uvicorn (host)  --OTLP/http :4318-->  signoz-otel-collector  -->  ClickHouse
   |  traces + logs + metrics              (signoz-net)              |
   +------------------------------------------------------->  SigNoz UI :8080
```

- The application creates one `TracerProvider` and one `LoggerProvider`
  (`observability/__init__.py`). `StrandsTelemetry` receives the same tracer provider, so agent
  spans, HTTP spans, and log records share one `trace_id`.
- HTTP spans are produced by `FastAPIInstrumentor`, which names spans after the route template
  (`PATCH /provider/{router_id}`), not the raw URL.
- The SigNoz collector (not the repository) owns the OTLP ports. The dead `otel-collector` service
  was removed from `docker/docker-compose.yml`.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `OBSERVABILITY_ENABLED` | `true` | Master switch for span/log export |
| `OTEL_SERVICE_NAME` | `r2framework-api` | Resource `service.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | SigNoz collector base URL |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | OTLP transport |
| `OTEL_TRACES_SAMPLER_ARG` | `1.0` | Trace sample ratio (`0.0`–`1.0`) |
| `DEPLOYMENT_ENVIRONMENT` | `development` | Resource `deployment.environment` |
| `LOG_LEVEL` | `INFO` | Root log level |
| `LOG_FORMAT` | `json` | `json` or `console` |
| `LOG_FILE` | empty | Optional rotating file (10 MB × 5) |

`OTEL_SDK_DISABLED=true` also disables export. Unit tests set
`OBSERVABILITY_ENABLED=false` before importing `main`, so the suite never contacts the collector.

## Running locally

```bash
uv run uvicorn main:app --port 8000
```

- `GET /health` returns `{"status": "ok"}` and is **not** traced.
- Logs are JSON lines on stdout, including `trace_id`, `span_id`, and `request_id`.
- Every response carries `X-Request-ID`; an inbound value is reused.

## What is recorded

- **Traces:** FastAPI routes, Strands agent/tool/model calls, and `strands.*` metrics.
- **Exceptions:** `record_exception(escaped=True)` plus `ERROR` span status for unhandled errors and
  for 5xx `HTTPException`s. 4xx responses are logged at WARNING without a stack trace.
  Client responses are generic (`{"detail": "Internal server error", "request_id": ...}`).
- **Logs:** exported through `RedactingLoggingHandler` → `BatchLogRecordProcessor` → OTLP. Values
  matching `api_key`, `token`, `password`, `secret`, `authorization`, robot keys, `sk-*`, and
  `Bearer ...` are replaced with `[REDACTED]`. Request bodies are never logged.
- **Redaction covers every sink.** The JSON formatter redacts the message, `exception` text, and
  event fields. The OTel handler redacts `exception.message`/`exception.stacktrace` and all
  string attributes. `record_exception` overrides both exception fields on the span event, so
  secrets inside exception text never reach SigNoz.
- **Sanitized validation errors.** Invalid recovery payloads are logged with field paths only
  (never submitted values), and the span exception carries
  `Invalid recovery payload: fields=[...]` instead of the raw Pydantic message.

Excluded from tracing: `/health`, `/docs`, `/redoc`, `/openapi.json`, `/scalar`, `/favicon.ico`.
The `http send` / `http receive` sub-spans are disabled.

### Structured log fields

Callers emit events through `observability.events.log_event`:

```python
log_event(logger, "recovery.persisted", recovery_id=rid, duration_ms=elapsed_ms(start))
```

It renders a readable `event key=value ...` message and attaches each keyword as a record extra,
which `JsonFormatter` copies into the JSON line and the OTel handler exports as a log attribute, so
SigNoz can filter without parsing messages. Only fields passed to `log_event` are copied; ad-hoc
`extra=` values are ignored by the JSON formatter. UUIDs and other objects are stringified.
Free text (`task_name`, `model`, exception `detail`) is truncated to 120 characters with `brief()`;
request bodies and screenshots are never logged.

## Recovery turn instrumentation

`/recovery/robot_exception/ws` opens one `recovery.turn` span, and every robot action gets a child
`gui.action` span (`gui.iteration`, `gui.action_type`, `gui.success`, `gui.duration_ms`). The turn
span carries `recovery.robot_key_id`, `recovery.id`, `agent.id`, `recovery.outcome`,
`recovery.success`, and truncated `recovery.task_name` / `inference.model`.

Lifecycle events (all include `event` and the relevant ids):

| Event | Level | Notes |
| --- | --- | --- |
| `recovery.auth_failed` | WARNING | Invalid/disabled robot key; connection closed with 1008 |
| `recovery.connected` | INFO | Robot key accepted, turn span started |
| `recovery.payload_received` | INFO | `ui_log_count`, `has_errored_activity`, `payload_bytes` |
| `recovery.payload_invalid` | WARNING | Field paths only; no submitted values |
| `recovery.no_gateway_agent` | ERROR | Gateway agent missing; turn marked `no_gateway_agent` |
| `recovery.persisted` | INFO | Row committed with `duration_ms` |
| `recovery.agent_started` / `recovery.agent_finished` | INFO | Agent id, model, task name, `success`, `duration_ms` |
| `recovery.turn_finished` | INFO | `outcome` (`success` / `completed_unsuccessful`), `success`, total `duration_ms` |
| `recovery.turn_failed` | ERROR | Unexpected failure; redacted exception recorded on the span |
| `recovery.client_disconnected` | INFO | Robot closed the socket first |
| `recovery.report_result*` | INFO/WARNING | `/report_result/{recovery_id}` outcomes |

GUI-agent and hook events: `gui.task_started`, `gui.screenshot` (DEBUG), `gui.action_sent`,
`gui.action_result`, `gui.action_done`, `gui.action_retry` (unparseable or failed step),
`gui.max_actions_exceeded`, `gui.task_finished`, `gui.trace_registered` (DEBUG), `tool.started`
(DEBUG), `tool.finished`, `agent.trace_started`, `agent.trace_finished`, `agent.usage`.

These logs complement the Postgres audit tables (`AgentTrace`, `ToolTrace`, `GUITrace`); they do not
duplicate payloads or screenshots.

## SigNoz queries

Error rate by exception type (last 24h):

```sql
SELECT exceptionType, count() AS errors
FROM signoz_traces.distributed_signoz_error_index_v2
WHERE timestamp > now() - INTERVAL 1 DAY
GROUP BY exceptionType
ORDER BY errors DESC
```

Latency by route:

```sql
SELECT name, count() AS calls, quantile(0.95)(durationNano) / 1e6 AS p95_ms
FROM signoz_traces.distributed_signoz_index_v3
WHERE timestamp > now() - INTERVAL 1 DAY AND name NOT LIKE '%health%'
GROUP BY name
ORDER BY p95_ms DESC
LIMIT 20
```

Logs for one trace:

```sql
SELECT timestamp, severity_text, body
FROM signoz_logs.distributed_logs_v2
WHERE timestamp > now() - INTERVAL 1 DAY
  AND attributes_string['trace_id'] = '<trace_id>'
ORDER BY timestamp
```

Recovery outcomes and timings (last 24h):

```sql
SELECT
  attributes_string['outcome'] AS outcome,
  count() AS turns,
  quantile(0.95)(toFloat64(attributes_number['duration_ms'])) AS p95_ms
FROM signoz_logs.distributed_logs_v2
WHERE timestamp > now() - INTERVAL 1 DAY
  AND attributes_string['event'] = 'recovery.turn_finished'
GROUP BY outcome
ORDER BY turns DESC
```

Recovery failures by type:

```sql
SELECT attributes_string['error_type'] AS error_type, count() AS failures
FROM signoz_logs.distributed_logs_v2
WHERE timestamp > now() - INTERVAL 1 DAY
  AND attributes_string['event'] IN ('recovery.turn_failed', 'gui.action_retry')
GROUP BY error_type
ORDER BY failures DESC
```

One recovery end to end:

```sql
SELECT timestamp, body, attributes_string
FROM signoz_logs.distributed_logs_v2
WHERE timestamp > now() - INTERVAL 1 DAY
  AND attributes_string['recovery_id'] = '<recovery_id>'
ORDER BY timestamp
```

## Containerized backend

If the API runs in Docker, join the `signoz-net` network and change only the endpoint:

```yaml
services:
  backend:
    networks:
      - signoz-net
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://signoz-otel-collector:4318"

networks:
  signoz-net:
    external: true
```

## Known limitation

SigNoz `v0.108` indexes exceptions from **span events** (`record_exception`), which is what this
code emits. The log-based `.exception` convention requires collector `>= 0.144.3` and SigNoz
`>= 0.120.0`; upgrading later needs no application changes.

## Tests

```bash
uv run pytest tests/unit/observability -q
```

The tests use `InMemorySpanExporter` / `InMemoryLogRecordExporter` and never make network calls.
