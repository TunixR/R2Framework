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

Like every other setting, these are read in `settings.py` (from `.env`, see `.env.example`);
`ObservabilitySettings.from_settings()` collects them, and tests override fields through it.
Export always uses OTLP over HTTP/protobuf.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OBSERVABILITY_ENABLED` | `true` | Master switch for span/log export |
| `OTEL_SERVICE_NAME` | `r2framework-api` | Resource `service.name` |
| `OTEL_SERVICE_NAMESPACE` | `r2framework` | Resource `service.namespace` |
| `DEPLOYMENT_ENVIRONMENT` | `development` | Resource `deployment.environment` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | SigNoz collector base URL |
| `OTEL_TRACES_SAMPLER_ARG` | `1.0` | Trace sample ratio (clamped to `0.0`–`1.0`) |
| `LOG_LEVEL` | `INFO` | Root log level |
| `LOG_FORMAT` | `json` | `json` or `console` |
| `LOG_FILE` | empty | Optional rotating log file |
| `LOG_FILE_MAX_BYTES` | `10000000` | Rotation size of `LOG_FILE` |
| `LOG_FILE_BACKUP_COUNT` | `5` | Rotated files kept |
| `STRANDS_LOG_LEVEL` | `INFO` | Level of the `strands` logger |
| `TELEMETRY_MAX_TEXT_LENGTH` | `120` | Truncation of free text on spans and events (`brief()`) |

`OTEL_SDK_DISABLED=true` also disables export. Unit tests set
`OBSERVABILITY_ENABLED=false` before importing `main`, so the suite never contacts the collector.

## Running locally

```bash
uv run uvicorn main:app --port 8000
```

- `GET /health` returns `{"status": "ok"}` and is **not** traced.
- Logs are JSON lines on stdout, including `trace_id`, `span_id`, and `request.id`.
- Every response carries `X-Request-ID`; an inbound value is reused.

## What is recorded

- **Traces:** FastAPI routes, Strands agent/tool/model calls, and `strands.*` metrics.
- **Exceptions:** `record_exception(escaped=True)` plus `ERROR` span status for unhandled errors and
  for 5xx `HTTPException`s. 4xx responses are logged at WARNING without a stack trace.
  Client responses are generic (`{"detail": "Internal server error", "request_id": ...}`).
- **Logs:** exported through the `LoggingHandler` from `opentelemetry-instrumentation-logging` →
  `RedactingLogRecordProcessor` → `BatchLogRecordProcessor` → OTLP. Request bodies are never
  logged.
- **Redaction (best effort, see [Privacy](#privacy)).** Values matching `api_key`, `token`,
  `password`, `secret`, `authorization`, robot keys, `sk-*`, and `Bearer ...` are replaced with
  `[REDACTED]` in log bodies, log attributes (including `exception.*`), the JSON formatter, and
  exception events recorded through `record_exception`.
- **Sanitized validation errors.** Invalid recovery payloads are logged with field paths only
  (never submitted values), and the span exception carries
  `Invalid recovery payload: fields=[...]` instead of the raw Pydantic message.

Excluded from tracing: `/health`, `/docs`, `/redoc`, `/openapi.json`, `/scalar`, `/favicon.ico`.
The `http send` / `http receive` sub-spans are disabled.

### Spans or logs?

Anything with a duration or a parent is a **span**; a **log event** is reserved for something that
happened at a point in time and is not already a span: a rejection, a recovered failure, a
misconfiguration, an accounting record. Successful work produces no logs. Strands already traces
agent invocations (`invoke_agent`), model calls (`chat`, with `gen_ai.usage.*`) and tool calls
(`execute_tool <name>`), so the code enriches those spans instead of logging around them.

### Naming

Names follow the OpenTelemetry rules: lowercase, dot-separated namespaces, `snake_case` within a
component. Standard semantic-convention keys are reused where they exist (`error.type`,
`exception.message`, `client.address`, `http.*`, `url.path`, `gen_ai.usage.*`); project keys live
under `recovery.*`, `robot_key.*`, `agent.*`, `agent_trace.*`, `gui.*` and `request.*`. All of them
are defined in `observability/attributes.py`; change them there and here together.

Log events are emitted with `observability.events.log_event`:

```python
log_event(
    logger,
    attrs.EVENT_RECOVERY_TURN_FAILED,
    {attrs.ERROR_TYPE: "RuntimeError"},
    logging.ERROR,
)
```

The event name travels as `otel.event.name`, which the logging handler promotes to the OTLP
LogRecord `event_name` field. SigNoz `v0.108` (collector `v0.129`) drops that field, so
`EventNameAttributeProcessor` also exports it as the `event.name` attribute; filter events with
`attributes_string['event.name']`. Each attribute is exported under its key and copied into the JSON
line; ad-hoc `extra=` values are not. Free text (task names, process models, exception messages)
is truncated to 120 characters with `brief()`.

## Recovery turn instrumentation

```
WebSocket /recovery/robot_exception/ws            (FastAPI instrumentation)
└── recovery.turn
    ├── recovery.persist                           (RobotException + RecoveryContext insert)
    └── invoke_agent <gateway>                     (Strands)
        ├── chat                                   (Strands, gen_ai.usage.*)
        └── execute_tool <gui agent>               (Strands, enriched with gui.task.*)
            ├── gui.screenshot
            ├── invoke_agent / chat                (UI-TARS, Strands)
            └── gui.action                         (one per robot action)
                └── gui.screenshot
