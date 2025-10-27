"""Entry point for the intermediate FastAPI application."""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .activity import close_activity_store, init_activity_store
from .api.routers import api_router, health_router
from .core.config import Settings, get_settings
from .core.logging import configure_logging
from .core.middleware import CorrelationIdMiddleware
from .deps import SettingsDependency
from .errors import register_exception_handlers
from .schemas.system import RootResponse
from .views import router as views_router

STATIC_DIR = Path(__file__).resolve().parent / "static"


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
        summary="Intermediate FastAPI service with API and SSR features.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=openapi_url,
    )

    application.state.settings = settings

    application.add_middleware(CorrelationIdMiddleware)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        session_cookie=settings.session_cookie_name,
        max_age=settings.session_max_age,
        https_only=settings.session_https_only,
        same_site=settings.session_same_site,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    if STATIC_DIR.exists():
        application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    application.include_router(views_router)

    if router_prefix:
        application.include_router(api_router, prefix=router_prefix)
    else:
        application.include_router(api_router)

    application.include_router(health_router)

    register_exception_handlers(application)

    @application.on_event("startup")
    async def _initialise_activity_store() -> None:
        await init_activity_store()

    @application.on_event("shutdown")
    async def _dispose_activity_store() -> None:
        await close_activity_store()

    return application


app = create_app()


@app.get("/api/metadata", response_model=RootResponse, summary="Service metadata")
async def read_api_metadata(settings: SettingsDependency) -> RootResponse:
    """Expose minimal service metadata for API clients."""

    return RootResponse(
        name=settings.project_name,
        environment=settings.environment,
        version=settings.version,
        api_prefix=settings.api_prefix,
    )


def run() -> None:
    """Convenience entry point for ``poetry run intermediate-app``."""

    settings: Settings = get_settings()
    uvicorn.run(
        "projects.02-intermediate.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.reload,
        log_config=None,
    )
