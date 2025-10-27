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
