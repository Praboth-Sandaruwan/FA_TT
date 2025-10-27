"""Application settings powered by ``pydantic-settings``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Sequence

from pydantic import Field, field_validator
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
        if parent.name == "01-beginner":
            project_dir = parent
            break
    if project_dir is None:
        raise RuntimeError("Unable to determine project directory for beginner app.")
    repository_root = project_dir.parent.parent.parent
    return project_dir, repository_root


PROJECT_DIR, REPOSITORY_ROOT = _resolve_project_dirs()


class Settings(BaseSettings):
    """Runtime configuration for the beginner FastAPI service."""

    model_config = SettingsConfigDict(
        env_prefix="BEGINNER_",
        env_file=(PROJECT_DIR / ".env", REPOSITORY_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_name: str = "Beginner FastAPI"
    environment: str = Field(default="development", alias="ENVIRONMENT")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    version: str = Field(default=package_version, alias="VERSION")
    database_url: str = Field(
        default="postgresql+asyncpg://app:app@localhost:5432/app_db",
        alias="DATABASE_URL",
    )
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="ALLOWED_ORIGINS",
    )
    cors_allow_credentials: bool = Field(default=True, alias="ALLOW_CREDENTIALS")
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"], alias="ALLOW_METHODS")
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"], alias="ALLOW_HEADERS")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8002, alias="APP_PORT")
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

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> str:
        if not isinstance(value, str):
            return "INFO"
        return value.upper()


@lru_cache()
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
