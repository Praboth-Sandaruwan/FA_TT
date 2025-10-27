"""Application settings loaded via Pydantic."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings", "PROJECT_ROOT"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT_ENV_FILE = PROJECT_ROOT.parents[2] / ".env"


def _coerce_list(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    else:
        items = [str(item).strip() for item in value]
    return [item for item in items if item]


class Settings(BaseSettings):
    """Runtime configuration for the Task Tracker application."""

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", ROOT_ENV_FILE),
        env_file_encoding="utf-8",
        env_prefix="TASK_TRACKER_",
        extra="ignore",
    )

    project_name: str = "Task Tracker API"
    debug: bool = False
    log_level: str = "INFO"

    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str = "/openapi.json"

    cors_origins: list[str] = Field(default_factory=list)
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("cors_origins", "cors_allow_methods", "cors_allow_headers", mode="before")
    @classmethod
    def _parse_list_values(cls, value: str | Iterable[str] | None) -> list[str]:
        return _coerce_list(value)


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of :class:`Settings`."""
    return Settings()
