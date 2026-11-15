"""Administrator view of the people who use the app: users, their chats, projects, renders and files, with full detail. Read-only (nothing here edits or deletes)."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app import jobs as jobstore
from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Job, StudioAttachment, StudioConversation, StudioEvent, StudioMessage, StudioProject, StudioProjectVersion, UserModel
from app.routers.lm_admin import admin

router = APIRouter(prefix="/admin/manage", tags=["administration"], dependencies=[Depends(admin)])


def _db():
    if AsyncSessionLocal is None:
        raise HTTPException(503, "The database is not available")
    return AsyncSessionLocal()


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def _user_row(row: UserModel) -> dict:
    return {"id": row.id, "email": row.email, "name": row.name, "created_at": row.created_at, "is_active": bool(row.is_active)}


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except OSError:
        pass
    return total


@router.get("/users")
async def users(query: str = Query("", max_length=100), limit: int = Query(200, ge=1, le=500)):
    async with _db() as db:
        stmt = select(UserModel).order_by(UserModel.id)
        if query.strip():
            like = f"%{query.strip().lower()}%"
            stmt = stmt.where(func.lower(UserModel.email).like(like) | func.lower(UserModel.name).like(like))
        rows = (await db.execute(stmt.limit(limit))).scalars().all()
        chats = {k: (c, m) for k, c, m in (await db.execute(select(StudioConversation.user_key, func.count(), func.max(StudioConversation.updated_at)).group_by(StudioConversation.user_key))).all()}
        projects = {k: c for k, c in (await db.execute(select(StudioProject.user_key, func.count()).group_by(StudioProject.user_key))).all()}
        files = {k: (c, s or 0) for k, c, s in (await db.execute(select(StudioAttachment.user_key, func.count(), func.sum(StudioAttachment.size_bytes)).group_by(StudioAttachment.user_key))).all()}
        jobs = {k: c for k, c in (await db.execute(select(Job.user_id, func.count()).group_by(Job.user_id))).all()}
        total = (await db.execute(select(func.count()).select_from(UserModel))).scalar_one()
    out = []
    for row in rows:
        key = str(row.id)
        count, last = chats.get(key, (0, None))
        out.append({**_user_row(row), "chats": count, "projects": projects.get(key, 0), "jobs": jobs.get(row.id, 0), "files": files.get(key, (0, 0))[0],
                    "storage_bytes": int(files.get(key, (0, 0))[1]), "last_active": _iso(last)})
    return {"total": total, "users": out}


def _chat_status(projects: list) -> str:
    """One word for a chat: what its newest project is doing (running / done / failed / stopped), or idle when it has none."""
    if not projects:
        return "idle"
    newest = max(projects, key=lambda p: p.updated_at or p.created_at)
    status = str(newest.status or "")
    return {"planning": "running", "running": "running", "analyzing": "running", "rendering": "running", "queued": "running", "awaiting_input": "waiting", "awaiting_confirmation": "waiting",
            "done": "done", "completed": "done", "ready": "done", "failed": "failed", "error": "failed", "canceled": "stopped", "cancelled": "stopped"}.get(status, status or "idle")


@router.get("/chats")
async def all_chats(query: str = Query("", max_length=100), user: int | None = None, status: str = Query("", max_length=20), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    """Every chat of every person, newest first: just the facts (title, who, when, status) and the link; the chat itself is opened in the chat page (read-only for an administrator)."""
    async with _db() as db:
        base = select(StudioConversation)
        if query.strip():
            base = base.where(StudioConversation.title.ilike(f"%{query.strip()}%"))
        if user is not None:
            base = base.where(StudioConversation.user_key == str(user))
        total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (await db.execute(base.order_by(StudioConversation.updated_at.desc()).limit(limit if not status else 400).offset(offset if not status else 0))).scalars().all()
        ids = [c.id for c in rows]
        projects = (await db.execute(select(StudioProject).where(StudioProject.conversation_id.in_(ids)))).scalars().all() if ids else []
        counts = dict((await db.execute(select(StudioMessage.conversation_id, func.count()).where(StudioMessage.conversation_id.in_(ids)).group_by(StudioMessage.conversation_id))).all()) if ids else {}
        file_counts = dict((await db.execute(select(StudioAttachment.conversation_id, func.count()).where(StudioAttachment.conversation_id.in_(ids)).group_by(StudioAttachment.conversation_id))).all()) if ids else {}
        keys = {int(c.user_key) for c in rows if str(c.user_key).isdigit()}
        people = {u.id: u for u in (await db.execute(select(UserModel).where(UserModel.id.in_(keys)))).scalars().all()} if keys else {}
    by_chat: dict[str, list] = {}
    for p in projects:
        by_chat.setdefault(p.conversation_id, []).append(p)
    out = []
    for c in rows:
        person = people.get(int(c.user_key)) if str(c.user_key).isdigit() else None
        state = _chat_status(by_chat.get(c.id, []))
        if status and state != status:
            continue
        out.append({"id": c.id, "title": c.title, "user": {"id": c.user_key, "name": person.name if person else "", "email": person.email if person else ""}, "status": state,
                    "messages": counts.get(c.id, 0), "projects": len(by_chat.get(c.id, [])), "files": file_counts.get(c.id, 0), "created_at": _iso(c.created_at), "updated_at": _iso(c.updated_at)})
    if status:
        total, out = len(out), out[offset:offset + limit]
    return {"total": total, "chats": out}


@router.get("/files")
async def all_files(query: str = Query("", max_length=100), user: int | None = None, kind: str = Query("", max_length=12), limit: int = Query(60, ge=1, le=200), offset: int = Query(0, ge=0)):
    """Every uploaded file of every person, newest first, with the chat it belongs to."""
    async with _db() as db:
        base = select(StudioAttachment)
        if query.strip():
            base = base.where(StudioAttachment.filename.ilike(f"%{query.strip()}%"))
        if user is not None:
            base = base.where(StudioAttachment.user_key == str(user))
        if kind in {"video", "image", "audio"}:
            base = base.where(StudioAttachment.kind == kind)
        total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = (await db.execute(base.order_by(StudioAttachment.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        keys = {int(f.user_key) for f in rows if str(f.user_key).isdigit()}
        people = {u.id: u for u in (await db.execute(select(UserModel).where(UserModel.id.in_(keys)))).scalars().all()} if keys else {}
        titles = {c.id: c.title for c in (await db.execute(select(StudioConversation).where(StudioConversation.id.in_({f.conversation_id for f in rows})))).scalars().all()} if rows else {}
    return {"total": total, "files": [{"id": f.id, "conversation_id": f.conversation_id, "chat_title": titles.get(f.conversation_id, ""), "name": f.filename, "kind": f.kind, "mime": f.mime_type,
                                       "size": f.size_bytes, "created_at": _iso(f.created_at),
                                       "user": {"id": f.user_key, "name": (people.get(int(f.user_key)).name if str(f.user_key).isdigit() and people.get(int(f.user_key)) else "")}} for f in rows]}


@router.get("/users/{user_id}")
async def user_detail(user_id: int):
    key = str(user_id)
    async with _db() as db:
        row = await db.get(UserModel, user_id)
        if row is None:
            raise HTTPException(404, "user not found")
        counts = dict((await db.execute(select(StudioMessage.conversation_id, func.count()).join(StudioConversation, StudioConversation.id == StudioMessage.conversation_id)
                                        .where(StudioConversation.user_key == key).group_by(StudioMessage.conversation_id))).all())
        conversations = (await db.execute(select(StudioConversation).where(StudioConversation.user_key == key).order_by(StudioConversation.updated_at.desc()).limit(300))).scalars().all()
        projects = (await db.execute(select(StudioProject).where(StudioProject.user_key == key).order_by(StudioProject.updated_at.desc()).limit(300))).scalars().all()
        files = (await db.execute(select(StudioAttachment).where(StudioAttachment.user_key == key).order_by(StudioAttachment.created_at.desc()).limit(400))).scalars().all()
        job_rows = (await db.execute(select(Job).where(Job.user_id == user_id).order_by(Job.created_at.desc()).limit(200))).scalars().all()
    return {
        "user": _user_row(row),
        "conversations": [{"id": c.id, "title": c.title, "language": c.language, "messages": counts.get(c.id, 0), "status": _chat_status([p for p in projects if p.conversation_id == c.id]),
                           "created_at": _iso(c.created_at), "updated_at": _iso(c.updated_at)} for c in conversations],
        "projects": [{"id": p.id, "conversation_id": p.conversation_id, "title": p.title, "engine": p.engine, "status": p.status, "job": p.external_ref, "version": p.current_version,
                      "created_at": _iso(p.created_at), "updated_at": _iso(p.updated_at)} for p in projects],
        "files": [{"id": f.id, "conversation_id": f.conversation_id, "name": f.filename, "kind": f.kind, "mime": f.mime_type, "size": f.size_bytes, "created_at": _iso(f.created_at)} for f in files],
        "jobs": [{"id": j.id, "title": j.title, "status": j.status, "stage": j.stage, "progress": j.progress_pct, "message": (j.message or "")[:300], "created_at": j.created_at, "updated_at": j.updated_at} for j in job_rows],
        "storage_bytes": sum(int(f.size_bytes or 0) for f in files),
    }


@router.get("/conversations/{conversation_id}")
async def conversation_detail(conversation_id: str, messages: int = Query(300, ge=1, le=1000)):
    async with _db() as db:
        conversation = await db.get(StudioConversation, conversation_id)
        if conversation is None:
            raise HTTPException(404, "chat not found")
        rows = (await db.execute(select(StudioMessage).where(StudioMessage.conversation_id == conversation_id).order_by(StudioMessage.id).limit(messages))).scalars().all()
        projects = (await db.execute(select(StudioProject).where(StudioProject.conversation_id == conversation_id))).scalars().all()
        files = (await db.execute(select(StudioAttachment).where(StudioAttachment.conversation_id == conversation_id))).scalars().all()
        events = (await db.execute(select(func.count()).select_from(StudioEvent).where(StudioEvent.conversation_id == conversation_id))).scalar_one()
    return {"conversation": {"id": conversation.id, "user": conversation.user_key, "title": conversation.title, "language": conversation.language, "created_at": _iso(conversation.created_at),
                             "updated_at": _iso(conversation.updated_at), "events": events},
            "messages": [{"id": m.id, "role": m.role, "content": m.content[:6000], "attachments": m.attachments or [], "created_at": _iso(m.created_at)} for m in rows],
            "projects": [{"id": p.id, "title": p.title, "engine": p.engine, "status": p.status} for p in projects],
            "files": [{"id": f.id, "name": f.filename, "kind": f.kind, "size": f.size_bytes} for f in files]}


@router.get("/projects/{project_id}")
async def project_detail(project_id: str):
    async with _db() as db:
        project = await db.get(StudioProject, project_id)
        if project is None:
            raise HTTPException(404, "project not found")
        versions = (await db.execute(select(StudioProjectVersion).where(StudioProjectVersion.project_id == project_id).order_by(StudioProjectVersion.version.desc()).limit(30))).scalars().all()
        events = (await db.execute(select(StudioEvent).where(StudioEvent.conversation_id == project.conversation_id).order_by(StudioEvent.seq.desc()).limit(80))).scalars().all()
    state = project.state or {}
    observed = state.get("last_observed") or {}
    job_info = None
    exports: list[dict] = []
    if project.external_ref:
        job = jobstore.get(project.external_ref)
        if job is not None:
            render = job.render
            job_info = {"id": job.id, "status": render.status, "message": render.message, "progress": render.progress, "output": render.output, "versions": list(job.versions or []),
                        "technical_qc": {k: v for k, v in (render.technical_qc or {}).items() if k != "creative_review"}, "creative_review": ((render.technical_qc or {}).get("creative_review") or {}).get("summary"),
                        "storage_bytes": _dir_size(job.dir)}
            folder = job.dir / "exports"
            if folder.is_dir():
                exports = [{"name": f.name, "size": f.stat().st_size} for f in sorted(folder.iterdir()) if f.is_file()]
    return {"project": {"id": project.id, "conversation_id": project.conversation_id, "user": project.user_key, "title": project.title, "engine": project.engine, "status": project.status,
                        "job": project.external_ref, "version": project.current_version, "created_at": _iso(project.created_at), "updated_at": _iso(project.updated_at)},
            "request": str(state.get("request") or "")[:3000], "observed": observed, "design_choice": state.get("design_choice"),
            "state_keys": sorted(state.keys()), "job": job_info, "exports": exports,
            "versions": [{"version": v.version, "created_at": _iso(getattr(v, "created_at", None))} for v in versions],
            "events": [{"seq": e.seq, "type": e.event_type, "at": _iso(e.created_at), "message": str((e.data or {}).get("message") or (e.data or {}).get("stage") or "")[:240]} for e in reversed(events)]}


@router.get("/files/{attachment_id}")
async def file_content(attachment_id: str):
    async with _db() as db:
        row = await db.get(StudioAttachment, attachment_id)
    if row is None:
        raise HTTPException(404, "file not found")
    path = Path(row.path).resolve()
    root = Path(settings.JOBS_DIR).expanduser().resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(path, media_type=row.mime_type or None, filename=row.filename)


@router.get("/projects/{project_id}/exports/{name}")
async def export_content(project_id: str, name: str):
    async with _db() as db:
        project = await db.get(StudioProject, project_id)
    job = jobstore.get(project.external_ref) if project is not None and project.external_ref else None
    if job is None or Path(name).name != name:
        raise HTTPException(404, "file not found")
    path = job.dir / "exports" / name
    if not path.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(path)
