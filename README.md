# Bootstrap Tooling

This repository contains a minimal Python project skeleton configured with modern developer tooling.

## Getting Started

1. Install [Poetry](https://python-poetry.org/docs/#installation) if it is not already available on your system.
2. Install the project dependencies:

   ```bash
   poetry install
   ```

3. Enable the shared git hooks provided by [pre-commit](https://pre-commit.com/):

   ```bash
   poetry run pre-commit install
   ```

4. Run the test suite:

   ```bash
   poetry run pytest
   ```

## Tooling

- **Formatter**: [Black](https://black.readthedocs.io/en/stable/)
- **Linter**: [Ruff](https://docs.astral.sh/ruff/)
- **Type Checker**: [mypy](https://mypy.readthedocs.io/en/stable/)
- **Test Runner**: [pytest](https://docs.pytest.org/)
- **HTTP Client Library**: [httpx](https://www.python-httpx.org/)
- **Test Coverage**: [coverage.py](https://coverage.readthedocs.io/)

All tooling is configured via the committed configuration files in the project root. The pre-commit hooks ensure that Ruff, Black, and mypy run automatically before each commit.

## Documentation

- Start new project docs from the shared [template](docs/template.md) so structure remains consistent across the repository.
- Store diagrams, media, and their source files under [`docs/diagrams`](docs/diagrams/README.md) for easy reuse.
- Review the [contribution guidelines](CONTRIBUTING.md) for branching, testing, and PR expectations.
- Advanced realtime messaging topology: [docs/advanced_messaging_bus.md](docs/advanced_messaging_bus.md).

---

## Docker Compose Stack

This repository includes a dockerized development stack orchestrating Postgres, MongoDB, Redis, RabbitMQ, and two placeholder FastAPI services (app1 and app2). Services share a common network and data is persisted in named volumes.

### Quick start

1. Copy the env file and adjust values if needed (optional – sensible defaults are provided so this step can be skipped):

   ```bash
   cp .env.example .env
   ```

2. Bring the stack up:

   ```bash
   docker compose up -d --build
   ```

3. Check service health:

   ```bash
   docker compose ps
   ```

   Postgres, MongoDB, Redis, and RabbitMQ include healthchecks and should reach a healthy state.

### Service endpoints

- app1: http://localhost:8000 (docs: http://localhost:8000/docs)
- app2: http://localhost:8001 (docs: http://localhost:8001/docs)
- Postgres: localhost:5432 (db: app_db, user: app, pass: app)
- MongoDB: localhost:27017 (root user: app, pass: app, authSource: admin)
- Redis: localhost:6379 (password required: app)
- RabbitMQ AMQP: localhost:5672 (user: app, pass: app)
- RabbitMQ Management UI: http://localhost:15672 (user: app, pass: app)

Connection URIs are provided in .env.example for convenience.

### Observability & monitoring

The advanced realtime service exposes OpenTelemetry-powered traces and Prometheus metrics.

- Health probe: `GET http://localhost:8004/healthz`
- Readiness probe: `GET http://localhost:8004/readyz`
- Metrics endpoint: `GET http://localhost:8004/metrics`
- Rate limiting is enabled by default (`ADVANCED_RATE_LIMIT_DEFAULT`) and returns `429` with
  a JSON body when the limit is exceeded.

A monitoring stack is available via Docker Compose:

```bash
docker compose up -d advanced-app jaeger prometheus grafana
```

Services provided:

- **Jaeger** (traces): http://localhost:16686
- **Prometheus** (metrics explorer): http://localhost:9090
- **Grafana** (dashboards): http://localhost:3001 (default credentials `admin` / `admin`)

Grafana automatically provisions an "Advanced Realtime Observability" dashboard with panels
for HTTP traffic, board event throughput, and rate-limit rejections. Prometheus is configured
to scrape the `/metrics` endpoint exposed by `advanced-app`.

### Development workflow

- Hot reload is enabled for the FastAPI apps via uvicorn --reload.
- Source code is bind-mounted from the host, so changes are reflected immediately in running containers.
- Dependencies are installed with Poetry inside the containers. On container start, poetry install runs to ensure dependencies match the pyproject.toml in each app.

Common commands:

```bash
# Tail logs for a service
docker compose logs -f app1

# Add a dependency to app1 from inside the container
docker compose exec app1 bash -lc "poetry add requests"

# Rebuild an app image after dependency changes
docker compose build app1 && docker compose up -d app1
```

### Teardown

```bash
docker compose down
# Remove named volumes as well (database data, etc.)
docker compose down -v
```

### Notes

- Named volumes are used for Postgres, MongoDB, Redis, and RabbitMQ to persist data across restarts.
- All services are attached to a shared network named "${COMPOSE_PROJECT_NAME}_net" (defaults to "devstack_net").

## Intermediate app caching

The intermediate FastAPI service includes an optional Redis-backed cache that accelerates read-heavy
endpoints such as task listings and statistics. Caching can be toggled with the
`INTERMEDIATE_CACHE_ENABLED` setting, and time-to-live values can be adjusted via
`INTERMEDIATE_CACHE_TTL_SECONDS`. The application logs cache hits, misses, and invalidations and
exposes in-memory metrics for instrumentation and tests. All task mutations automatically invalidate
related cache entries to ensure clients always receive fresh data.

## Intermediate app logging and environment profiles

Structured JSON logging is enabled across the intermediate API and its background worker. Every log
line includes consistent keys such as `timestamp`, `level`, `logger`, `message`, `service`,
`environment`, and `request_id`. Request correlation identifiers are sourced from the
`X-Request-ID` header when present, applied via middleware, and automatically propagated to
background jobs so queue processing events keep the same correlation id.

Configuration is managed by Pydantic settings with dedicated profiles:

- **development** – debug logging and hot reload enabled.
- **test** – warnings-and-above logging, cache disabled by default, reload off.
- **ci** – info-level logging optimised for non-interactive runtimes.

Explicit environment variables (e.g. `INTERMEDIATE_LOG_LEVEL`, `INTERMEDIATE_CACHE_ENABLED`) always
override the profile defaults. Use `INTERMEDIATE_ENVIRONMENT` to switch between profiles for local
development, automated tests, and CI pipelines.
