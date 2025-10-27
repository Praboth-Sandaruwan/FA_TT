"""Configuration helpers for the advanced realtime FastAPI application."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Callable, Literal

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

    telemetry_enabled: bool = True
    telemetry_service_name: str = "advanced-realtime"
    otel_exporter_otlp_endpoint: str | None = None
    otel_exporter_otlp_headers: dict[str, str] = Field(default_factory=dict)
    metrics_path: str = "/metrics"

    rate_limit_default: str = "120/minute"
    rate_limit_storage_uri: str = "memory://"
    rate_limit_headers_enabled: bool = True
    activity_stream_rate_limit: str | None = "30/minute"

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
    cors_allow_credentials: bool = False
    cors_allow_methods: list[str] = Field(
        default_factory=lambda: ["GET", "HEAD", "OPTIONS"]
    )
    cors_allow_headers: list[str] = Field(
        default_factory=lambda: [
            "Accept",
            "Accept-Language",
            "Authorization",
            "Content-Type",
            "Cache-Control",
            "Pragma",
            "X-Requested-With",
        ]
    )
    cors_expose_headers: list[str] = Field(
        default_factory=lambda: [
            "Retry-After",
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
        ]
    )
    cors_max_age: int = 600

    security_headers_enabled: bool = True
    content_security_policy: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self' https: http: ws: wss:; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "object-src 'none'"
    )
    strict_transport_security: str = "max-age=63072000; includeSubDomains; preload"
    referrer_policy: str = "no-referrer"
    permissions_policy: str = "camera=(), microphone=(), geolocation=()"
    cross_origin_opener_policy: str = "same-origin"
    cross_origin_resource_policy: str = "same-origin"
    cross_origin_embedder_policy: str | None = None
    x_content_type_options: str = "nosniff"
    x_frame_options: str = "DENY"
    remove_server_header: bool = True

    @staticmethod
    def _coerce_list(
        value: str | list[str] | tuple[str, ...],
        *,
        normalise: Callable[[str], str] | None = None,
    ) -> list[str]:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, (list, tuple)):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            return []
        if normalise:
            items = [normalise(item) for item in items]
        return items

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_allowed_origins(cls, value: str | list[str]) -> list[str]:
        origins = cls._coerce_list(value)
        if not origins:
            raise ValueError(
                "ADVANCED_ALLOWED_ORIGINS must specify at least one explicit origin."
            )
        if any(origin == "*" or origin.endswith("://*") for origin in origins):
            raise ValueError(
                "Wildcard origins are not permitted for ADVANCED_ALLOWED_ORIGINS."
            )
        return origins

    @field_validator("cors_allow_methods", mode="before")
    @classmethod
    def _parse_cors_methods(cls, value: str | list[str]) -> list[str]:
        methods = cls._coerce_list(value, normalise=lambda entry: entry.upper())
        return methods or ["GET", "HEAD", "OPTIONS"]

    @field_validator("cors_allow_headers", "cors_expose_headers", mode="before")
    @classmethod
    def _parse_cors_headers(cls, value: str | list[str]) -> list[str]:
        return cls._coerce_list(value)

    @field_validator("cors_max_age")
    @classmethod
    def _validate_cors_max_age(cls, value: int) -> int:
        if value < 0:
            raise ValueError("ADVANCED_CORS_MAX_AGE must be zero or a positive integer.")
        return value

    @field_validator("metrics_path")
    @classmethod
    def _normalise_metrics_path(cls, value: str) -> str:
        candidate = value.strip() or "/metrics"
        if not candidate.startswith("/"):
            candidate = f"/{candidate}"
        return candidate

    @field_validator("otel_exporter_otlp_headers", mode="before")
    @classmethod
    def _parse_otlp_headers(cls, value: Any) -> dict[str, str]:
        if isinstance(value, dict):
            return {str(key): str(val) for key, val in value.items()}
        if isinstance(value, str):
            headers: dict[str, str] = {}
            for item in value.split(","):
                if not item.strip():
                    continue
                if "=" not in item:
                    continue
                key, header_value = item.split("=", 1)
                headers[key.strip()] = header_value.strip()
            return headers
        return {}

    @field_validator("activity_stream_rate_limit", mode="before")
    @classmethod
    def _normalise_activity_limit(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "content_security_policy",
        "strict_transport_security",
        "referrer_policy",
        "permissions_policy",
        "cross_origin_opener_policy",
        "cross_origin_resource_policy",
        "cross_origin_embedder_policy",
        "x_content_type_options",
        "x_frame_options",
        mode="before",
    )
    @classmethod
    def _strip_security_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(value).strip()


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()  # type: ignore[arg-type]


SettingsDependency = Annotated[Settings, Depends(get_settings)]
