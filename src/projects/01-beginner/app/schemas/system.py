"""Common system-level response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RootResponse(BaseModel):
    """Metadata payload returned by the root endpoint."""

    name: str = Field(description="Human-friendly service name")
    environment: str = Field(description="Deployment environment identifier")
    version: str = Field(description="Semantic version of the service")
    api_prefix: str = Field(description="Base path for API routes")


class HealthCheckResponse(BaseModel):
    """Payload returned by the health check endpoint."""

    status: str = Field(default="ok", description="Service health indicator")


class ErrorResponse(BaseModel):
    """Standardised error envelope returned by exception handlers."""

    code: str = Field(description="Machine-readable error identifier")
    message: str = Field(description="Human-readable error message")
    details: Any | None = Field(
        default=None,
        description="Optional structured metadata describing the error context.",
    )
