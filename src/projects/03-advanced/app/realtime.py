"""Realtime coordination primitives for websockets and server-sent events."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from .config import Settings


class ConnectionLimitExceeded(RuntimeError):
    """Raised when the websocket connection pool is exhausted."""


class BoardMessage(BaseModel):
    """Payload accepted from websocket clients."""

    action: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    user: str = Field(default="anonymous")
    message: str | None = None
    correlation_id: str | None = None

    @field_validator("user")
    @classmethod
    def _normalise_user(cls, value: str) -> str:
        candidate = value.strip()
        return candidate or "anonymous"


class ActivityEvent(BaseModel):
    """Event broadcast to websocket and SSE observers."""

    id: str
    board: str
    action: str
    user: str
    payload: dict[str, Any]
    timestamp: datetime
    correlation_id: str | None = None
    kind: str = "board_event"
    active_connections: int = 0


def build_activity_event(
    board_id: str,
    message: BoardMessage,
    *,
    event_id: str | None = None,
    correlation_id: str | None = None,
) -> ActivityEvent:
    """Create a canonical activity event from a client message."""

    payload = dict(message.payload)
    if message.message and "message" not in payload:
        payload["message"] = message.message
    return ActivityEvent(
        id=event_id or str(uuid4()),
        board=board_id,
        action=message.action,
        user=message.user,
        payload=payload,
        timestamp=datetime.now(timezone.utc),
        correlation_id=correlation_id or message.correlation_id,
    )


class RealtimeBroker:
    """Tracks websocket connections and SSE listener queues."""

    def __init__(self) -> None:
        self._boards: dict[str, set[WebSocket]] = defaultdict(set)
        self._activity_subscribers: list[asyncio.Queue[ActivityEvent]] = []
        self._lock = asyncio.Lock()

    async def connect(self, board_id: str, websocket: WebSocket, settings: Settings) -> int:
        """Register a websocket connection for the given board."""

        async with self._lock:
            total_connections = sum(len(connections) for connections in self._boards.values())
            if total_connections >= settings.websocket_max_connections:
                raise ConnectionLimitExceeded("Websocket connection limit reached.")
            self._boards[board_id].add(websocket)
            active = len(self._boards[board_id])
        await websocket.accept()
        return active

    async def disconnect(self, board_id: str, websocket: WebSocket) -> None:
        """Remove a websocket connection from the board registry."""

        async with self._lock:
            connections = self._boards.get(board_id)
            if not connections:
                return
            connections.discard(websocket)
            if not connections:
                self._boards.pop(board_id, None)

    async def broadcast(self, event: ActivityEvent) -> None:
        """Send an activity event to websocket clients and SSE listeners."""

        async with self._lock:
            connections = list(self._boards.get(event.board, set()))
            listeners = list(self._activity_subscribers)
        enriched = event.model_copy(update={"active_connections": len(connections)})

        stale: list[WebSocket] = []
        for websocket in connections:
            if websocket.application_state != WebSocketState.CONNECTED:
                stale.append(websocket)
                continue
            try:
                await websocket.send_json(enriched.model_dump())
            except WebSocketDisconnect:
                stale.append(websocket)
            except RuntimeError:
                stale.append(websocket)

        if stale:
            async with self._lock:
                for websocket in stale:
                    for clients in self._boards.values():
                        clients.discard(websocket)

        for queue in listeners:
            queue.put_nowait(enriched)

    async def register_activity_listener(self) -> asyncio.Queue[ActivityEvent]:
        """Add a new SSE listener queue."""

        queue: asyncio.Queue[ActivityEvent] = asyncio.Queue()
        async with self._lock:
            self._activity_subscribers.append(queue)
        return queue

    async def unregister_activity_listener(self, queue: asyncio.Queue[ActivityEvent]) -> None:
        """Remove an SSE listener queue when clients disconnect."""

        async with self._lock:
            if queue in self._activity_subscribers:
                self._activity_subscribers.remove(queue)

    async def reset(self) -> None:
        """Clear all websockets and listeners (used by tests)."""

        async with self._lock:
            self._boards.clear()
            self._activity_subscribers.clear()


broker = RealtimeBroker()

__all__ = [
    "ActivityEvent",
    "BoardMessage",
    "RealtimeBroker",
    "ConnectionLimitExceeded",
    "build_activity_event",
    "broker",
]
