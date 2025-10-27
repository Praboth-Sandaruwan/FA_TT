"""User-centric API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ...deps import AdminUserDependency, CurrentUserDependency
from ...schemas import UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic, summary="Return the authenticated user")
async def read_current_user(current_user: CurrentUserDependency) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.get(
    "/admin",
    response_model=UserPublic,
    summary="Endpoint restricted to admin users",
)
async def read_admin_user(admin_user: AdminUserDependency) -> UserPublic:
    return UserPublic.model_validate(admin_user)
