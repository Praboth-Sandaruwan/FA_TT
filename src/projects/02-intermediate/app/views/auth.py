from __future__ import annotations

from fastapi import APIRouter, Request, status
from starlette.datastructures import FormData
from starlette.responses import RedirectResponse

from ..core.session import add_flash_message, login_user, logout_user, validate_csrf_token
from ..core.templates import template_response
from ..deps import (
    AuthenticatedSessionUserDependency,
    DatabaseSessionDependency,
    SessionUserDependency,
    SettingsDependency,
)
from ..errors import ApplicationError
from ..services import AuthService

router = APIRouter(tags=["auth"])


def _clean_email(raw: object) -> str:
    return str(raw or "").strip().lower()


def _clean_text(raw: object) -> str:
    return str(raw or "").strip()


def _form_payload(form: FormData, *, include_password: bool = False) -> dict[str, str]:
    payload = {
        "email": _clean_email(form.get("email")),
        "full_name": _clean_text(form.get("full_name")),
    }
    if include_password:
        payload["password"] = _clean_text(form.get("password"))
    return payload


def _csrf_invalid_response(request: Request, context: dict[str, object], *, template: str) -> object:
    add_flash_message(request.session, "error", "The form has expired. Please try again.")
    return template_response(request, template, context, status_code=status.HTTP_400_BAD_REQUEST)


@router.get("/login", name="auth:login")
async def login_form(request: Request, current_user: SessionUserDependency) -> object:
    """Render the login form."""

    if current_user is not None and current_user.id is not None:
        return RedirectResponse(request.url_for("notes:list_notes"), status_code=303)
    return template_response(
        request,
        "auth/login.html",
        {
            "title": "Sign in",
            "form": {"email": ""},
            "errors": {},
        },
    )


@router.post("/login", name="auth:login:submit")
async def login_submit(
    request: Request,
    session: DatabaseSessionDependency,
    settings: SettingsDependency,
) -> object:
    """Handle login form submissions."""

    form = await request.form()
    if not validate_csrf_token(request.session, form.get("csrf_token")):
        context = {"form": _form_payload(form, include_password=False), "errors": {}}
        return _csrf_invalid_response(request, context, template="auth/login.html")

    email = _clean_email(form.get("email"))
    password = _clean_text(form.get("password"))

    errors: dict[str, str] = {}
    if not email:
        errors["email"] = "Email is required."
    if not password:
        errors["password"] = "Password is required."

    auth_service = AuthService(session, settings)
    user = None
    if not errors:
        try:
            user = await auth_service.authenticate_user(email, password)
        except ApplicationError as exc:
            errors["email"] = exc.message
        else:
            if user is None:
                errors["email"] = "Invalid email or password."

    if errors or user is None:
        return template_response(
            request,
            "auth/login.html",
            {
                "title": "Sign in",
                "form": {"email": email},
                "errors": errors,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if user.id is None:  # pragma: no cover - defensive guard
        errors["email"] = "Unable to authenticate with the provided credentials."
        return template_response(
            request,
            "auth/login.html",
            {
                "title": "Sign in",
                "form": {"email": email},
                "errors": errors,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    login_user(request.session, user.id)
    add_flash_message(request.session, "success", "Welcome back!")
    return RedirectResponse(request.url_for("notes:list_notes"), status_code=303)


@router.get("/register", name="auth:register")
async def register_form(request: Request, current_user: SessionUserDependency) -> object:
    """Render the registration form."""

    if current_user is not None and current_user.id is not None:
        return RedirectResponse(request.url_for("notes:list_notes"), status_code=303)
    return template_response(
        request,
        "auth/register.html",
        {
            "title": "Create an account",
            "form": {"email": "", "full_name": ""},
            "errors": {},
        },
    )


@router.post("/register", name="auth:register:submit")
async def register_submit(
    request: Request,
    session: DatabaseSessionDependency,
    settings: SettingsDependency,
) -> object:
    """Handle registration form submissions."""

    form = await request.form()
    if not validate_csrf_token(request.session, form.get("csrf_token")):
        context = {"form": _form_payload(form), "errors": {}}
        return _csrf_invalid_response(request, context, template="auth/register.html")

    email = _clean_email(form.get("email"))
    password = _clean_text(form.get("password"))
    full_name = _clean_text(form.get("full_name"))

    errors: dict[str, str] = {}
    if not email:
        errors["email"] = "Email is required."
    if not password or len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."

    auth_service = AuthService(session, settings)
    user = None
    if not errors:
        try:
            user = await auth_service.register_user(email=email, password=password, full_name=full_name or None)
        except ApplicationError as exc:
            errors["email"] = exc.message

    if errors or user is None:
        return template_response(
            request,
            "auth/register.html",
            {
                "title": "Create an account",
                "form": {"email": email, "full_name": full_name},
                "errors": errors,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if user.id is None:  # pragma: no cover - defensive guard
        errors["email"] = "Registration failed. Please try again."
        return template_response(
            request,
            "auth/register.html",
            {
                "title": "Create an account",
                "form": {"email": email, "full_name": full_name},
                "errors": errors,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    login_user(request.session, user.id)
    add_flash_message(request.session, "success", "Your account has been created.")
    return RedirectResponse(request.url_for("notes:list_notes"), status_code=303)


@router.post("/logout", name="auth:logout")
async def logout(
    request: Request,
    _: AuthenticatedSessionUserDependency,
) -> RedirectResponse | object:
    """Sign the user out and clear their browser session."""

    form = await request.form()
    if not validate_csrf_token(request.session, form.get("csrf_token")):
        add_flash_message(request.session, "error", "Invalid sign out request.")
        return RedirectResponse(request.url_for("notes:list_notes"), status_code=303)

    logout_user(request.session)
    add_flash_message(request.session, "info", "You have been signed out.")
    return RedirectResponse(request.url_for("pages:home"), status_code=303)
