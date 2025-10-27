"""Background worker that consumes board events from RabbitMQ and broadcasts via Redis."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aio_pika
from aio_pika import DeliveryMode, Message, RobustChannel, RobustConnection
from aio_pika.abc import AbstractIncomingMessage
from pydantic import ValidationError

from .config import Settings, get_settings
from .messaging import (
    BoardEventEnvelope,
    RabbitTopology,
    RedisBroadcaster,
    RedisIdempotencyStore,
    declare_rabbitmq_topology,
)
from .realtime import build_activity_event

logger = logging.getLogger(__name__)


class BoardEventConsumer:
    """Consume board events and fan them out via Redis."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: RobustConnection | None = None
        self._channel: RobustChannel | None = None
        self._topology: RabbitTopology | None = None
        self._consumer_tag: str | None = None
        self._redis = RedisBroadcaster(settings)
        self._idempotency: RedisIdempotencyStore | None = None
        self._stop_requested = asyncio.Event()

    async def start(self) -> None:
        logger.info("Starting board event consumer")
        await self._redis.start()
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self._settings.rabbitmq_prefetch_count)
        self._topology = await declare_rabbitmq_topology(self._channel, self._settings)
        self._idempotency = RedisIdempotencyStore(self._redis.redis, self._settings)
        self._stop_requested.clear()
        self._consumer_tag = await self._topology.queue.consume(self._on_message, no_ack=False)
        logger.info(
            "RabbitMQ consumer ready",
            extra={
                "queue": self._settings.rabbitmq_queue,
                "retry_queue": self._settings.rabbitmq_retry_queue,
                "dlq": self._settings.rabbitmq_dlq_queue,
            },
        )

    async def stop(self) -> None:
        self._stop_requested.set()
        if self._topology and self._consumer_tag:
            with contextlib.suppress(Exception):
                await self._topology.queue.cancel(self._consumer_tag)
        if self._channel:
            await self._channel.close()
        if self._connection:
            await self._connection.close()
        await self._redis.stop()
        self._consumer_tag = None
        self._channel = None
        self._connection = None
        self._topology = None
        self._idempotency = None
        logger.info("Board event consumer stopped")

    def request_stop(self) -> None:
        """Signal the consumer loop to stop."""

        self._stop_requested.set()

    async def run(self) -> None:
        """Block until a stop has been requested."""

        await self._stop_requested.wait()

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        if not self._idempotency or not self._topology:
            logger.error("Received message before consumer initialisation; rejecting")
            await message.reject(requeue=False)
            return

        try:
            payload = message.body.decode("utf-8")
            envelope = BoardEventEnvelope.model_validate_json(payload)
        except (UnicodeDecodeError, ValidationError) as exc:
            logger.exception("Invalid event payload received; forwarding to DLQ", exc_info=exc)
            await self._send_raw_to_dlq(message, reason="invalid_payload", extra={"error": str(exc)})
            await message.ack()
            return

        if await self._idempotency.is_processed(envelope.idempotency_key):
            logger.debug(
                "Skipping duplicate board event",
                extra={"event_id": envelope.event_id, "key": envelope.idempotency_key},
            )
            await message.ack()
            return

        event = build_activity_event(
            envelope.board_id,
            envelope.message,
            event_id=envelope.event_id,
            correlation_id=envelope.correlation_id,
        )

        try:
            await self._redis.publish(event)
            await self._idempotency.mark_processed(envelope.idempotency_key)
        except Exception as exc:  # pragma: no cover - network/transient failures
            logger.exception(
                "Failed to fan out event; scheduling retry",
                extra={"event_id": envelope.event_id, "board_id": envelope.board_id},
            )
            await self._handle_failure(message, envelope, exc)
            return

        await message.ack()

    async def _handle_failure(
        self,
        message: AbstractIncomingMessage,
        envelope: BoardEventEnvelope,
        exc: Exception,
    ) -> None:
        attempts = _extract_retry_count(message)
        if attempts >= self._settings.rabbitmq_max_retries:
            await self._send_to_dlq(message, envelope, exc, attempts)
        else:
            await self._send_to_retry(message, envelope, exc, attempts + 1)
        await message.ack()

    async def _send_to_retry(
        self,
        message: AbstractIncomingMessage,
        envelope: BoardEventEnvelope,
        exc: Exception,
        attempt: int,
    ) -> None:
        if not self._topology:
            return
        headers = dict(message.headers or {})
        headers["x-retry-count"] = attempt
        headers["last-error"] = str(exc)
        retry_message = Message(
            body=message.body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=envelope.event_id,
            timestamp=datetime.now(timezone.utc),
            headers=headers,
        )
        await self._topology.retry_exchange.publish(
            retry_message, routing_key=self._settings.rabbitmq_retry_routing_key
        )
        logger.warning(
            "Event processing failed; queued retry",
            extra={"event_id": envelope.event_id, "board_id": envelope.board_id, "attempt": attempt},
        )

    async def _send_to_dlq(
        self,
        message: AbstractIncomingMessage,
        envelope: BoardEventEnvelope,
        exc: Exception,
        attempts: int,
    ) -> None:
        if not self._topology:
            return
        headers = dict(message.headers or {})
        headers["x-retry-count"] = attempts
        headers["last-error"] = str(exc)
        dlq_message = Message(
            body=message.body,
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=envelope.event_id,
            timestamp=datetime.now(timezone.utc),
            headers=headers,
        )
        await self._topology.dlq_exchange.publish(
            dlq_message, routing_key=self._settings.rabbitmq_dlq_routing_key
        )
        logger.error(
            "Poison board event routed to DLQ",
            extra={
                "event_id": envelope.event_id,
                "board_id": envelope.board_id,
                "attempts": attempts,
            },
            exc_info=exc,
        )

    async def _send_raw_to_dlq(
        self,
        message: AbstractIncomingMessage,
        *,
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if not self._topology:
            return
        headers = dict(message.headers or {})
        headers["failure_reason"] = reason
        if extra:
            headers.update(extra)
        dlq_message = Message(
            body=message.body,
            content_type=message.content_type or "application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=message.message_id or str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            headers=headers,
        )
        await self._topology.dlq_exchange.publish(
            dlq_message, routing_key=self._settings.rabbitmq_dlq_routing_key
        )


def _extract_retry_count(message: AbstractIncomingMessage) -> int:
    raw = (message.headers or {}).get("x-retry-count", 0)
    try:
        return int(raw)
    except (TypeError, ValueError):  # pragma: no cover - defensive path
        return 0


async def serve(settings: Settings) -> None:
    consumer = BoardEventConsumer(settings)
    await consumer.start()

    loop = asyncio.get_running_loop()
    stop_signals = (signal.SIGINT, signal.SIGTERM)

    for sig in stop_signals:
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, consumer.request_stop)

    try:
        await consumer.run()
    finally:
        for sig in stop_signals:
            with contextlib.suppress(NotImplementedError):
                loop.remove_signal_handler(sig)
        await consumer.stop()


def run() -> None:
    """Entrypoint for ``poetry run advanced-worker``."""

    settings: Settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve(settings))


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    run()
