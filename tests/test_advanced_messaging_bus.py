from __future__ import annotations

import asyncio

import pytest

from projects.03-advanced.app.config import Settings
from projects.03-advanced.app.messaging import (
    BoardEventEnvelope,
    EventPipeline,
    RedisIdempotencyStore,
)
from projects.03-advanced.app.realtime import ActivityEvent, BoardMessage

try:  # pragma: no cover - optional test dependency
    import fakeredis.aioredis as fakeredis
except Exception:  # pragma: no cover - fallback for environments without fakeredis
    fakeredis = None


def test_board_event_envelope_correlation() -> None:
    message = BoardMessage(action="card.created", payload={"title": "Example"})
    envelope = BoardEventEnvelope.from_message("demo", message)
    assert envelope.correlation_id
    assert envelope.message.correlation_id == envelope.correlation_id
    assert envelope.event_id


@pytest.mark.asyncio()
async def test_in_memory_pipeline_broadcasts_events() -> None:
    received: list[ActivityEvent] = []

    async def handler(event: ActivityEvent) -> None:
        received.append(event)

    settings = Settings(event_transport="memory")
    pipeline = EventPipeline(settings, handler)
    await pipeline.start()
    try:
        envelope = BoardEventEnvelope.from_message(
            "board-123",
            BoardMessage(action="card.moved", payload={"column": "doing"}),
        )
        await pipeline.publish(envelope)
        await asyncio.sleep(0)
    finally:
        await pipeline.stop()

    assert len(received) == 1
    event = received[0]
    assert event.board == "board-123"
    assert event.action == "card.moved"
    assert event.correlation_id == envelope.correlation_id


@pytest.mark.asyncio()
@pytest.mark.skipif(fakeredis is None, reason="fakeredis is required for this test")
async def test_idempotency_store_prevents_duplicates() -> None:
    fake_redis = fakeredis.FakeRedis()
    settings = Settings()
    store = RedisIdempotencyStore(fake_redis, settings)

    assert await store.is_processed("abc123") is False
    await store.mark_processed("abc123")
    assert await store.is_processed("abc123") is True

    await fake_redis.close()
