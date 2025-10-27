"""Entry point for the beginner FastAPI application."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routers import api_router, health_router
from .core.config import Settings, get_settings
from .core.logging import configure_logging
from .deps import SettingsDependency
from .errors import register_exception_handlers
from .schemas.system import RootResponse


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings)

    raw_prefix = settings.api_prefix.strip()
    router_prefix = raw_prefix
    if router_prefix and not router_prefix.startswith("/"):
        router_prefix = f"/{router_prefix}"
    router_prefix = router_prefix.rstrip("/")
    if router_prefix == "/":
        router_prefix = ""
    openapi_url = "/openapi.json" if not router_prefix else f"{router_prefix}/openapi.json"

    application = FastAPI(
        title=settings.project_name,
        version=settings.version,
        summary="Starter FastAPI service scaffold.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=openapi_url,
    )

    application.state.settings = settings

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    if router_prefix:
        application.include_router(api_router, prefix=router_prefix)
    else:
        application.include_router(api_router)

    application.include_router(health_router)

    register_exception_handlers(application)

    return application


app = create_app()


@app.get("/", response_model=RootResponse, summary="Service metadata")
async def read_root(settings: SettingsDependency) -> RootResponse:
    """Expose minimal service metadata at the root endpoint."""
    return RootResponse(
        name=settings.project_name,
        environment=settings.environment,
        version=settings.version,
        api_prefix=settings.api_prefix,
    )


def run() -> None:
    """Convenience entry point for ``poetry run beginner-app``."""
    settings: Settings = get_settings()
    uvicorn.run(
        "projects.01-beginner.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.reload,
        log_config=None,
    )
