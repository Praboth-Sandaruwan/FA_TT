# Intermediate SSR + Background Jobs Project

## 1. Introduction

- **Purpose:** End-to-end reference application that blends a session-backed SSR surface with a fully
  featured FastAPI JSON API. It demonstrates how to layer Redis caching, background job execution,
  and a document-store analytics sink on top of a Postgres system of record.
- **Audience:** Engineers comfortable with Python, FastAPI, and containerised development who need a
  working example of SSR + API coexistence, queue-driven background processing, and Mongo-powered
  reporting.
- **Status & Owners:** Status – active (development). Maintainers – Platform Enablement group. Start
  new documentation efforts from the shared [template](../../docs/template.md).

## 2. Setup & Getting Started

### 2.1 Prerequisites

- Python 3.12 and [Poetry 1.8.x](https://python-poetry.org/)
- Docker Desktop (v4.24+) with Compose V2 for running Postgres, Redis, and MongoDB
- Optional: `mongoimport` CLI (bundled in the MongoDB container) for the analytics demonstration
- Recommended tooling from the repository root: `poetry run pre-commit install`

### 2.2 Local Environment Setup

1. Copy the environment template and adjust values as needed:

   ```bash
   cp projects/02-intermediate/.env.example projects/02-intermediate/.env
   ```

2. Install project dependencies (from the repository root):

   ```bash
   poetry install
   ```

3. Start supporting infrastructure. The compose file ships everything you need for the intermediate
   app; start only the relevant services to keep resource usage low:

   ```bash
   docker compose up -d postgres redis mongodb rq-dashboard
   ```

4. Apply database migrations so the SQLModel tables exist:

   ```bash
   poetry run alembic upgrade head
   ```

5. Seed a demo dataset (user + tasks) for the SSR surface:

   ```bash
   poetry run python -m projects.02-intermediate.app.db.seed
   ```

6. Launch the FastAPI application (serves both the API and SSR routes):

   ```bash
   poetry run intermediate-app
   ```

7. In a second terminal, start the background worker so queued jobs are processed:

   ```bash
   poetry run intermediate-worker
   ```

8. *(Optional analytics sink)* Import the sample task-report documents into MongoDB to visualise the
   document-store integration. The file lives under `projects/02-intermediate/docs/samples/`.

   ```bash
   docker compose cp projects/02-intermediate/docs/samples/task_reports.sample.json mongodb:/tmp/task_reports.json
   docker compose exec mongodb mongoimport \
     --username ${MONGO_INITDB_ROOT_USERNAME:-app} \
     --password ${MONGO_INITDB_ROOT_PASSWORD:-app} \
     --authenticationDatabase admin \
     --db analytics \
     --collection task_reports \
     --mode=upsert \
     --upsertFields owner_id \
     --jsonArray \
     --file /tmp/task_reports.json
   ```

### 2.3 Verification

- API heartbeat: `curl http://localhost:8003/healthz`
- OpenAPI docs: `http://localhost:8003/docs`
- SSR entry point: visit `http://localhost:8003/` and create an account; you should land on the
  `/notes` dashboard with seeded tasks
- Caching check: call `curl -H "Authorization: Bearer <token>" http://localhost:8003/api/tasks`
  twice, observing `Cache hit` log entries on the second request
- Background job flow: enqueue a report –

  ```bash
  curl -X POST http://localhost:8003/api/jobs/task-report \
    -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{"owner_id": 1}'
  ```

  Confirm the job completes via `docker compose logs rq-dashboard` or by refreshing the dashboard at
  `http://localhost:9181`

- Mongo integration: inspect imported analytics documents –

  ```bash
  docker compose exec mongodb mongosh --quiet --eval 'use analytics; db.task_reports.find().pretty()'
  ```

## 3. Architecture Overview

The intermediate project hosts two surfaces on one FastAPI instance: a JSON API (for automation and
third-party clients) and an SSR experience powered by Jinja templates and HTMX for partial updates.
Stateful browser sessions use signed cookies, CSRF tokens, and flash messaging provided by the
`core.session` helpers. Business logic lives in `services` modules that wrap SQLModel repositories.

Redis fulfils two responsibilities:

- A read-through cache for expensive task list/statistics endpoints (`core.cache`),
- The backing store for the RQ job queue used when generating task summary reports.

Postgres remains the source of truth for users, tasks, and aggregated reports. Analytics dashboards
can consume denormalised report snapshots via MongoDB; the repository includes a sample dataset and
instructions for syncing job outputs into the `analytics.task_reports` collection.

Source diagrams live under [`./docs/`](./docs/). The request lifecycle is summarised below:

```mermaid
%% Source: ./docs/request-lifecycle.mmd
sequenceDiagram
    autonumber
    participant Browser
    participant View as FastAPI SSR layer
    participant Session as Session middleware
    participant Cache as Redis cache
    participant Service as TaskService
    participant Postgres

    Browser->>View: GET /notes
    View->>Session: SessionUserDependency + CSRF bootstrap
    Session-->>View: Authenticated user context
    View->>Cache: cache_get_or_set(tasks:list,…)
    Cache-->>View: Cache miss
    View->>Service: list_tasks_for_owner(user_id)
    Service->>Postgres: SELECT tasks
    Postgres-->>Service: Task rows
    Service-->>View: Task collection
    View->>Cache: Store paginated payload
    View->>Browser: Render notes/index.html

    rect rgb(245, 245, 245)
        Browser->>View: POST /notes/{task_id}/toggle (HX-Request)
        View->>Session: validate_csrf_token
        Session-->>View: Token accepted
        View->>Service: update_task_for_owner()
        Service->>Postgres: UPDATE tasks SET status
        Postgres-->>Service: Updated row
        Service-->>View: Updated task entity
        View->>Cache: invalidate_task_cache()
        View->>Browser: Render notes/_note_item.html fragment
    end
```

### 3.1 Component Breakdown

| Component | Responsibility | Technology | Notes |
| --- | --- | --- | --- |
| FastAPI application | HTTP entry point, dependency injection, middleware | FastAPI + Starlette | `main.py` wires routes, middleware, and OpenAPI metadata |
| SSR views & templates | Render session-protected pages and HTMX partials | Jinja2, HTMX, Starlette sessions | See `views/` and `templates/` directories |
| JSON API routers | CRUD for tasks, users, auth, job orchestration | FastAPI routers | Namespaced under `/api` with OAuth2 + JWT auth |
| Services & repositories | Encapsulate data access and domain logic | SQLModel, SQLAlchemy | `TaskService`, `UserService`, `TaskReportService` |
| Redis cache | Speeds up task listings/statistics, tracks cache metrics | Redis 7, `redis.asyncio` | Configured via `INTERMEDIATE_CACHE_ENABLED` and TTL settings |
| RQ job queue & worker | Generates task summary reports off the main request path | RQ, Redis | Worker launched via `poetry run intermediate-worker` |
| Postgres database | Primary transactional store | Postgres 16, SQLModel | Managed through Alembic migrations |
| Mongo analytics sink | Stores denormalised report documents for dashboards | MongoDB 7 | Seeded via `task_reports.sample.json` or custom sync jobs |
| RQ dashboard | Operational view of queued/processed jobs | eoranged/rq-dashboard | Exposed on `http://localhost:9181` when the service is running |

### 3.2 Data Flow & Contracts

- Task list endpoints call `cache_get_or_set`, serialising responses via Pydantic models. Cache keys
  include owner, status, limit, and offset. Mutations invoke `invalidate_task_cache()` to keep cache
  entries coherent.
- JWT-secured APIs (`/api/tasks` and `/api/users`) rely on `deps.require_current_user` to translate
  Bearer tokens into domain users, enforcing role-based checks along the way.
- Background jobs are scheduled through `enqueue_task_report`. Each job receives a stable request id
  so logs emitted by the worker retain the originating correlation identifier.
- Optional analytics synchronisation pushes generated report snapshots into Mongo for BI workloads.
  The sample dataset mirrors the shape produced by `TaskReportService` and can be imported with the
  commands in section 2.

```mermaid
%% Source: ./docs/job-processing.mmd
sequenceDiagram
    autonumber
    participant Client
    participant API as FastAPI /api/jobs/task-report
    participant Queue as Redis queue (RQ)
    participant Worker as RQ worker
    participant Postgres as Postgres (SQLModel)
    participant Mongo as Mongo analytics (optional)

    Client->>API: POST /api/jobs/task-report
    API->>Queue: enqueue_task_report(owner_id, request_id)
    API-->>Client: 202 Accepted + job metadata
    Queue->>Worker: Dispatch generate_task_report_job
    Worker->>Postgres: TaskReportService.generate_report()
    Postgres-->>Worker: Aggregated counts
    Worker->>Postgres: UPSERT task_reports snapshot
    Worker-->>Queue: Mark job finished

    Note over Worker,Mongo: Optional analytics sync via mongoimport sample data
    Worker-->>Mongo: Upsert analytics.task_reports document (manual step)
```

## 4. Feature Walkthrough

### 4.1 Core Scenarios

1. **Register + Login:** Use the SSR forms at `/auth/register` and `/auth/login`. Successful login
   stores the user id in the signed session and displays flash messages confirming the action.
2. **Manage notes/tasks:** Create, toggle, and delete entries from the `/notes` page. HTMX submits
   forms asynchronously and swaps updated list items without a full page refresh.
3. **API interactions:** Obtain tokens through `/api/auth/login` (OAuth2 password flow). Use the
   returned access token to call `/api/tasks`, `/api/tasks/{id}`, and `/api/users/me`.
4. **Generate reports:** Trigger report calculation by POSTing to `/api/jobs/task-report`. Query the
   latest snapshot with `/api/jobs/task-report/{owner_id}` or via the SSR dashboard (future work).

### 4.2 Interfaces & APIs

| Surface | Endpoint(s) | Purpose |
| --- | --- | --- |
| Browser | `/`, `/auth/*`, `/notes`, `/static/*` | Session-protected SSR experience |
| JSON API | `/api/auth`, `/api/tasks`, `/api/users`, `/api/jobs`, `/healthz` | Token-secured programmatic interface |
| Documentation | `/docs`, `/redoc` | Swagger UI / ReDoc |
| Worker CLI | `poetry run intermediate-worker` | Starts the RQ worker consuming the queue |

### 4.3 Background Processes

- The worker logs in structured JSON (see `core.logging`) so observability platforms can ingest queue
  metrics easily.
- Retry behaviour (max attempts and back-off) is configurable via `INTERMEDIATE_JOB_MAX_RETRIES` and
  `INTERMEDIATE_JOB_RETRY_BACKOFF_SECONDS`.
- Operational teams can watch job throughput via the bundled RQ dashboard service in Docker Compose.

## 5. Operations & Maintenance

- **Deployments:** Build the image with the provided Dockerfile —

  ```bash
  docker build -f projects/02-intermediate/Dockerfile -t intermediate-app:latest .
  ```

  Run database migrations (`poetry run alembic upgrade head`) during rollouts before starting new
  application or worker replicas.

- **Configuration:** Key environment variables (prefixed with `INTERMEDIATE_`) include:

  | Variable | Purpose | Default |
  | --- | --- | --- |
  | `INTERMEDIATE_DATABASE_URL` | SQLModel connection string | `postgresql+asyncpg://app:app@localhost:5432/app_db` |
  | `INTERMEDIATE_REDIS_URL` | Redis instance for cache + queue | `redis://localhost:6379/0` |
  | `INTERMEDIATE_CACHE_ENABLED` | Toggle caching on/off | `true` in development / CI profiles |
  | `INTERMEDIATE_JOB_QUEUE_NAME` | Namespace for RQ jobs | `intermediate:tasks` |
  | `INTERMEDIATE_SESSION_SECRET_KEY` | Secure cookie signing key | `change-me-session` |
  | `INTERMEDIATE_ALLOWED_ORIGINS` | CORS allowlist for API clients | `http://localhost:3000,http://127.0.0.1:3000` |

- **Logging & Monitoring:** Structured JSON logs emit `request_id`, `service`, and `environment`
  fields. Configure log shipping to aggregate worker + API events. Use the Redis `INFO` command or RQ
  dashboard to monitor queue depth.
- **Backups:** Persist Postgres with `pg_dump` and Mongo analytics with `mongodump`. Redis-backed
  caches can be reconstructed from the primary data stores.

## 6. Troubleshooting Guide

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| API returns `503` when enqueuing jobs | Redis queue unavailable | Ensure the Redis container is
running (`docker compose up -d redis`) and revisit `INTERMEDIATE_REDIS_URL` |
| Cache misses never turn into hits | Cache disabled | Confirm `INTERMEDIATE_CACHE_ENABLED=true` and
watch for cache warnings in the logs indicating connectivity issues |
| SSR forms return “Invalid CSRF token” | Session expired or clock skew | Refresh the page to obtain a
new CSRF token; verify system clocks and that session secret keys match across replicas |
| `mongoimport` authentication fails | Using default credentials without auth DB | Include
`--authenticationDatabase admin` (already shown above) or match custom Mongo credentials |
| `alembic upgrade` fails with connection error | Postgres not ready | Check `docker compose logs postgres`
for health status; rerun the command once the database is healthy |

## 7. Project Documentation Checklist

- [x] README points back to the shared documentation template for future maintainers
- [x] Setup instructions validated on a clean environment with Docker-provisioned dependencies
- [x] Environment variables documented with defaults and override guidance
- [x] Architecture diagrams (source files) live under [`docs/`](./docs/)
- [x] Key workflows (API + job queue) documented with example commands
- [x] Deployment, monitoring, and backup considerations captured
- [x] Troubleshooting section covers common operational issues with actionable remedies
- [x] Supporting assets (Mongo sample dataset, diagrams) committed alongside the docs

## 8. Extension Exercises

1. **Real-time status updates:** Push job completion events to the browser via Server Sent Events or
   WebSockets so the `/notes` dashboard can show report progress without manual refreshes.
2. **Mongo sync job:** Implement a follow-on worker task that mirrors each `TaskReport` row into the
   Mongo analytics collection automatically instead of relying on manual imports.
3. **Cache observability:** Expose cache metrics (`core.cache.cache_metrics.snapshot()`) via a
   `/metrics` endpoint or Prometheus exporter to track hit/miss ratios over time.
4. **Access tiers:** Introduce role-specific dashboards by extending `UserRole` and gating views at
   the router level (e.g. admins see multi-owner statistics, standard users only their data).

---

For contribution guidelines, workflow expectations, and code-style conventions, refer back to
[CONTRIBUTING.md](../../CONTRIBUTING.md).
