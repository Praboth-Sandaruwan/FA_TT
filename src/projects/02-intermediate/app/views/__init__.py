from __future__ import annotations

from fastapi import APIRouter

from . import auth, notes, pages

router = APIRouter()
router.include_router(pages.router)
router.include_router(auth.router, prefix="/auth")
router.include_router(notes.router, prefix="/notes")

__all__ = ["router"]