```

| Span | Attributes |
| --- | --- |
| `recovery.turn` | `robot_key.id`, `agent.id`, `recovery.id`, `recovery.outcome` (`success`, `completed_unsuccessful`, `invalid_payload`, `client_disconnected`, `no_gateway_agent`, `internal_error`), `recovery.success`, `recovery.task_name`, `recovery.platform`, `recovery.os`, `recovery.process_model`, `recovery.payload.size`, `recovery.payload.ui_log_count`, `recovery.payload.has_errored_activity`, `recovery.payload.invalid_fields` |
| `recovery.persist` | none |
| `invoke_agent` (Strands) | `agent.id`, `agent_trace.id` (joins the trace to the `AgentTrace` row) |
| `execute_tool` (GUI agent) | `gui.task.name`, `gui.task.process_model`, `gui.task.ui_log_count`, `gui.task.has_errored_activity`, `gui.task.iterations`, `gui.task.outcome` (`done`, `max_actions_exceeded`, `unparseable_response`) |
| `gui.action` | `gui.action.iteration`, `gui.action.type`, `gui.action.success`; failed actions carry a redacted exception |
| `gui.screenshot` | `gui.screenshot.width`, `gui.screenshot.height`, `gui.screenshot.size` |
| `POST /recovery/report_result/{recovery_id}` | `recovery.id`, `robot_key.id`, `recovery.success` |
| `recovery.eval` (`/evals/recovery/eval/ws`) | `robot_key.id`, `agent.id`; unexpected failures carry a redacted exception |

Log events:

| Event | Level | Attributes |
| --- | --- | --- |
| `recovery.auth_failed` | WARN | `error.type`, `client.address` |
| `recovery.keep_alive_failed` | WARN | `error.type` |
| `recovery.no_gateway_agent` | ERROR | none |
| `recovery.payload_invalid` | WARN | `recovery.payload.invalid_fields` (paths only) |
| `recovery.turn_failed` | ERROR | `recovery.id`, `error.type`, redacted `exception.*` |
| `recovery.eval_invalid` | WARN | `error.type` |
| `gui.action_retry` | WARN | `gui.action.iteration`, `error.type`, `exception.message` |
| `gui.max_actions_exceeded` | WARN | `gui.task.max_actions` |
| `agent.usage` | INFO | `agent.id`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `agent.cost` |
| `http.server_error`, `http.unhandled_exception` | ERROR | `http.request.method`, `url.path`, `http.response.status_code` or `error.type` |
| `http.client_error`, `http.validation_failed` | WARN | the same request keys, `exception.message` or `request.invalid_fields` |

Every event carries the active trace and span ids, so filtering logs by trace shows every problem
within a recovery. The Postgres audit tables (`AgentTrace`, `ToolTrace`, `GUITrace`) remain the
record of payloads, messages and screenshots; telemetry does not duplicate them.

### Where the instrumentation lives

Business code reports milestones; small per-flow telemetry objects decide how they become spans,
attributes and events:

- `observability/instrumentation/recovery.py`: `recovery_turn()` / `RecoveryTurnTelemetry` for the recovery
  websocket (`payload_received`, `persisting`, `persisted`, `completed`, `invalid_payload`,
  `failed`, ...).
- `observability/instrumentation/gui_agent.py`: `GuiTaskTelemetry` for the GUI agent loop (`screenshot`,
  `action`, `retry`, `done`, `max_actions_exceeded`, `stopped`).

## Conventions for new code

- **Span or event?** Work with a duration, or that other work nests under, is a span. A point-in-
  time problem that is not already a span (rejection, recovered failure, misconfiguration,
  accounting) is a `log_event`. Do not log "started"/"finished" pairs or successful steps.
- **Check what is already traced.** FastAPI requests and websockets, Strands agents, model calls and
  tool calls already have spans. Add attributes to the current span instead of wrapping it again.
- **Names.** Add every span, event and attribute name to `observability/attributes.py`; reuse a
  semantic-convention key when one exists; keep project keys under a domain namespace, lowercase
  and dotted. Update the tables above in the same change.
- **Values.** Never export payloads, prompts, UI log `input` values, screenshots or credentials.
  Describe data by shape (counts, sizes, field paths) and pass free text through `brief()`.
- **Exceptions.** Use `observability.exceptions.record_exception` (redacted) rather than
  `span.record_exception`. Expected domain failures are WARN events; unexpected ones are ERROR events
  with `exc_info` plus `record_exception`. Never return raw exception text to clients.
- **Keep business code readable.** When a flow needs more than one or two telemetry calls, give it
  a telemetry object in `observability/instrumentation/` (see above) and test that object with
  in-memory exporters.
- **Correlate with the database.** When code creates an audit row (`RobotException`,
  `AgentTrace`, ...), put its id on the current span (`recovery.id`, `agent_trace.id`).

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

Recovery outcomes and turn latency (last 24h):

```sql
SELECT
  attributes_string['recovery.outcome'] AS outcome,
  count() AS turns,
  quantile(0.95)(durationNano) / 1e6 AS p95_ms
