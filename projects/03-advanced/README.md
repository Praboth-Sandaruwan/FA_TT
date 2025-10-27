# Advanced Realtime Collaboration Project

## 1. Introduction

- **Purpose:** Demonstrates a production-ready realtime layer using FastAPI with WebSockets
  and Server-Sent Events (SSE) to power a collaborative kanban + chat experience. The project
  highlights authenticated bi-directional messaging, broadcast fan-out, and resilient client
  reconnection strategies.
- **Audience:** Engineers who need an end-to-end example of how to blend websocket updates with SSE
  feeds while enforcing authentication for every realtime surface.
- **Status & Owners:** Status – active (development). Maintainers – Platform Enablement group. Base new
  documentation from the shared [template](../../docs/template.md).

## 2. Setup & Getting Started

### 2.1 Prerequisites

- Python 3.12 and [Poetry 1.8.x](https://python-poetry.org/)
- Redis 7+ (optional for future channel fan-out; current demo uses in-memory broker)
- Recommended: enable git hooks from the repository root (`poetry run pre-commit install`)

### 2.2 Local Environment Setup

1. Copy the environment template and provide a strong realtime token:

   ```bash
   cp projects/03-advanced/.env.example projects/03-advanced/.env
   # Edit projects/03-advanced/.env and replace ADVANCED_REALTIME_TOKEN
   ```

2. Install dependencies (from the repository root):

   ```bash
   poetry install
   ```

3. Launch the FastAPI application:

   ```bash
   poetry run advanced-app
   ```

4. Open the realtime playground at [http://localhost:8004](http://localhost:8004) and paste the token
   into the connection form. Open the page in two browser windows to watch updates propagate.

### 2.3 Verification

- WebSocket handshake: use the docs or a websocket client to connect to `/ws/boards/demo?token=<token>`.
- SSE stream: curl keeps connections open and prints events – `curl -N "http://localhost:8004/sse/activity?token=<token>"`.
- Activity demo: add cards or chat messages in one browser tab and confirm the other tab reflects the
  updates instantly.

## 3. Architecture Overview

The realtime layer is intentionally framework-light:

- **WebSockets:** Accept authenticated clients on `/ws/boards/{board_id}`. A shared `RealtimeBroker`
  holds websocket references, fans out JSON messages to every participant, and mirrors each event to the
  activity feed.
- **Server-Sent Events:** `/sse/activity` streams the same event objects that the websocket clients
  consume. Each subscriber receives heartbeats to keep the connection alive, plus broadcast payloads as
  soon as the broker publishes them.
- **Authentication:** Websocket and SSE connections validate a bearer token supplied either as a
  `token` query parameter or `Authorization: Bearer <token>` header. Unauthenticated sessions are
  closed with code `4401` before any data exchange.
- **Resilience:** The frontend ships with an exponential back-off reconnection loop for websockets, and
  the native `EventSource` handles SSE retries automatically. Client counts are maintained server-side
  and sent with every event so the UI can display the number of connected collaborators.

The realtime broker currently stores connections in memory. Redis channel fan-out is reserved via the
`ADVANCED_*` settings to illustrate how the deployment can scale out with a proper pub/sub backend.

## 4. Feature Walkthrough

1. **Authenticate once:** Enter the realtime token in the UI. Credentials are reused for websocket and
   SSE channels and stored only in page memory.
2. **Broadcast board updates:** Submitting the card form emits a `card.added` message. Every websocket
   client updates the kanban board in real time.
3. **Chat in real time:** Messages travel as `chat.message` events. The chat log and the SSE-backed
   activity feed both reflect the message instantly.
4. **Observe activity history:** The SSE activity feed lists all actions across clients with timestamps,
   making it ideal for audit trails or toast notifications in richer applications.
5. **Automatic reconnection:** Disconnect the network or terminate the server process; the UI
   transparently reconnects when possible and retains a rolling view of the feed and board state.

## 5. Configuration Reference

| Variable | Purpose | Default |
| --- | --- | --- |
| `ADVANCED_APP_HOST` | Host interface for development server | `0.0.0.0` |
| `ADVANCED_APP_PORT` | HTTP port | `8004` |
| `ADVANCED_REALTIME_TOKEN` | Shared secret required for websocket + SSE auth | `change-me-realtime` |
| `ADVANCED_ALLOWED_ORIGINS` | CORS allowlist | `http://localhost:3000,http://127.0.0.1:3000` |
| `ADVANCED_BOARD_CHANNEL` | Logical channel name for board events | `advanced:board` |
| `ADVANCED_ACTIVITY_CHANNEL` | Logical channel for activity feed | `advanced:activity` |
| `ADVANCED_REDIS_URL` | Planned Redis pub/sub endpoint (not required for local demo) | `redis://:app@localhost:6379/2` |
| `ADVANCED_SSE_HEARTBEAT_SECONDS` | Idle timeout before emitting SSE heartbeats | `15` |
| `ADVANCED_WEBSOCKET_MAX_CONNECTIONS` | Upper bound on concurrent websocket sessions | `256` |
| `ADVANCED_RECONNECT_INITIAL_DELAY_SECONDS` | Client reconnect delay baseline | `1.5` |
| `ADVANCED_RECONNECT_MAX_DELAY_SECONDS` | Cap for websocket reconnect delay | `12.0` |

## 6. Testing

Automated tests live at the repository root and exercise websocket and SSE flows with real clients.
Run the full suite from the project root:

```bash
poetry run pytest -k advanced
```

The tests verify:

- Authenticated websocket handshakes using both query parameters and bearer headers.
- Broadcast fan-out to multiple websocket clients.
- SSE event delivery mirrors websocket updates and enforces authentication.

## 7. Next Steps

- Swap the in-memory broker for Redis pub/sub, allowing multiple app replicas to share realtime state.
- Persist kanban state in Postgres and replay activity feed events for late-joining clients.
- Add fine-grained channel auth so tokens encode boards and permissions for multi-team deployments.

---

Refer to [CONTRIBUTING.md](../../CONTRIBUTING.md) for contribution workflow and style guidance.
