"""Configuration helpers for the advanced realtime FastAPI application."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the advanced realtime layer."""

    model_config = SettingsConfigDict(env_prefix="ADVANCED_", extra="ignore")

    project_name: str = "Advanced Realtime Board"
    version: str = "0.1.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8004
    reload: bool = True

    realtime_token: str = "change-me-realtime"
    redis_url: str = "redis://localhost:6379/2"
    board_channel: str = "advanced:board"
    activity_channel: str = "advanced:activity"
    redis_idempotency_prefix: str = "advanced:idempotency"
    redis_idempotency_ttl_seconds: int = 300
    sse_heartbeat_seconds: int = 15
    websocket_max_connections: int = 128

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "advanced.board.events"
    rabbitmq_queue: str = "advanced.board.events"
    rabbitmq_retry_exchange: str = "advanced.board.events.retry"
    rabbitmq_retry_queue: str = "advanced.board.events.retry"
    rabbitmq_dlq_exchange: str = "advanced.board.events.dlq"
    rabbitmq_dlq_queue: str = "advanced.board.events.dlq"
    rabbitmq_routing_key: str = "boards.activity"
    rabbitmq_retry_routing_key: str = "boards.activity.retry"
    rabbitmq_dlq_routing_key: str = "boards.activity.dlq"
    rabbitmq_retry_delay_ms: int = 5000
    rabbitmq_max_retries: int = 5
    rabbitmq_prefetch_count: int = 16

    event_transport: Literal["rabbitmq", "memory"] = "rabbitmq"

    reconnect_initial_delay_seconds: float = 1.5
    reconnect_max_delay_seconds: float = 10.0

    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
        ]
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_allowed_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            origins = [item.strip() for item in value.split(",") if item.strip()]
            return origins or ["*"]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()  # type: ignore[arg-type]


SettingsDependency = Annotated[Settings, Depends(get_settings)]
