# Docker stack

Everything R2Framework runs on, as one Compose project (`r2framework`) with two entry points:

| File | Runs | Use |
| --- | --- | --- |
| `compose.dev.yaml` | Postgres, SeaweedFS, SigNoz, otel-agent | Development: the framework runs on the host |
| `compose.prod.yaml` | The same, plus the framework API | Production |

## Architecture

```
                         ┌──────────────────────────── r2framework-backend ───────────────────────────┐
                         │                                                                            │
  clients ──:8000──▶ framework ──SQL──▶ postgres                                                      │
  (prod only)            │   └──S3──▶ seaweedfs-s3 ──▶ seaweedfs-filer ──▶ seaweedfs-master           │
                         │                                   └──────────▶ seaweedfs-volume            │
                         │                                                                            │
                         │                 otel-agent ◀── metrics: postgresql receiver, Prometheus ───┘
                         │                    │       ◀── logs: Docker json-file logs (host mount)
                         │ OTLP               │ OTLP
  ┌──────────────────────▼────────────────────▼───────── r2framework-telemetry ────────────────────────┐
  │                 signoz-collector ──▶ signoz-clickhouse ◀── signoz ◀──:8080── browser                │
  │                   (ingest)               │      ▲            │                                      │
  │                                   signoz-keeper │      signoz-metastore (Postgres)                  │
  │                                    signoz-migrator (schema, runs once per start)                    │
  └─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Two internal networks keep the data plane and the telemetry plane apart. Only services that
need both (the framework and the otel-agent) join both.

| Group | Directory | Services | Role |
| --- | --- | --- | --- |
| Database | `postgres/` | `postgres` | The framework's relational store (`gateway` database) |
| Object storage | `seaweedfs/` | `seaweedfs-master`, `-volume`, `-filer`, `-s3` | S3-compatible storage for screenshots and artifacts |
| Observability | `observability/` | `signoz`, `signoz-collector`, `signoz-clickhouse`, `signoz-keeper`, `signoz-metastore`, `signoz-migrator`, `signoz-clickhouse-scripts`, `otel-agent` | Traces, logs and metrics for the framework and the infrastructure |
| Application | `framework/` | `framework` (built from `framework/Dockerfile`) | The API (production only) |

Each group's `compose.yaml` is complete on its own. A `compose.dev.yaml` next to it holds
development-only additions (published ports, the Postgres seed mount). The entry points pull
the groups in with `include`.

### Request and telemetry flow

- The framework reads and writes Postgres, and stores objects through the S3 gateway. The gateway
  keeps metadata in the filer, which places data on the volume server through the master.
- The framework exports its own traces and logs over OTLP to `signoz-collector`
  (`http://localhost:4318` in dev, `http://signoz-collector:4318` in prod).
- Postgres and SeaweedFS do not speak OTLP. The `otel-agent` scrapes their metrics, reads the
  Docker logs of every container labelled `otel.service.name`, parses them (severity, database,
  pid, source location) and forwards everything to `signoz-collector`. See `../OBSERVABILITY.md`.
- `signoz-collector` writes to ClickHouse. The `signoz` UI and API query it. SigNoz's own state
  (users, dashboards, alerts) lives in `signoz-metastore`.
- `signoz-migrator` applies ClickHouse schema migrations on every `up` and exits. The collector
  refuses to start until the schema matches its version.

### Security model

| Service | Authentication | Exposure |
| --- | --- | --- |
| framework | App JWTs, robot keys | Published (prod) |
| signoz (UI) | SigNoz login | Published on 127.0.0.1 (`SIGNOZ_UI_BIND` to open it) |
| postgres | Password (`POSTGRES_PASSWORD`); agent uses a read-only `pg_monitor` role | Internal; 127.0.0.1 in dev |
| seaweedfs-s3 | Access keys when `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY` are set (required in prod) | Internal; 127.0.0.1 in dev |
| seaweedfs-filer | None | Internal; 127.0.0.1 in dev (browse objects) |
| signoz-clickhouse | Password (`SIGNOZ_CLICKHOUSE_PASSWORD`) | Internal only |
| signoz-metastore | Password (`SIGNOZ_METASTORE_PASSWORD`) | Internal only |
| signoz-collector | None (OTLP) | Internal; 127.0.0.1 in dev |
| seaweedfs master/volume, signoz-keeper | None | Internal only |

