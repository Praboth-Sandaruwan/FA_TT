"""Router registrations for the intermediate application."""

from __future__ import annotations

from fastapi import APIRouter

from .auth import router as auth_router
from .health import router as health_router
from .tasks import router as tasks_router
from .users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(tasks_router)
api_router.include_router(users_router)

__all__ = ["api_router", "auth_router", "health_router", "tasks_router", "users_router"]
