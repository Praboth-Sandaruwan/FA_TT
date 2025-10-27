"""Entry point for the advanced realtime FastAPI application."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated, AsyncIterator

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from .auth import RealtimeAuthenticationError, authenticate_websocket, require_http_token
from .config import Settings, SettingsDependency, get_settings
from .messaging import BoardEventEnvelope, EventPipeline
from .realtime import (
    BoardMessage,
    ConnectionLimitExceeded,
    ActivityEvent,
    broker,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application for realtime collaboration."""

    settings = get_settings()
    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        summary="Advanced realtime board with WebSockets and SSE.",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.state.settings = settings

    pipeline = EventPipeline(settings, broker.broadcast)
    app.state.event_pipeline = pipeline

    @app.on_event("startup")
    async def start_event_pipeline() -> None:
        await pipeline.start()

    @app.on_event("shutdown")
    async def stop_event_pipeline() -> None:
        await pipeline.stop()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="advanced-static")

    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    async def validate_http_token(
        request: Request, settings: SettingsDependency
    ) -> str:
        return require_http_token(request, settings)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, settings: SettingsDependency) -> HTMLResponse:
        """Serve the realtime playground surface."""

        token_hint = (
            settings.realtime_token
            if settings.realtime_token.startswith("change-me")
            else "Configured via ADVANCED_REALTIME_TOKEN"
        )
        context = {
            "request": request,
            "project_name": settings.project_name,
            "token_hint": token_hint,
            "channels": {
                "board": settings.board_channel,
                "activity": settings.activity_channel,
            },
            "reconnect": {
                "initial_delay": settings.reconnect_initial_delay_seconds,
                "max_delay": settings.reconnect_max_delay_seconds,
            },
        }
        return templates.TemplateResponse("index.html", context)

    @app.get("/healthz", summary="Application liveness probe")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/sse/activity")
    async def activity_stream(
        request: Request,
        _: Annotated[str, Depends(validate_http_token)],
        settings: SettingsDependency,
    ) -> StreamingResponse:
        """Stream board activity events via Server-Sent Events."""

        queue = await broker.register_activity_listener()

        async def event_source() -> AsyncIterator[str]:
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event: ActivityEvent = await asyncio.wait_for(
                            queue.get(), timeout=settings.sse_heartbeat_seconds
                        )
                    except asyncio.TimeoutError:
                        yield "event: heartbeat\ndata: {}\n\n"
                        continue
                    payload = json.dumps(event.model_dump())
                    yield f"id: {event.id}\nevent: {event.action}\ndata: {payload}\n\n"
            finally:
                await broker.unregister_activity_listener(queue)

        response = StreamingResponse(event_source(), media_type="text/event-stream")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Connection"] = "keep-alive"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    @app.websocket("/ws/boards/{board_id}")
    async def board_updates(websocket: WebSocket, board_id: str, settings: SettingsDependency) -> None:
        """Handle realtime board updates for websocket clients."""

        try:
            await authenticate_websocket(websocket, settings)
        except RealtimeAuthenticationError:
            return

        connected = False
        pipeline: EventPipeline = app.state.event_pipeline
        try:
            await broker.connect(board_id, websocket, settings)
            connected = True
        except ConnectionLimitExceeded:
            await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
            return

        try:
            while True:
                try:
                    raw = await websocket.receive_json()
                except json.JSONDecodeError:
                    await websocket.send_json(
                        {
                            "kind": "error",
                            "reason": "invalid_json",
                            "detail": "Messages must be valid JSON objects.",
                        }
                    )
                    continue

                try:
                    message = BoardMessage.model_validate(raw)
                except ValidationError as exc:
                    await websocket.send_json(
                        {
                            "kind": "error",
                            "reason": "validation_error",
                            "detail": exc.errors(),
                        }
                    )
                    continue

                envelope = BoardEventEnvelope.from_message(board_id, message)
                try:
                    await pipeline.publish(envelope)
                except Exception:  # pragma: no cover - network/transient failures
                    logger.exception(
                        "Failed to publish board event",
                        extra={"board_id": board_id, "action": message.action},
                    )
                    await websocket.send_json(
                        {
                            "kind": "error",
                            "reason": "event_bus_failure",
                            "detail": "Unable to process board event. Please retry.",
                        }
                    )
                    continue
        except WebSocketDisconnect:
            pass
        finally:
            if connected:
                await broker.disconnect(board_id, websocket)

    return app


app = create_app()


def run() -> None:
    """Convenience entry point for ``poetry run advanced-app``."""

    settings: Settings = get_settings()
    import uvicorn

    uvicorn.run(
        "projects.03-advanced.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.reload,
        log_config=None,
    )