FROM signoz_traces.distributed_signoz_index_v3
WHERE timestamp > now() - INTERVAL 1 DAY AND name = 'recovery.turn'
GROUP BY outcome
ORDER BY turns DESC
```

GUI actions by type and success:

```sql
SELECT
  attributes_string['gui.action.type'] AS action_type,
  attributes_bool['gui.action.success'] AS success,
  count() AS actions,
  quantile(0.95)(durationNano) / 1e6 AS p95_ms
FROM signoz_traces.distributed_signoz_index_v3
WHERE timestamp > now() - INTERVAL 1 DAY AND name = 'gui.action'
GROUP BY action_type, success
ORDER BY actions DESC
```

One recovery end to end: find the `recovery.turn` span by its `recovery.id` attribute in the trace
explorer, open its trace, and use the related-logs view to see every event logged within it.

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

### Integration tests against a live SigNoz

```bash
uv run pytest tests/integration/observability -q
```

One happy path per feature, exported through the real OTLP pipeline and read back from SigNoz:
request tracing with `request.id`, typed and redacted log events in the request trace, client
errors as WARN events, unhandled errors in the Exceptions index (redacted), a full recovery
websocket turn (websocket span → `recovery.turn` → `recovery.persist` and a real Strands agent,
joined to the `RobotException` row), and GUI action and screenshot spans.

Each run exports under a unique `service.name` (`r2framework-it-<random>`). At the end the suite
waits for ingestion to settle, deletes that service's rows from ClickHouse (SigNoz has no delete
API) and asserts nothing is left. Attribute autocomplete metadata is left to retention.
The tests are skipped when SigNoz is not reachable.

The tests export to `OTEL_EXPORTER_OTLP_ENDPOINT`. Their SigNoz access is also set in `settings.py`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SIGNOZ_CLICKHOUSE_URL` | unset | ClickHouse HTTP endpoint; when unset, `docker exec` is used |
| `SIGNOZ_CLICKHOUSE_CONTAINER` | `signoz-clickhouse` | Container for `docker exec` |
| `SIGNOZ_POLL_TIMEOUT` | `60` | Seconds to wait for ingested rows |

## Privacy

Redaction is a known gap, tracked in [#202](https://github.com/TunixR/R2Framework/issues/202). Today:

- Regex redaction misses quoted keys, e.g. `{"password": "..."}` in JSON or Python reprs.
- Strands exports prompts and completions as `gen_ai.*` span data. They include the task, the UI
  log, variables and user-typed input, and reach SigNoz unredacted.

Every exported span already flows through `RedactingSpanProcessor` and every log record through
`RedactingLogRecordProcessor` (`observability/redaction.py`), so the fix lands in one module. The
span processor is a pass-through placeholder until then.
