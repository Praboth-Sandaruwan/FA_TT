from __future__ import annotations

import asyncio
import contextlib
import json
import os
from typing import Any

import httpx
import websockets

DEFAULT_MESSAGE: dict[str, Any] = {
    "action": "card.added",
    "user": "pipeline.demo",
    "payload": {"title": "Pipeline demo", "column": "in_progress"},
}


async def _listen_for_event(client: httpx.AsyncClient, sse_url: str, token: str) -> dict[str, Any]:
    params = {"token": token}
    async with client.stream("GET", sse_url, params=params, timeout=None) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or line.startswith(":"):
                continue
            if line.startswith("data: "):
                payload = json.loads(line.removeprefix("data: "))
                return payload
    raise RuntimeError("SSE stream ended without receiving an event")


async def main() -> None:
    token = os.environ.get("ADVANCED_REALTIME_TOKEN", "change-me-realtime")
    board_id = os.environ.get("ADVANCED_BOARD_ID", "demo")
    app_host = os.environ.get("ADVANCED_APP_HOST", "localhost")
    app_port = os.environ.get("ADVANCED_APP_PORT", "8004")

    base_http = f"http://{app_host}:{app_port}"
    base_ws = f"ws://{app_host}:{app_port}"

    sse_url = f"{base_http}/sse/activity"
    ws_url = f"{base_ws}/ws/boards/{board_id}?token={token}"

    async with httpx.AsyncClient(http2=False) as client:
        listener = asyncio.create_task(_listen_for_event(client, sse_url, token))
        try:
            async with websockets.connect(ws_url, extra_headers={"Authorization": f"Bearer {token}"}) as websocket:
                await websocket.send(json.dumps(DEFAULT_MESSAGE))
                event = await listener
        finally:
            if not listener.done():
                listener.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await listener

    print("Received event from SSE:")
    print(json.dumps(event, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