The unauthenticated services are reachable only from containers on the internal networks.
SeaweedFS can sign master/volume/filer traffic with JWTs (`security.toml`), and the collector
can require a bearer token; neither is configured yet.

The only container running as root is the otel-agent: Docker's log files are root-only. It
mounts them read-only.

## Setup

```bash
cp docker/.env.example docker/.env   # fill in the passwords
```

`docker/.env` holds the stack's settings and the credentials shared between services. The
framework's own settings (provider keys, `SECRET_KEY`, ...) stay in the repository's `.env`.

### Development

```bash
docker compose -f docker/compose.dev.yaml up -d
uv run fastapi dev main.py
```

In the repository's `.env`, point the framework at the published ports, using the same
credentials as `docker/.env`:

```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432            # POSTGRES_HOST_PORT in docker/.env, if changed
POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB   = docker/.env
S3_URL=http://localhost:8333
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY        = S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

**Seeding Postgres from a dump.** On an empty data volume, the dev Postgres restores every
dump in `postgres/dumps/` (git- and docker-ignored) into the database named after the file. See
`postgres/dumps/README.md`. For example, from a local server:

```bash
pg_dump -h localhost -U postgres -d gateway -Fc -f docker/postgres/dumps/gateway.dump
```

The first time SigNoz opens (http://localhost:8080), it asks you to create the admin account.

### Production

```bash
docker compose -f docker/compose.prod.yaml up -d --build
```

The framework reads the repository's `.env` (`FRAMEWORK_ENV_FILE` to use another file). The
stack overrides service addresses and shared credentials, so they cannot drift.
`S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` are required. Seed dumps are not mounted in
production; restore with `pg_restore` through `docker compose exec postgres`.

**Schema.** The API does not create its tables on startup, and `migrations/versions/` is
git-ignored, so a new production database needs its schema from a dump or from
`database.general.create_db_and_tables()`. Committed Alembic migrations, run once per deploy,
are pending work.

### Integration tests

With the development stack up and the repository's `.env` pointing at it:

```bash
docker compose -f docker/compose.dev.yaml up -d --wait
uv run pytest tests/integration -q
```

| Folder | Checks |
| --- | --- |
| `tests/integration/postgres` | Server version, a table for every model, a rolled-back write, the read-only monitoring role |
| `tests/integration/s3` | Object round trips through the S3 gateway |
| `tests/integration/observability` | The framework's traces, logs and exceptions in SigNoz |
| `tests/integration/interoperability` | Postgres errors arrive as parsed logs; Postgres and S3 activity arrives as metrics |

## Published ports

| Port | Service | Dev | Prod |
| --- | --- | --- | --- |
| 5432 | Postgres | 127.0.0.1 (`POSTGRES_HOST_PORT`) | - |
| 8333 | SeaweedFS S3 | 127.0.0.1 (`S3_HOST_PORT`) | - |
| 8888 | SeaweedFS filer (web UI, HTTP API) | 127.0.0.1 (`FILER_HOST_PORT`) | - |
| 4317 / 4318 | OTLP gRPC / HTTP | 127.0.0.1 | - |
| 8080 | SigNoz UI | 127.0.0.1 | 127.0.0.1 (`SIGNOZ_UI_BIND`) |
| 8000 | Framework API | - (runs on the host) | 0.0.0.0 (`FRAMEWORK_BIND`) |

## Scaling

What can run as more than one instance today, and what needs work first.

| Service | Scales today? | Notes / work needed |
| --- | --- | --- |
| `framework` | **Not yet.** The API itself is close | Holds no cross-request state: a recovery runs inside one websocket. Needs a load balancer that supports websockets in front, instead of the fixed published port. |
| `signoz-collector` | **Yes** | Stateless. `deploy.replicas: N` works on the internal network (Docker DNS round-robin). In dev the published OTLP ports pin it to one; use a load balancer to scale there. |
| `seaweedfs-volume` | **Yes, by adding servers** | Add `seaweedfs-volume-2`, ... each with its own `-ip` and volume; the master spreads new volumes across them. Raise `-defaultReplication` (e.g. `001`) to survive a server loss. |
| `seaweedfs-s3` | **Yes** | Stateless gateway; replicas can share the filer. Needs a load balancer once published. |
| `seaweedfs-filer` | **No** | Metadata is in a local leveldb2 store. Several filers need a shared store (Postgres, Redis, ...) configured in `filer.toml`. |
| `seaweedfs-master` | **No** | A single master. HA needs 3 masters with `-peers=` (raft); clients take the full list. |
| `postgres` | **No** | Single primary. Read replicas or HA need streaming replication plus failover (Patroni, or a managed Postgres). Back it up meanwhile (`pg_dump`). |
| `signoz` | **Not configured** | With the Postgres metastore (in place), SigNoz supports several replicas behind a load balancer; the fixed published UI port prevents it here. |
| `signoz-clickhouse` | **No** | One shard, one replica, created with `replication: false`. Scaling needs more replicas/shards in `remote_servers`, replicated tables (migrator `--replication`, which needs migrating existing data or a fresh install) and 3 keepers. |
| `signoz-keeper` | **No** | One node. HA needs 3 (an odd number) in `raft_configuration`. |
| `signoz-metastore` | **No** | Single Postgres, same as `postgres`. |
| `otel-agent` | **One per Docker host** | Reads that host's container logs. With several hosts (e.g. Swarm), run it as a global service, one per node, not as replicas. |
| `signoz-migrator`, `signoz-clickhouse-scripts` | n/a | One-shot jobs. |

## Data

| Volume | Holds |
| --- | --- |
| `r2framework-postgres-data` | Postgres (18+ layout, mounted at `/var/lib/postgresql`) |
| `r2framework-seaweedfs-volume-data` | SeaweedFS object data |
| `r2framework-seaweedfs-filer-data` | SeaweedFS filer metadata (directory tree, buckets) |
| `r2framework-seaweedfs-master-data` | SeaweedFS master state (rebuilt from the volume server) |
| `r2framework-signoz-clickhouse-data` | Traces, logs, metrics |
| `r2framework-signoz-metastore-data` | SigNoz users, dashboards, alerts |
| `r2framework-signoz-keeper-data` | ClickHouse coordination |
| `r2framework-signoz-clickhouse-scripts` | `histogramQuantile` UDF binary (re-downloadable) |
| `r2framework-otel-agent-data` | Log read offsets |

`docker compose down` keeps the volumes; `-v` deletes them.

## Upgrades

Changes to this structure that need manual steps (data moves, renamed volumes,
new required settings) are recorded in [UPGRADE.md](UPGRADE.md). Read it before
pulling a new version of `docker/`.

Every image is pinned in the compose files with an override variable (listed in
`.env.example`). To upgrade, bump the pin, read the release notes, then run
`docker compose -f docker/compose.<env>.yaml up -d`. Changing a bind-mounted config file needs
`docker compose ... restart <service>`; Compose does not recreate containers for it.

- **Postgres**: minor versions are drop-in. A major version needs `pg_upgrade` or
  dump/restore; the 18+ volume layout allows `pg_upgrade --link`.
- **SeaweedFS**: within 4.x, bump `SEAWEEDFS_VERSION`.
- **SigNoz**: bump `signoz`, `signoz-otel-collector` (migrator and collector share it) and
  ClickHouse together, as the release notes pair them. Check
  <https://signoz.io/upgrade-path/> for required stops and step through each one:

  ```bash
  SIGNOZ_VERSION=vX SIGNOZ_COLLECTOR_VERSION=vY docker compose -f docker/compose.dev.yaml up -d --wait signoz
  ```

  This runs the ClickHouse schema migrations and SigNoz's metastore migrations without starting
  the collector. Bring the full stack up after the last stop. The collector, ClickHouse and
  Keeper configs follow SigNoz Foundry's generated manifests; compare them with Foundry's
  `docs/examples/docker/compose` on each upgrade.
