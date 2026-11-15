"""Helpers for enforcing ownership on job scoped API routes."""
from __future__ import annotations

from fastapi import HTTPException, Request

from app import jobs as jobstore


def is_local_auth_bypass(request: Request) -> bool:
    """True only when main's loopback-only development middleware opted in."""
    return getattr(request.state, "local_auth_bypass", False) is True


def admin_view_as(request: Request) -> str | None:
    """The user an administrator is LOOKING at («مشاهدهٔ چت کاربر»): the X-Admin-View-As header, honoured only for an administrator and only for reads (GET/HEAD).
    Every write still runs as the administrator's own account, so an administrator can read any chat and file but change none."""
    target = str(request.headers.get("x-admin-view-as") or "").strip()
    if not target or request.method not in {"GET", "HEAD"} or not target.isdigit():
        return None
    try:
        from app.routers.lm_admin import allowed
    except Exception:
        return None
    return target if allowed(request) else None


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
