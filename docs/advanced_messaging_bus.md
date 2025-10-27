# Advanced messaging bus

The advanced realtime stack now pushes every board event through RabbitMQ before
fan-out to websocket and Server-Sent Event clients. This mirrors production
topologies where API processes remain lightweight and background workers handle
fan-out, retries, and error isolation.

## Architecture overview

```
WebSocket client  ──▶ FastAPI (writes BoardMessage)
                      │
                      ├─▶ RabbitMQ exchange ``advanced.board.events``
                      │
                      └─▶ Retry exchange ``advanced.board.events.retry`` (delayed)

RabbitMQ consumer ──▶ Redis pub/sub ``advanced:activity`` ──▶ In-process broker ──▶ WebSocket/SSE clients
                                      ▲
                                      └─▶ Redis idempotency keys ``advanced:idempotency:<key>``
```

Key characteristics:

- **RabbitMQ** provides durable queues, retry routing, and a dedicated dead letter
  queue for poison messages. Failed deliveries log at `ERROR` level before being
  parked in the DLQ for inspection.
- **Redis** handles cross-process fan-out. Consumers publish processed
  `ActivityEvent` payloads to a shared channel; every API instance subscribes and
  relays events to connected clients.
- **Idempotency** is enforced via Redis keys to prevent duplicated broadcasts
  when messages are retried.

## Running the pipeline locally

1. Start the stack, including the new advanced services:

   ```bash
   docker compose up -d --build advanced-app advanced-worker redis rabbitmq
   ```

   The `advanced-app` container serves the FastAPI application on
   `http://localhost:8004`, while `advanced-worker` continuously drains the
   RabbitMQ queue and fan-outs events via Redis.

2. Send a demo event and observe the broadcast:

   ```bash
   poetry run python scripts/advanced_pipeline_demo.py
   ```

   The helper script opens both the websocket and SSE endpoints, publishes a
   board message, and prints the resulting activity event after it travels
   through RabbitMQ and Redis. Ensure the realtime token in your environment
   matches the application configuration (`ADVANCED_REALTIME_TOKEN`).

3. Inspect the RabbitMQ dead letter queue if failures occur:

   ```bash
   docker compose exec rabbitmq rabbitmqadmin --username app --password app get queue=advanced.board.events.dlq
   ```

   The worker logs every poison message at `ERROR` level with context metadata
   (`event_id`, `board_id`, retry attempts) to simplify alerting or forwarding
   into your observability stack.

## Configuration reference

Environment variables prefixed with `ADVANCED_` control the runtime behaviour of
both the API process and the worker. The defaults in `.env.example` provide a
development-friendly setup that mirrors production naming so configuration can
be promoted without surprises.

| Variable | Description |
| --- | --- |
| `ADVANCED_EVENT_TRANSPORT` | Set to `rabbitmq` (default) to enable the full pipeline. Use `memory` for local unit tests. |
| `ADVANCED_RABBITMQ_URL` | Connection URI for the RabbitMQ cluster. |
| `ADVANCED_RABBITMQ_EXCHANGE` / `ADVANCED_RABBITMQ_QUEUE` | Durable exchange/queue handling new board events. |
| `ADVANCED_RABBITMQ_RETRY_*` | Retry exchange/queue and delay (ms) used for exponential backoff. |
| `ADVANCED_RABBITMQ_DLQ_*` | Dead letter exchange/queue for poison messages. |
| `ADVANCED_RABBITMQ_MAX_RETRIES` | Maximum retry attempts before a message is routed to the DLQ. |
| `ADVANCED_RABBITMQ_PREFETCH_COUNT` | Consumer prefetch for RabbitMQ backpressure control. |
| `ADVANCED_REDIS_URL` | Redis instance used for pub/sub and idempotency keys. |
| `ADVANCED_REDIS_IDEMPOTENCY_PREFIX` / `ADVANCED_REDIS_IDEMPOTENCY_TTL_SECONDS` | Namespace and TTL for processed message keys. |
| `ADVANCED_REALTIME_TOKEN` | Shared secret required for websocket and SSE clients. |
| `ADVANCED_ACTIVITY_CHANNEL` | Redis channel published by the worker and consumed by the API instances. |

For production parity, keep exchange, queue, and channel names identical across
environments. Point `ADVANCED_RABBITMQ_URL` and `ADVANCED_REDIS_URL` at managed
infrastructure while leaving application level settings untouched.

## Testing

- Unit tests exercising the messaging helpers live in
  `tests/test_advanced_messaging_bus.py` and cover envelope construction,
  in-memory pipelines, and idempotency storage.
- The existing realtime tests (`tests/test_advanced_realtime.py`) run with the
  in-memory transport to keep the suite hermetic, while integration testing
  against live RabbitMQ/Redis is supported via the included demo script.

Together these safeguards ensure the advanced messaging bus behaves consistently
from localhost through to production deployments.
