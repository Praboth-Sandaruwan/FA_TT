"""Application entrypoint for the beginner FastAPI Task Tracker."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from projects import __version__

from .api.routers import api_router
from .core.config import Settings, get_settings
from .core.logging import configure_logging

__all__ = ["create_application", "app"]


def _build_fastapi_kwargs(settings: Settings) -> dict[str, Any]:
    """Prepare the keyword arguments used when instantiating :class:`FastAPI`."""
    return {
        "title": settings.project_name,
        "version": __version__,
        "debug": settings.debug,
        "docs_url": settings.docs_url,
        "redoc_url": settings.redoc_url,
        "openapi_url": settings.openapi_url,
    }


def create_application() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(**_build_fastapi_kwargs(settings))

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=settings.cors_allow_methods,
            allow_headers=settings.cors_allow_headers,
        )

    app.include_router(api_router)

    @app.get("/", tags=["Root"], summary="Root API information")
    async def read_root() -> dict[str, str]:
        return {
            "name": settings.project_name,
            "version": __version__,
        }

    return app


app = create_application()
