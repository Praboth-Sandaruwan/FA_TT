from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from ..core.templates import partial_response, template_response
from ..deps import ActivityServiceDependency, AuthenticatedSessionUserDependency

router = APIRouter(tags=["activity"], prefix="/activity")

LimitQuery = Annotated[
    int,
    Query(
        default=25,
        ge=1,
        le=100,
        description="Maximum number of activity entries to include in the feed.",
    ),
]


@router.get("/", name="activity:index")
async def activity_index(
    request: Request,
    current_user: AuthenticatedSessionUserDependency,
    activity_service: ActivityServiceDependency,
    limit: LimitQuery = 25,
) -> object:
    """Render the activity feed landing page."""

    events = await activity_service.list_recent(limit=limit)
    return template_response(
        request,
        "activity/index.html",
        {
            "title": "Activity",
            "events": events,
            "limit": limit,
        },
    )


@router.get("/feed", name="activity:feed")
async def activity_feed(
    request: Request,
    current_user: AuthenticatedSessionUserDependency,
    activity_service: ActivityServiceDependency,
    limit: LimitQuery = 25,
) -> object:
    """Return a partial rendering of recent activity for HTMX polling."""

    events = await activity_service.list_recent(limit=limit)
    return partial_response(
        request,
        "activity/_event_list.html",
        {
            "events": events,
            "limit": limit,
        },
    )
