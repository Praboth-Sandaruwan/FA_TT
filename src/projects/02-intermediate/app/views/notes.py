from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from starlette.responses import RedirectResponse

from ..core.session import add_flash_message, validate_csrf_token
from ..core.templates import is_htmx_request, partial_response, template_response
from ..deps import AuthenticatedSessionUserDependency, DatabaseSessionDependency
from ..models import TaskStatus
from ..services import TaskService

router = APIRouter(tags=["notes"])


def _require_user_id(user) -> int:
    if user.id is None:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authenticated user missing identifier.",
        )
    return int(user.id)


def _clean_text(raw: object) -> str:
    return str(raw or "").strip()


def _redirect_to_notes(request: Request) -> RedirectResponse:
    return RedirectResponse(request.url_for("notes:list_notes"), status_code=303)


@router.get("/", name="notes:list_notes")
async def list_notes(
    request: Request,
    current_user: AuthenticatedSessionUserDependency,
    session: DatabaseSessionDependency,
) -> object:
    """Render the authenticated user's collection of notes/tasks."""

    service = TaskService(session)
    user_id = _require_user_id(current_user)
    tasks = await service.list_tasks_for_owner(user_id)
    return template_response(
        request,
        "notes/index.html",
        {
            "title": "My entries",
            "tasks": tasks,
            "form": {"title": "", "description": ""},
            "errors": {},
            "current_user": current_user,
        },
    )


@router.post("/", name="notes:create_note")
async def create_note(
    request: Request,
    current_user: AuthenticatedSessionUserDependency,
    session: DatabaseSessionDependency,
) -> object:
    """Persist a new note for the authenticated user."""

    form = await request.form()
    if not validate_csrf_token(request.session, form.get("csrf_token")):
        add_flash_message(request.session, "error", "The form has expired. Please try again.")
        return _redirect_to_notes(request)

    title = _clean_text(form.get("title"))
    description = _clean_text(form.get("description"))

    errors: dict[str, str] = {}
    if not title:
        errors["title"] = "Title is required."

    service = TaskService(session)
    user_id = _require_user_id(current_user)
    if errors:
        tasks = await service.list_tasks_for_owner(user_id)
        return template_response(
            request,
            "notes/index.html",
            {
                "title": "My entries",
                "tasks": tasks,
                "form": {"title": title, "description": description},
                "errors": errors,
                "current_user": current_user,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    await service.create_task(
        owner_id=user_id,
        title=title,
        description=description or None,
        status=TaskStatus.PENDING,
    )
    add_flash_message(request.session, "success", "Entry created successfully.")
    return _redirect_to_notes(request)


@router.post("/{task_id}/toggle", name="notes:toggle_status")
async def toggle_status(
    task_id: int,
    request: Request,
    current_user: AuthenticatedSessionUserDependency,
    session: DatabaseSessionDependency,
) -> object:
    """Toggle a note between pending and completed states."""

    form = await request.form()
    if not validate_csrf_token(request.session, form.get("csrf_token")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSRF token.")

    service = TaskService(session)
    user_id = _require_user_id(current_user)
    task = await service.get_task_for_owner(task_id, user_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found.")

    new_status = TaskStatus.COMPLETED if task.status != TaskStatus.COMPLETED else TaskStatus.PENDING
    task = await service.update_task_for_owner(
        task_id,
        user_id,
        status=new_status,
    )

    context = {
        "task": task,
        "current_user": current_user,
    }
    if is_htmx_request(request):
        return partial_response(request, "notes/_note_item.html", context)

    add_flash_message(request.session, "success", "Entry updated.")
    return _redirect_to_notes(request)
