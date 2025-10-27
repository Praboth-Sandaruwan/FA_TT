"""Router registrations for the beginner application."""

from __future__ import annotations

from fastapi import APIRouter

from .health import router as health_router

api_router = APIRouter()

__all__ = ["api_router", "health_router"]
