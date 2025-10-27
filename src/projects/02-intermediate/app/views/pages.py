from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse

from ..core.templates import template_response
from ..deps import SessionUserDependency

router = APIRouter(tags=["web"])


@router.get("/", name="pages:home")
async def home(request: Request, current_user: SessionUserDependency) -> RedirectResponse | object:
    """Render the landing page or redirect authenticated users to their notes."""

    if current_user is not None and current_user.id is not None:
        return RedirectResponse(request.url_for("notes:list_notes"), status_code=303)
    return template_response(
        request,
        "pages/home.html",
        {
            "title": "Welcome",
        },
    )
