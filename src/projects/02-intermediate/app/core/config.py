from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from ... import __version__ as package_version
except ImportError:  # pragma: no cover - fallback during early bootstrapping
    package_version = "0.1.0"


def _resolve_project_dirs() -> tuple[Path, Path]:
    """Locate the project root and repository root directories."""

    current = Path(__file__).resolve()
    project_dir: Path | None = None
    for parent in current.parents:
        if parent.name == "02-intermediate":
            project_dir = parent
            break
    if project_dir is None:
        raise RuntimeError("Unable to determine project directory for intermediate app.")
    repository_root = project_dir.parent.parent.parent
    return project_dir, repository_root


PROJECT_DIR, REPOSITORY_ROOT = _resolve_project_dirs()

EnvironmentName = Literal["development", "test", "ci"]

_ENVIRONMENT_ALIASES: dict[str, EnvironmentName] = {
    "development": "development",
    "dev": "development",
    "test": "test",
    "testing": "test",
    "ci": "ci",
}

_ENVIRONMENT_PROFILES: dict[EnvironmentName, dict[str, Any]] = {
    "development": {
        "log_level": "DEBUG",
        "reload": True,
        "cache_enabled": True,
        "db_echo": False,
    },
    "test": {
        "log_level": "WARNING",
        "reload": False,
        "cache_enabled": False,
        "db_echo": False,
    },
    "ci": {
        "log_level": "INFO",
        "reload": False,
        "cache_enabled": True,
        "db_echo": False,
    },
}


class Settings(BaseSettings):
    """Runtime configuration for the intermediate FastAPI application."""

    model_config = SettingsConfigDict(
        env_prefix="INTERMEDIATE_",
        env_file=(PROJECT_DIR / ".env", REPOSITORY_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_name: str = "Intermediate FastAPI"
    environment: EnvironmentName = Field(default="development", alias="ENVIRONMENT")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    version: str = Field(default=package_version, alias="VERSION")
    database_url: str = Field(
        default="postgresql+asyncpg://app:app@localhost:5432/app_db",
        alias="DATABASE_URL",
    )
    mongo_url: str = Field(default="mongodb://localhost:27017", alias="MONGO_URL")
    mongo_database: str = Field(default="intermediate_app", alias="MONGO_DATABASE")
    activity_ttl_seconds: int = Field(default=60 * 60 * 24, alias="ACTIVITY_TTL_SECONDS")
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="ALLOWED_ORIGINS",
    )
    cors_allow_credentials: bool = Field(default=True, alias="ALLOW_CREDENTIALS")
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"], alias="ALLOW_METHODS")
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"], alias="ALLOW_HEADERS")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8003, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    reload: bool = Field(default=True, alias="RELOAD")

    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_refresh_secret_key: str = Field(
        default="change-me-refresh",
        alias="JWT_REFRESH_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_minutes: int = Field(
        default=60 * 24,
        alias="REFRESH_TOKEN_EXPIRE_MINUTES",
    )
    db_echo: bool = Field(default=False, alias="DB_ECHO")
    cache_enabled: bool = Field(default=True, alias="CACHE_ENABLED")
    cache_default_ttl_seconds: int = Field(default=60, alias="CACHE_TTL_SECONDS")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    job_queue_name: str = Field(default="intermediate:tasks", alias="JOB_QUEUE_NAME")
    job_worker_name: str = Field(default="intermediate-worker", alias="JOB_WORKER_NAME")
    job_default_timeout: int = Field(default=300, alias="JOB_TIMEOUT_SECONDS")
    job_result_ttl_seconds: int = Field(default=600, alias="JOB_RESULT_TTL_SECONDS")
    job_max_retries: int = Field(default=3, alias="JOB_MAX_RETRIES")
    job_retry_backoff_seconds: list[int] = Field(
        default_factory=lambda: [5, 15, 30],
        alias="JOB_RETRY_BACKOFF_SECONDS",
    )

    session_secret_key: str = Field(default="change-me-session", alias="SESSION_SECRET_KEY")
    session_cookie_name: str = Field(default="intermediate_session", alias="SESSION_COOKIE_NAME")
    session_max_age: int | None = Field(default=60 * 60 * 24 * 14, alias="SESSION_MAX_AGE")
    session_https_only: bool = Field(default=True, alias="SESSION_HTTPS_ONLY")
    session_same_site: str = Field(default="lax", alias="SESSION_SAME_SITE")

    @field_validator("environment", mode="before")
    @classmethod
    def _normalise_environment(cls, value: object) -> EnvironmentName:
        if isinstance(value, str):
            normalized = value.strip().lower()
        else:
            normalized = ""
        if not normalized:
            normalized = "development"
        mapped = _ENVIRONMENT_ALIASES.get(normalized)
        if mapped is not None:
            return mapped
        return "development"

    @field_validator("cache_default_ttl_seconds", mode="before")
    @classmethod
    def _ensure_non_negative_ttl(cls, value: object) -> int:
        try:
            ttl = int(value)
        except (TypeError, ValueError):
            return 60
        return max(ttl, 0)

    @field_validator("activity_ttl_seconds", mode="before")
    @classmethod
    def _normalise_activity_ttl(cls, value: object) -> int:
        try:
            ttl = int(value)
        except (TypeError, ValueError):
            return 60 * 60 * 24
        return max(ttl, 1)

    @field_validator(
        "cors_allow_origins",
        "cors_allow_methods",
        "cors_allow_headers",
        mode="before",
    )
    @classmethod
    def _coerce_comma_separated(cls, value: object) -> list[str]:
        """Allow comma separated strings for CORS configuration."""

        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, Sequence):
            return [str(item) for item in value if str(item).strip()]
        return []

    @field_validator("job_default_timeout", "job_result_ttl_seconds", "job_max_retries", mode="before")
    @classmethod
    def _ensure_non_negative_job_settings(cls, value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return max(parsed, 0)

    @field_validator("job_retry_backoff_seconds", mode="before")
    @classmethod
    def _parse_retry_backoff(cls, value: object) -> list[int]:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, Sequence):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            items = []
        backoff: list[int] = []
        for item in items:
            try:
                backoff.append(max(int(item), 0))
            except (TypeError, ValueError):
                continue
        if not backoff:
            return [5, 15, 30]
        return backoff

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> str:
        if not isinstance(value, str):
            return "INFO"
        return value.upper()

    @model_validator(mode="after")
    def _apply_environment_profile(self) -> "Settings":
        profile = _ENVIRONMENT_PROFILES[self.environment]
        fields_set = set(getattr(self, "model_fields_set", set()))
        for field_name, value in profile.items():
            if field_name not in fields_set:
                setattr(self, field_name, value)
        return self

    @field_validator("session_same_site", mode="before")
    @classmethod
    def _normalize_same_site(cls, value: object) -> str:
        if not isinstance(value, str):
            return "lax"
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            return "lax"
        return normalized


@lru_cache()
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""

    return Settings()
