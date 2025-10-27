from __future__ import annotations

import asyncio
import json
import logging
from threading import Lock
from typing import Any, Awaitable, Callable, TypeVar, cast

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from redis.asyncio import Redis

from .config import get_settings

T = TypeVar("T")

logger = logging.getLogger("projects.02-intermediate.app.core.cache")

TASK_LIST_CACHE_NAMESPACE = "tasks:list"
TASK_STATISTICS_CACHE_NAMESPACE = "tasks:statistics"


class CacheMetrics:
    """In-memory counters for cache behaviour instrumentation."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.hits = 0
        self.misses = 0
        self.stores = 0
        self.invalidations = 0
        self.skipped = 0

    def _bump(self, attribute: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, attribute, getattr(self, attribute) + amount)

    def record_hit(self) -> None:
        self._bump("hits")

    def record_miss(self) -> None:
        self._bump("misses")

    def record_store(self) -> None:
        self._bump("stores")

    def record_invalidation(self, amount: int = 1) -> None:
        self._bump("invalidations", amount)

    def record_skipped(self) -> None:
        self._bump("skipped")

    def reset(self) -> None:
        with self._lock:
            self.hits = 0
            self.misses = 0
            self.stores = 0
            self.invalidations = 0
            self.skipped = 0

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "stores": self.stores,
                "invalidations": self.invalidations,
                "skipped": self.skipped,
            }


cache_metrics = CacheMetrics()

_redis_client: Redis | None = None
_redis_lock = asyncio.Lock()
_connection_error_logged = False


def set_cache_client(client: Redis | None) -> None:
    """Inject a Redis client instance (primarily for tests)."""

    global _redis_client, _connection_error_logged
    _redis_client = client
    _connection_error_logged = False


async def close_cache_client() -> None:
    """Close the active Redis client, if any."""

    global _redis_client
    client = _redis_client
    if client is not None:
        await client.close()
    _redis_client = None


async def _create_redis_client() -> Redis | None:
    global _connection_error_logged

    settings = get_settings()
    try:
        client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        await client.ping()
    except Exception:  # pragma: no cover - network failure scenarios
        if not _connection_error_logged:
            logger.warning("Redis cache unavailable; caching will be bypassed.", exc_info=True)
            _connection_error_logged = True
        return None
    else:
        _connection_error_logged = False
        return client


async def get_cache_client() -> Redis | None:
    """Return a connected Redis client or ``None`` if caching is disabled."""

    settings = get_settings()
    if not settings.cache_enabled:
        return None

    global _redis_client
    if _redis_client is not None:
        return _redis_client

    async with _redis_lock:
        if _redis_client is None:
            _redis_client = await _create_redis_client()
        return _redis_client


async def cache_get_or_set(
    *,
    namespace: str,
    key: str,
    builder: Callable[[], Awaitable[T]],
    ttl: int | None = None,
    model: type[BaseModel] | None = None,
) -> T:
    """Return a cached value or compute and store it if absent."""

    settings = get_settings()
    if not settings.cache_enabled:
        cache_metrics.record_skipped()
        return await builder()

    client = await get_cache_client()
    if client is None:
        cache_metrics.record_skipped()
        return await builder()

    if model is not None and not issubclass(model, BaseModel):  # pragma: no cover - defensive code
        raise TypeError("model must be a BaseModel subclass")

    cache_key = f"{namespace}:{key}"

    try:
        cached_payload = await client.get(cache_key)
    except Exception:  # pragma: no cover - network failure scenarios
        logger.warning("Failed to read cache key %s; bypassing cache.", cache_key, exc_info=True)
        cached_payload = None

    if cached_payload is not None:
        cache_metrics.record_hit()
        logger.info("Cache hit for %s", cache_key)
        data = json.loads(cached_payload)
        if model is not None:
            return cast(T, model.model_validate(data))
        return cast(T, data)

    cache_metrics.record_miss()
    logger.info("Cache miss for %s", cache_key)

    result = await builder()
    payload = jsonable_encoder(result)

    serialized = json.dumps(payload)
    expiry_source = ttl if ttl is not None else settings.cache_default_ttl_seconds
    expires: int | None
    try:
        expires = int(expiry_source)
    except (TypeError, ValueError):  # pragma: no cover - defensive guard
        expires = settings.cache_default_ttl_seconds
    if expires <= 0:
        expires = None

    try:
        await client.set(cache_key, serialized, ex=expires)
    except Exception:  # pragma: no cover - network failure scenarios
        logger.warning("Failed to store cache key %s", cache_key, exc_info=True)
    else:
        cache_metrics.record_store()
        logger.info("Stored cache entry for %s", cache_key)

    return result


async def invalidate_namespace(namespace: str, match: str = "*") -> None:
    """Remove cached entries under the provided namespace."""

    settings = get_settings()
    if not settings.cache_enabled:
        return

    client = await get_cache_client()
    if client is None:
        return

    pattern = f"{namespace}:{match}"
    try:
        keys = [key async for key in client.scan_iter(match=pattern)]
    except Exception:  # pragma: no cover - network failure scenarios
        logger.warning("Failed to scan cache keys for pattern %s", pattern, exc_info=True)
        return

    if not keys:
        return

    try:
        await client.delete(*keys)
    except Exception:  # pragma: no cover - network failure scenarios
        logger.warning("Failed to delete cache keys for pattern %s", pattern, exc_info=True)
    else:
        cache_metrics.record_invalidation(len(keys))
        logger.info("Invalidated %d cache entries for pattern %s", len(keys), pattern)


async def invalidate_task_cache() -> None:
    """Clear cached task listings and statistics."""

    await invalidate_namespace(TASK_LIST_CACHE_NAMESPACE)
    await invalidate_namespace(TASK_STATISTICS_CACHE_NAMESPACE)


__all__ = [
    "TASK_LIST_CACHE_NAMESPACE",
    "TASK_STATISTICS_CACHE_NAMESPACE",
    "cache_get_or_set",
    "cache_metrics",
    "close_cache_client",
    "get_cache_client",
    "invalidate_namespace",
    "invalidate_task_cache",
    "set_cache_client",
]
