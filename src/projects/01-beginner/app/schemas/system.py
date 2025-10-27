"""Common system-level response models."""

from __future__ import annotations

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
