from __future__ import annotations

import asyncio
from collections.abc import Mapping

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

from ..core.config import get_settings
from .models import ActivityEvent

_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None
_initialized = False
_lock = asyncio.Lock()


def set_activity_client(client: AsyncIOMotorClient | None) -> None:
    """Inject a custom motor client instance (primarily for tests)."""

    global _client, _database, _initialized
    _client = client
    _database = None
    _initialized = False


def _normalise_ttl(raw: object) -> int:
    try:
        ttl = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 60 * 60 * 24
    return max(ttl, 1)


async def _ensure_indexes(ttl_seconds: int) -> None:
    collection = get_activity_collection()
    existing = await collection.index_information()

    ttl_name = "activity_created_at_ttl"
    current_ttl = None
    ttl_index = existing.get(ttl_name)
    if isinstance(ttl_index, Mapping):
        current_ttl = ttl_index.get("expireAfterSeconds")

    if current_ttl is not None and int(current_ttl) != ttl_seconds:
        try:
            await collection.drop_index(ttl_name)
        except OperationFailure:
            pass

    await collection.create_index([("created_at", DESCENDING)], name="activity_created_at")
    await collection.create_index(
        [("created_at", ASCENDING)],
        expireAfterSeconds=ttl_seconds,
        name=ttl_name,
    )
    await collection.create_index([("action", ASCENDING)], name="activity_action")


async def init_activity_store(*, client: AsyncIOMotorClient | None = None, force: bool = False) -> None:
    """Initialise the beanie document store used for activity logging."""

    global _client, _database, _initialized

    async with _lock:
        if client is not None:
            set_activity_client(client)

        if _initialized and not force:
            return

        settings = get_settings()
        if _client is None:
            _client = AsyncIOMotorClient(settings.mongo_url, tz_aware=True, uuidRepresentation="standard")
        _database = _client[settings.mongo_database]

        await init_beanie(
            database=_database,
            document_models=[ActivityEvent],
            allow_index_dropping=True,
        )

        ttl_seconds = _normalise_ttl(settings.activity_ttl_seconds)
        await _ensure_indexes(ttl_seconds)
        _initialized = True


async def close_activity_store() -> None:
    """Dispose the MongoDB client used for activity logging."""

    global _client, _database, _initialized
    client = _client
    if client is not None:
        client.close()
    _client = None
    _database = None
    _initialized = False


def get_activity_collection() -> AsyncIOMotorCollection:
    """Return the MongoDB collection backing the activity log."""

    return ActivityEvent.get_motor_collection()
