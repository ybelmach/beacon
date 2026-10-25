# Beacon

Device telemetry ingest and analytics platform.

Devices push events over HTTP; the API validates them and publishes to Kafka. Consumers
fan out from there — one persists to ClickHouse for analytics, another evaluates alert
rules. Postgres holds the operational state (devices, users, rules), Redis handles caching
and rate limiting, S3-compatible storage (RustFS) holds exported artifacts.

## Stack

| Concern | Choice |
| --- | --- |
| Runtime | Python 3.14, FastAPI, uvicorn |
| Packaging | uv (`uv.lock` is committed and authoritative) |
| Operational store | PostgreSQL + SQLAlchemy 2 (async) + Alembic |
| Analytics store | ClickHouse |
| Messaging | Kafka (3 brokers, KRaft) |
| Cache / rate limiting | Redis |
| Object storage | RustFS (S3 API) |
| Observability | structlog (JSON), Prometheus, Grafana |
| Orchestration | Docker Compose, Taskfile |

## Quick start

Requires Docker, [Task](https://taskfile.dev) and [uv](https://docs.astral.sh/uv/).

```bash
task setup   # uv sync + create .env from .env.example
task up      # infrastructure + backend
```

`.env` is mandatory — both Compose and the Taskfile refuse to run without it. `task setup`
creates it from `.env.example`; the defaults there are for local development only.

| Service | URL |
| --- | --- |
| API docs (Scalar) | http://localhost:18000/scalar |
| API docs (Swagger) | http://localhost:18000/docs |
| RustFS console | http://localhost:19001 |
| ClickHouse | http://localhost:18123/play |
| Grafana | http://localhost:13000 |
| Prometheus | http://localhost:19090 |
| Kafka UI | http://localhost:18080 |

Consumers, observability, tooling and the simulator sit behind Compose profiles and are
off by default. `task up:all` starts everything; `task up:obs` (Prometheus + Grafana) and
`task up:tools` (Kafka UI) start individual groups.

## Everyday commands

`task` on its own lists everything. The ones you will actually use:

```bash
task up / down / clean      # clean also drops volumes — all data is lost
task logs -- backend        # follow one service
task ps                     # container status
task sh                     # shell inside the backend container
task sh:pg / sh:redis / sh:ch  # psql, redis-cli, clickhouse-client

task test                   # pytest, on the host
task test:cov               # pytest with a coverage report
task lint                   # ruff, mypy, pyright, on the host
task fmt                    # ruff format
task check                  # fmt + lint + test, run this before committing

task db:migrate             # apply Alembic migrations
task db:revision NAME="..." # autogenerate a migration
task ch:init                # apply ClickHouse DDL

task sim                    # start the device simulator
task load                   # k6 load test
```

## Layout

```
beacon/
  core/            config, logging, health probes, error handling, middleware
  entrypoints/     process entry points and their lifespans: api, consumer_storage, consumer_alerting, simulator
  modules/         business modules (router / service / repository / models / schemas)
  infrastructure/  clients for postgres, redis, kafka, clickhouse, s3, notifiers
infra/             Dockerfile, Compose, Prometheus/Grafana/ClickHouse configuration
scripts/           container entrypoint and helpers
tests/
```

Each module under `beacon/modules/` owns one slice of the domain and follows the same
router → service → repository split. `core` and `infrastructure` never import from
`modules`.

Dependencies point one way: `entrypoints → modules → infrastructure → core`. `core`
knows nothing about Postgres, Redis or any other backend.

Every process builds its clients with `beacon.infrastructure.resources.build_resources`,
which yields a `Resources` bundle and tears it down in reverse order. The API's lifespan
stores it on `app.state.resources` and registers the readiness checks it cares about.
Routes reach it through `beacon.infrastructure.dependencies` (`SessionDep`, `RedisDep`).

`SessionDep` opens one session per request and never commits. The service owns the
transaction (`await session.commit()` or `async with session.begin()`); repositories only
`add`, `flush` and query. Anything left uncommitted is rolled back when the session closes.

## Configuration

Every setting lives in `beacon/core/config.py` as a field on `Settings` and is read from
the environment. `.env.example` is the annotated reference; `Settings` validates on
startup, so a bad `LOG_LEVEL` or a `CORS_ALLOW_CREDENTIALS=true` combined with `*`
fails the process immediately rather than at the first request.

`BEACON_ENV_FILE` overrides which dotenv is read. The test suite points it at
`tests/.env.test` so a developer's local `.env` can never change how tests behave; real
environment variables still take precedence over the file, so CI can override any single
value.

`SECRET_KEY` may be any value while `ENVIRONMENT` is `local` or `test`. In every other
environment (`dev`, `staging`, `production`) startup fails unless it is at least 32
characters and not a known placeholder – generate one with `openssl rand -hex 32`.

Two flags are worth calling out:

- `DEBUG_MODE` — verbose local mode: SQL echo, callsite info in logs, a per-request
  "started" line. It deliberately does **not** change what a client sees; error responses
  have the same shape in every environment.
- `LOG_FORMAT` — `json` for anything a log collector reads, `console` for a readable
  local terminal.

## Operational endpoints

| Path | Purpose |
| --- | --- |
| `GET /healthz` | Liveness. Answers as long as the process is up; never touches a dependency. |
| `GET /readyz` | Readiness. Probes Postgres and Redis concurrently, each bounded by `READINESS_TIMEOUT_SECONDS`. Returns 503 with a per-check breakdown when anything is not `ok`. |

Both are excluded from the OpenAPI schema and from the access log.

## Error format

Every error response is [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem detail
with the `application/problem+json` media type:

```json
{
  "type": "http://localhost:18000/problems/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Device 7 does not exist",
  "instance": "/api/v1/devices/7",
  "request_id": "0f9c1e2a-..."
}
```

Raise a subclass of `beacon.core.exceptions.AppError` from anywhere in a module; the
class declares its own `status_code`, `slug` and `default_detail`, and that is the single
source of truth — the status→slug index used for bare `HTTPException`s is derived from
the class hierarchy, not maintained separately.

Validation failures add an `errors` array. Unhandled exceptions become a generic 500 with
no internals leaked, logged once with a structured traceback.

## Logging

structlog, JSON to stdout, one line per event. Stdlib loggers (uvicorn, SQLAlchemy,
aiokafka) are routed through the same pipeline, so the output is uniform. Every line
carries `service` and `env`; every line emitted during a request also carries
`request_id`, which comes from the inbound `X-Request-ID` header when present and is
echoed back on the response. An inbound id is trusted only if it is 1–128 characters of
`A-Z a-z 0-9 . _ : -`; anything else is silently replaced with a fresh UUID.

The access log records method, path, status and duration – never the query string,
which routinely carries tokens.

## Tests

```bash
task test        # same as: uv run pytest -v
```

Integration tests use [testcontainers](https://testcontainers-python.readthedocs.io/),
so Docker must be running. Settings are pinned by `tests/.env.test`; the Taskfile
deliberately does not load `.env` for test tasks, so local values cannot leak in.

## CI

`.github/workflows/ci.yml` and `.gitlab-ci.yml` run the same pipeline:

| Job | When | What |
| --- | --- | --- |
| `lint` | PRs/MRs into `develop`/`main`, pushes to them | `pre-commit run --all-files` (ruff, mypy, pyright, hygiene hooks) |
| `test` | same | `pytest` with coverage and a JUnit report |
| `build` | pushes to `develop`/`main` | production image, pushed to GHCR / the GitLab registry, tagged with the short SHA and the branch |

Neither needs secrets: tests read `tests/.env.test`. GitHub Actions are pinned to
commit SHAs.
