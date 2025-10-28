# Advanced Realtime Collaboration Project

## 1. Introduction

- **Purpose:** Demonstrates a production-ready realtime collaboration surface backed by FastAPI, WebSockets, Server-Sent Events (SSE), RabbitMQ, and Redis. It showcases authenticated fan-out, cross-instance delivery guarantees, and full-stack observability.
- **Audience:** Engineers designing resilient realtime platforms who need patterns for brokered fan-out, rate limiting, instrumentation, and operational hardening.
- **Status & Owners:** Status – active (development). Maintainers – Platform Enablement group. Start new documentation efforts from the shared [template](../../docs/template.md).

## 2. Setup & Getting Started

### 2.1 Prerequisites

- Python 3.12 and [Poetry 1.8.x](https://python-poetry.org/)
- Docker Desktop / Docker Compose V2 for Redis, RabbitMQ, Prometheus, Grafana, and Jaeger
- Optional CLI tooling: `redis-cli`, `rabbitmqadmin`, `grpcurl`
- Recommended: install repository git hooks – `poetry run pre-commit install`

### 2.2 Local Environment Setup

1. Copy the environment template and customise the realtime token:

   ```bash
   cp projects/03-advanced/.env.example projects/03-advanced/.env
   # Edit ADVANCED_REALTIME_TOKEN and any broker credentials before starting the stack
   ```

2. Install dependencies from the repository root:

   ```bash
   poetry install
   ```

3. Start the infrastructure dependencies. The provided compose file ships Redis, RabbitMQ, and the observability stack used by this project:

   ```bash
   docker compose up -d redis rabbitmq jaeger prometheus grafana
   ```

   > 💡 Want to explore the app without external brokers? Export `ADVANCED_EVENT_TRANSPORT=memory` before launching the app to bypass RabbitMQ and Redis.

4. In one terminal, launch the background consumer that relays RabbitMQ messages into Redis:

   ```bash
   poetry run advanced-worker
   ```

5. In another terminal, start the FastAPI application:

   ```bash
   poetry run advanced-app
   ```

6. Open [http://localhost:8004](http://localhost:8004), paste the configured realtime token into the playground, and open a second browser window to observe cross-client fan-out.

### 2.3 Verification Checklist

- **WebSocket handshake:** `websocat ws://localhost:8004/ws/boards/demo?token=<token>` and send a JSON payload; expect the broadcast payload echoed with `active_connections` metadata.
- **SSE stream:** `curl -N "http://localhost:8004/sse/activity?token=<token>"` and trigger board activity. Heartbeats arrive roughly every 15 seconds when idle.
- **End-to-end pipeline:**
  
  ```bash
  poetry run python scripts/advanced_pipeline_demo.py
  ```
  
  The script sends a WebSocket event and waits for the correlated SSE payload, exercising RabbitMQ → Redis fan-out.
- **Observability probes:**
  
  ```bash
  curl http://localhost:8004/metrics | grep advanced_http_requests_total
  curl http://localhost:8004/readyz
  ```
- **Automated tests:** `poetry run pytest -k "advanced"`

## 3. Realtime Architecture

Client updates land on a FastAPI WebSocket endpoint. Each payload is validated, wrapped in a transport envelope, and published to RabbitMQ. A dedicated worker consumes the queue, applies idempotency checks, and fans events out via Redis pub/sub. Local app instances subscribe to the Redis channel and broadcast structured activity events to WebSocket peers and SSE listeners. Rate limiting, token-based auth, and hardened security headers defend the edge.

```mermaid
%% Source: ./docs/realtime-messaging-flow.mmd
sequenceDiagram
    autonumber
    participant Client as Browser/Websocket client
    participant API as FastAPI realtime API
    participant Pipeline as EventPipeline
    participant RabbitMQ as RabbitMQ exchange + queue
    participant Worker as advanced-worker
    participant Redis as Redis pub/sub
    participant Subscriber as RedisActivitySubscriber
    participant Broker as RealtimeBroker
    participant SSE as SSE stream subscribers

    Client->>API: WebSocket JSON payload
    API->>Pipeline: Validate + publish(BoardEventEnvelope)
    Pipeline->>RabbitMQ: Persist message (boards.activity)
    Worker->>RabbitMQ: Consume delivery
    Worker->>Redis: Publish ActivityEvent (advanced:activity)
    Redis->>Subscriber: Notify via pub/sub
    Subscriber->>Broker: broker.broadcast(ActivityEvent)
    Broker->>Client: send_json(ActivityEvent)
    Broker->>SSE: Queue ActivityEvent for SSE stream
    API-->>SSE: Server-Sent Event heartbeat/data
```

### 3.1 Component Breakdown

```mermaid
%% Source: ./docs/component-map.mmd
flowchart TD
    subgraph Clients
        Browser[Realtime board UI]
        Automation[Automation scripts]
    end

    subgraph FastAPI[FastAPI advanced-app]
        WS[WebSocket endpoint /ws/boards/{id}]
        SSE[/SSE endpoint /sse/activity/]
        Pipeline[EventPipeline + rate limits]
        Auth[Token auth + security headers]
        Telemetry[Observability middleware]
    end

    subgraph Messaging[Messaging + fan-out]
        Rabbit[(RabbitMQ exchanges & queues)]
        Worker[advanced-worker]
        Redis[(Redis pub/sub + idempotency store)]
    end

    subgraph Observability
        Prom[Prometheus metrics]
        Grafana[Grafana dashboards]
        Jaeger[Jaeger tracing]
    end

    Browser -- WebSocket --> WS
    Browser -- EventSource --> SSE
    Automation -- API tests --> WS
    WS --> Pipeline
    Pipeline --> Rabbit
    Worker --> Rabbit
    Worker --> Redis
    Redis --> Pipeline
    Pipeline --> WS
    Pipeline --> SSE
    Telemetry --> Prom
    Telemetry --> Jaeger
    Prom --> Grafana
```

| Component | Responsibility | Technology | Key Files |
| --- | --- | --- | --- |
| FastAPI app | Hosts HTTP + WebSocket surfaces, applies security headers, rate limiting, and telemetry | FastAPI, SlowAPI | `src/projects/03-advanced/app/main.py`
| Event pipeline | Wraps board messages, publishes to RabbitMQ, subscribes to Redis | aio-pika, redis-py | `app/messaging.py`
| Realtime broker | Tracks WebSocket connections and SSE listener queues | Starlette + asyncio | `app/realtime.py`
| Authentication | Validates shared realtime token across HTTP and WebSockets | FastAPI dependencies | `app/auth.py`
| Worker | Consumes RabbitMQ queue, ensures idempotent Redis fan-out, manages retries/DLQ | aio-pika, Redis | `app/worker.py`
| Observability | Exposes Prometheus metrics, OTLP traces, rate-limit counters | OpenTelemetry SDK, Prometheus client | `app/telemetry.py`

### 3.2 Messaging Semantics & Failure Handling

- **Idempotency:** Each event envelope carries a `correlation_id` reused as the Redis idempotency key. Duplicate deliveries are skipped.
- **Back-pressure:** RabbitMQ retry and DLQ exchanges absorb transient Redis failures. The worker requeues messages with exponential back-off based on `ADVANCED_RABBITMQ_RETRY_DELAY_MS`.
- **Client resilience:** Web clients rely on exponential back-off timers (`ADVANCED_RECONNECT_*`) while the SSE endpoint emits heartbeats to keep proxies from timing out idle connections.
- **Readiness signalling:** `/readyz` only flips to `ready` after the event pipeline connects to RabbitMQ and subscribes to Redis, ensuring the app can broadcast events the moment traffic arrives.

## 4. Observability & Operations

- **Metrics:**
  - `advanced_http_requests_total`, `advanced_http_request_duration_seconds` capture FastAPI latency and throughput.
  - `advanced_board_events_published_total` and `advanced_board_event_publish_duration_seconds` measure RabbitMQ publish success/error ratios.
  - Exposed under `/metrics` (default) for Prometheus scraping. GitHub-ready dashboards live in `docker/grafana/`.
- **Tracing:** When `ADVANCED_TELEMETRY_ENABLED=true` and `ADVANCED_OTEL_EXPORTER_OTLP_ENDPOINT` is set, OpenTelemetry spans flow to Jaeger (or your collector). Spans include route templates and status codes.
- **Rate limiting:** SlowAPI guards HTTP and SSE endpoints. `/metrics` and health probes are exempt to keep monitoring uninterrupted.
- **Logging:** Worker logs highlight retry attempts, DLQ routing, and duplicate detection—forward these streams into your log aggregation platform for alerting on sustained retries.

## 5. Scaling & Security Considerations

- **Horizontal scaling:** Multiple FastAPI replicas share a Redis subscription, while RabbitMQ ensures ordered delivery. Scale `advanced-worker` independently to keep up with traffic without saturating the WebSocket layer.
- **Connection limits:** `ADVANCED_WEBSOCKET_MAX_CONNECTIONS` caps concurrent sockets to protect memory. Pair with Kubernetes pod-level limits or autoscaling triggers.
- **Edge hardening:**
  - Token-auth enforced uniformly across HTTP + WebSocket surfaces (`4401` close code for unauthorised sockets).
  - Strict CORS allowlist (`ADVANCED_ALLOWED_ORIGINS`) blocks wildcard origins.
  - Security headers include CSP, HSTS, Referrer-Policy, and Permissions-Policy.
- **Secrets management:** Store tokens, broker credentials, and OTLP headers in a secret manager. CI/CD pipelines should hydrate `.env` files or container env vars securely at deploy time—never commit secrets into the repo.
- **Transport security:** Terminate TLS at your ingress and forward `X-Forwarded-*` headers so rate limiting uses client IPs instead of load balancer origins.

## 6. Configuration Reference

### 6.1 Realtime & Messaging

| Variable | Purpose | Default |
| --- | --- | --- |
| `ADVANCED_REALTIME_TOKEN` | Shared secret required for WebSocket and SSE auth | `change-me-realtime` |
| `ADVANCED_EVENT_TRANSPORT` | `rabbitmq` for production fan-out, `memory` for local/offline testing | `rabbitmq` |
| `ADVANCED_WEBSOCKET_MAX_CONNECTIONS` | Upper bound on concurrent WebSocket sessions per instance | `128` |
| `ADVANCED_BOARD_CHANNEL` | Logical identifier used in payload metadata | `advanced:board` |
| `ADVANCED_ACTIVITY_CHANNEL` | Redis pub/sub channel for SSE + fan-out | `advanced:activity` |
| `ADVANCED_REDIS_URL` | Redis connection string (fan-out + idempotency store) | `redis://localhost:6379/2` |
| `ADVANCED_REDIS_IDEMPOTENCY_TTL_SECONDS` | Lifetime for processed-event markers | `300` |
| `ADVANCED_RABBITMQ_URL` | RabbitMQ connection string for event publication | `amqp://guest:guest@localhost:5672/` |
| `ADVANCED_RABBITMQ_EXCHANGE` | Topic exchange for realtime events | `advanced.board.events` |
| `ADVANCED_RABBITMQ_QUEUE` | Primary consumption queue | `advanced.board.events` |
| `ADVANCED_RABBITMQ_RETRY_QUEUE` | Delayed retry queue name | `advanced.board.events.retry` |
| `ADVANCED_RABBITMQ_DLQ_QUEUE` | Poison message DLQ | `advanced.board.events.dlq` |
| `ADVANCED_RABBITMQ_MAX_RETRIES` | Max retry attempts before DLQ | `5` |
| `ADVANCED_RABBITMQ_RETRY_DELAY_MS` | Delay applied between retries | `5000` |

### 6.2 Edge, Observability & Telemetry

| Variable | Purpose | Default |
| --- | --- | --- |
| `ADVANCED_ALLOWED_ORIGINS` | Comma-separated list of allowed browser origins | `http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173` |
| `ADVANCED_RATE_LIMIT_DEFAULT` | Global rate limit applied by SlowAPI | `120/minute` |
| `ADVANCED_ACTIVITY_STREAM_RATE_LIMIT` | Optional rate limit applied to SSE requests | `30/minute` |
| `ADVANCED_TELEMETRY_ENABLED` | Toggle Prometheus + OTLP instrumentation | `true` |
| `ADVANCED_METRICS_PATH` | Path that serves Prometheus metrics | `/metrics` |
| `ADVANCED_OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector URL for traces | _unset_ |
| `ADVANCED_OTEL_EXPORTER_OTLP_HEADERS` | Comma-separated `key=value` pairs for OTLP auth | _unset_ |
| `ADVANCED_CONTENT_SECURITY_POLICY` | CSP header applied to HTTP responses | Strict default (see `Settings` class) |
| `ADVANCED_STRICT_TRANSPORT_SECURITY` | HSTS header value | `max-age=63072000; includeSubDomains; preload` |

## 7. Deployment & Production Hardening

A full promotion plan—including preflight checks, secret rotation, and observability validation—is captured in [`docs/deployment-checklist.md`](./docs/deployment-checklist.md).

Guidelines for taking this stack to production:

- **CI/CD:** Attach `poetry run pytest -k advanced` and `docker build -f projects/03-advanced/Dockerfile` jobs to your pipeline. Block promotion when tests or image scans fail.
- **Infrastructure-as-code:** Provision Redis, RabbitMQ, and observability endpoints through Terraform/Pulumi (examples in the checklist). Encode topology names (`advanced.board.events*`) directly in IaC to avoid drift.
- **Secrets management:** Inject secrets at deploy time using your platform’s secret store. Rotate the realtime token regularly and notify clients via your config service.
- **Blue/Green or Canary deploys:** Start by rolling out the worker so new events can drain before cutting WebSocket traffic over. Monitor RabbitMQ queue depth and `/readyz` before shifting load balancers.
- **Disaster recovery:** Document backup strategies for RabbitMQ (definitions + persistent queues) and Redis (AOF snapshot). For stateless events, preserving queue durability often suffices.

## 8. Troubleshooting Guide

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| WebSocket closes immediately with code `4401` | Missing or incorrect realtime token | Confirm `ADVANCED_REALTIME_TOKEN` in both app/worker env and client requests; rotate token via secret manager if compromised |
| SSE stream connects but never emits events | Worker not running or Redis creds invalid | Ensure `poetry run advanced-worker` (or deployment equivalent) is active; verify Redis URL/credentials and inspect worker logs for retry warnings |
| `/readyz` reports `event_pipeline_ready=false` | RabbitMQ unreachable or credentials rejected | Check RabbitMQ health, exchange/queue existence, and network ACLs; restart the app after fixing broker connectivity |
| RabbitMQ retry/DLQ queues filling up | Redis publish failures or idempotency store unavailable | Inspect worker logs, confirm Redis readiness, and ensure Redis password matches `ADVANCED_REDIS_URL` |
| `/metrics` returns `503` with `telemetry disabled` message | Telemetry toggled off | Set `ADVANCED_TELEMETRY_ENABLED=true` and restart the service; ensure Prometheus isn’t scraping disabled environments |
| Clients receive 429 responses on SSE | Activity stream rate limit too low for usage | Increase `ADVANCED_ACTIVITY_STREAM_RATE_LIMIT`, or exempt trusted automation by adjusting SlowAPI rate limit headers |

## 9. Verification Scripts & Tests

- Automated regression suite: `poetry run pytest -k advanced`
- Targeted realtime tests: `poetry run pytest tests/test_advanced_realtime.py`
- Messaging pipeline smoke: `poetry run pytest tests/test_advanced_messaging_bus.py`
- Observability contract: `poetry run pytest tests/test_advanced_observability.py`
- End-to-end manual probe: `poetry run python scripts/advanced_pipeline_demo.py`

## 10. Extension Exercises

1. **Multi-tenant routing:** Augment `BoardMessage` with organisation identifiers and exchange tokens for JWTs that enumerate allowed boards. Enforce the mapping in the worker to avoid cross-tenant leakage.
2. **Guaranteed delivery analytics:** Persist ActivityEvents to ClickHouse or BigQuery for audit trails, then expose a replay endpoint for late-joining clients.
3. **Adaptive rate limiting:** Feed Prometheus metrics into an admission controller that tightens or loosens rate limits based on current fan-out latency.
4. **Synthetic monitoring:** Deploy a cron-based job using `scripts/advanced_pipeline_demo.py` to continuously validate the path from WebSocket ingress to SSE delivery, alerting on latency thresholds.

---

Supporting diagrams and deployment collateral live under [`./docs/`](./docs/). For contribution workflow and style conventions, see [CONTRIBUTING.md](../../CONTRIBUTING.md).
