"""Messaging bus integration for the advanced realtime application."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Protocol
from uuid import uuid4

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message, RobustChannel, RobustConnection
from aio_pika.abc import AbstractExchange, AbstractQueue
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from .config import Settings
from .realtime import ActivityEvent, BoardMessage, build_activity_event

logger = logging.getLogger(__name__)

EventHandler = Callable[[ActivityEvent], Awaitable[None]]


class BoardEventEnvelope(BaseModel):
    """Canonical transport envelope for board events."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    board_id: str
    message: BoardMessage
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str
    idempotency_key: str

    @classmethod
    def from_message(cls, board_id: str, message: BoardMessage) -> "BoardEventEnvelope":
        correlation_id = message.correlation_id or str(uuid4())
        message_copy = message.model_copy(update={"correlation_id": correlation_id})
        return cls(
            board_id=board_id,
            message=message_copy,
            correlation_id=correlation_id,
            idempotency_key=correlation_id,
        )

    def json_bytes(self) -> bytes:
        """Serialise the envelope for transport."""

        return self.model_dump_json().encode("utf-8")


class EventPublisher(Protocol):
    """Protocol implemented by event publishers."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def publish(self, envelope: BoardEventEnvelope) -> None: ...


class InMemoryEventPublisher:
    """Event publisher used in tests that bypasses external brokers."""

    def __init__(self, handler: EventHandler) -> None:
        self._handler = handler

    async def start(self) -> None:  # noqa: D401 - interface parity
        return None

    async def stop(self) -> None:  # noqa: D401 - interface parity
        return None

    async def publish(self, envelope: BoardEventEnvelope) -> None:
        event = build_activity_event(
            envelope.board_id,
            envelope.message,
            event_id=envelope.event_id,
            correlation_id=envelope.correlation_id,
        )
        await self._handler(event)


@dataclass
class RabbitTopology:
    """Declared exchanges and queues for the messaging topology."""

    exchange: AbstractExchange
    retry_exchange: AbstractExchange
    dlq_exchange: AbstractExchange
    queue: AbstractQueue
    retry_queue: AbstractQueue
    dlq_queue: AbstractQueue


async def declare_rabbitmq_topology(channel: RobustChannel, settings: Settings) -> RabbitTopology:
    """Ensure exchanges and queues exist for the realtime pipeline."""

    exchange = await channel.declare_exchange(
        settings.rabbitmq_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )
    retry_exchange = await channel.declare_exchange(
        settings.rabbitmq_retry_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )
    dlq_exchange = await channel.declare_exchange(
        settings.rabbitmq_dlq_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )

    queue = await channel.declare_queue(settings.rabbitmq_queue, durable=True)
    await queue.bind(exchange, routing_key=settings.rabbitmq_routing_key)

    retry_queue = await channel.declare_queue(
        settings.rabbitmq_retry_queue,
        durable=True,
        arguments={
            "x-message-ttl": settings.rabbitmq_retry_delay_ms,
            "x-dead-letter-exchange": settings.rabbitmq_exchange,
            "x-dead-letter-routing-key": settings.rabbitmq_routing_key,
        },
    )
    await retry_queue.bind(retry_exchange, routing_key=settings.rabbitmq_retry_routing_key)

    dlq_queue = await channel.declare_queue(settings.rabbitmq_dlq_queue, durable=True)
    await dlq_queue.bind(dlq_exchange, routing_key=settings.rabbitmq_dlq_routing_key)

    return RabbitTopology(
        exchange=exchange,
        retry_exchange=retry_exchange,
        dlq_exchange=dlq_exchange,
        queue=queue,
        retry_queue=retry_queue,
        dlq_queue=dlq_queue,
    )


class RabbitMQEventPublisher:
    """Publish board events to RabbitMQ."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: RobustConnection | None = None
        self._channel: RobustChannel | None = None
        self._topology: RabbitTopology | None = None

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self._settings.rabbitmq_prefetch_count)
        self._topology = await declare_rabbitmq_topology(self._channel, self._settings)
        logger.info(
            "RabbitMQ publisher ready",
            extra={
                "exchange": self._settings.rabbitmq_exchange,
                "queue": self._settings.rabbitmq_queue,
            },
        )

    async def stop(self) -> None:
        if self._channel:
            await self._channel.close()
        if self._connection:
            await self._connection.close()
        self._channel = None
        self._connection = None
        self._topology = None

    async def publish(self, envelope: BoardEventEnvelope) -> None:
        if not self._topology:
            raise RuntimeError("RabbitMQ publisher has not been started.")
        message = Message(
            body=envelope.json_bytes(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=envelope.event_id,
            timestamp=envelope.published_at,
            headers={
                "correlation_id": envelope.correlation_id,
                "idempotency_key": envelope.idempotency_key,
            },
        )
        await self._topology.exchange.publish(
            message, routing_key=self._settings.rabbitmq_routing_key
        )


class RedisBroadcaster:
    """Publish processed events to Redis channels for fan-out."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._redis: Redis | None = None

    async def start(self) -> None:
        if self._redis:
            return
        self._redis = Redis.from_url(
            self._settings.redis_url,
            encoding="utf-8",
            decode_responses=False,
        )

    async def stop(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _require_redis(self) -> Redis:
        if not self._redis:
            raise RuntimeError("Redis connection has not been initialised.")
        return self._redis

    @property
    def redis(self) -> Redis:
        """Return the underlying Redis connection."""

        return self._require_redis()

    async def publish(self, event: ActivityEvent) -> None:
        payload = event.model_dump_json().encode("utf-8")
        await self._require_redis().publish(self._settings.activity_channel, payload)


class RedisIdempotencyStore:
    """Tracks processed messages to avoid duplicate fan-out."""

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    def _key(self, key: str) -> str:
        return f"{self._settings.redis_idempotency_prefix}:{key}"

    async def is_processed(self, key: str) -> bool:
        namespaced = self._key(key)
        return bool(await self._redis.exists(namespaced))

    async def mark_processed(self, key: str) -> None:
        ttl = max(1, int(self._settings.redis_idempotency_ttl_seconds))
        await self._redis.set(self._key(key), "1", ex=ttl)


class RedisActivitySubscriber:
    """Subscribe to Redis pub/sub to relay activity events to websocket clients."""

    def __init__(self, settings: Settings, handler: EventHandler) -> None:
        self._settings = settings
        self._handler = handler
        self._redis: Redis | None = None
        self._pubsub: PubSub | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        self._stopped.clear()
        await self._initialise_pubsub()
        assert self._pubsub is not None
        self._task = asyncio.create_task(self._listen_loop(), name="advanced-redis-subscriber")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._pubsub:
            with contextlib.suppress(Exception):
                await self._pubsub.unsubscribe(self._settings.activity_channel)
                await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def _initialise_pubsub(self) -> None:
        if self._pubsub:
            with contextlib.suppress(Exception):
                await self._pubsub.unsubscribe(self._settings.activity_channel)
                await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
        self._redis = Redis.from_url(
            self._settings.redis_url,
            encoding="utf-8",
            decode_responses=False,
        )
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self._settings.activity_channel)

    async def _listen_loop(self) -> None:
        assert self._pubsub is not None
        backoff = self._settings.reconnect_initial_delay_seconds
        max_backoff = self._settings.reconnect_max_delay_seconds

        while not self._stopped.is_set():
            try:
                async for message in self._pubsub.listen():
                    if self._stopped.is_set():
                        break
                    if message.get("type") != "message":
                        continue
                    data = message.get("data")
                    if isinstance(data, bytes):
                        payload = data.decode("utf-8")
                    else:
                        payload = str(data)
                    event = ActivityEvent.model_validate_json(payload)
                    try:
                        await self._handler(event)
                    except Exception:  # pragma: no cover - defensive logging path
                        logger.exception(
                            "Activity handler raised an exception", extra={"board": event.board}
                        )
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive logging path
                logger.exception("Redis pub/sub listener encountered an error; retrying")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
                await self._initialise_pubsub()
            else:
                backoff = self._settings.reconnect_initial_delay_seconds


class EventPipeline:
    """Coordinates event publication and downstream fan-out."""

    def __init__(self, settings: Settings, handler: EventHandler) -> None:
        self._settings = settings
        self._handler = handler
        self._publisher: EventPublisher | None = None
        self._subscriber: RedisActivitySubscriber | None = None

    async def start(self) -> None:
        if self._settings.event_transport == "memory":
            self._publisher = InMemoryEventPublisher(self._handler)
            await self._publisher.start()
            return

        self._subscriber = RedisActivitySubscriber(self._settings, self._handler)
        await self._subscriber.start()
        publisher = RabbitMQEventPublisher(self._settings)
        try:
            await publisher.start()
        except Exception:
            await self._subscriber.stop()
            self._subscriber = None
            raise
        self._publisher = publisher

    async def stop(self) -> None:
        if self._publisher:
            await self._publisher.stop()
            self._publisher = None
        if self._subscriber:
            await self._subscriber.stop()
            self._subscriber = None

    async def publish(self, envelope: BoardEventEnvelope) -> None:
        if not self._publisher:
            raise RuntimeError("Event pipeline has not been started.")
        await self._publisher.publish(envelope)


__all__ = [
    "BoardEventEnvelope",
    "EventPipeline",
    "InMemoryEventPublisher",
    "RabbitMQEventPublisher",
    "RabbitTopology",
    "RedisActivitySubscriber",
    "RedisBroadcaster",
    "RedisIdempotencyStore",
    "declare_rabbitmq_topology",
]
