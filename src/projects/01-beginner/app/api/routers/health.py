"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from ...schemas.system import HealthCheckResponse

router = APIRouter(tags=["system"])


@router.get(
    "/healthz",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check",
)
async def read_health() -> HealthCheckResponse:
    """Return a simple heartbeat payload for health checks."""
    return HealthCheckResponse(status="ok")
