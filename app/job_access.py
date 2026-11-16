"""Helpers for enforcing ownership on job scoped API routes."""
from __future__ import annotations

from fastapi import HTTPException, Request

from app import jobs as jobstore


def is_local_auth_bypass(request: Request) -> bool:
    """True only when main's loopback-only development middleware opted in."""
    return getattr(request.state, "local_auth_bypass", False) is True


def admin_view_as(request: Request) -> str | None:
    """The user an administrator is acting for («مشاهدهٔ چت کاربر»): the X-Admin-View-As header, or the admin_view_as cookie (media and download links
    cannot send headers), honoured only for an administrator. Since 2026-11-16 the administrator can also act in that chat (send, edit, approve), as the
    owner asked: such requests run as the viewed user and are logged."""
    target = str(request.headers.get("x-admin-view-as") or request.cookies.get("admin_view_as") or "").strip()
    if not target or not target.isdigit() or "/admin/" in request.url.path:
        return None
    try:
        from app.routers.lm_admin import allowed
    except Exception:
        return None
    if not allowed(request):
        return None
    if request.method not in {"GET", "HEAD"}:
        import logging
        logging.getLogger(__name__).warning("administrator acts in user %s's chat: %s %s", target, request.method, request.url.path)
    return target


def verify_job_owner(request: Request, job) -> None:
    """Allow legacy unowned jobs, and reject jobs owned by another user."""
    if is_local_auth_bypass(request):
        return
    if admin_view_as(request) is not None:
        return
    owner_id = getattr(job, "user_id", None)
    if owner_id is None:
        return
    user = getattr(request.state, "user", None)
    if user is None or str(getattr(user, "id", "")) != str(owner_id):
        raise HTTPException(403, "You do not have access to this job")


def get_job_for_request(request: Request, job_id: str, *, missing: str = "job not found"):
    job = jobstore.get(job_id)
    if not job:
        raise HTTPException(404, missing)
    verify_job_owner(request, job)
    return job


def require_job_access(request: Request, job_id: str) -> None:
    """FastAPI dependency for routers whose every route is job scoped."""
    get_job_for_request(request, job_id)
