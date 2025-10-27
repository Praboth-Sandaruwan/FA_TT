"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

__all__ = ["router"]

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", status_code=status.HTTP_200_OK, summary="Service health check")
async def read_health() -> dict[str, str]:
    """Return a simple health response used for uptime checks."""
    return {"status": "ok"}
