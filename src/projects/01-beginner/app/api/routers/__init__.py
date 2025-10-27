"""API routers for the beginner FastAPI Task Tracker."""

from __future__ import annotations

from fastapi import APIRouter

from .health import router as health_router

__all__ = ["api_router"]

api_router = APIRouter()
api_router.include_router(health_router)
