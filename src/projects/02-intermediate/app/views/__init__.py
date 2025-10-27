from __future__ import annotations

from fastapi import APIRouter

from . import activity, auth, notes, pages

router = APIRouter()
router.include_router(pages.router)
router.include_router(auth.router, prefix="/auth")
router.include_router(notes.router, prefix="/notes")
router.include_router(activity.router)

__all__ = ["router"]
