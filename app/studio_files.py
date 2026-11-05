"""A person's files across every chat, and the deletion of files, projects and chats.

Uploads (from the device or imported from Google Drive) are kept on the server for good: nothing removes them by itself. This module makes them reachable
from any chat: it lists them together with the rendered videos, attaches one to the current chat again without uploading (a hard link, so no second copy
is made and deleting the older chat cannot break it), enforces a per-person space limit on uploads, and deletes on request.

File ids are plain strings: ``att:<attachment id>`` (an upload or a Drive import), ``out:<project id>:<file name>`` (a render in a project's exports) and
``mot:<motion id>:<version>`` (a motion graphic's video).
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import uuid
from pathlib import Path

from app.studio_ingest import IngestError, attachment_folder, finalize, kind_of
from app.studio_store import repo

QUOTA_BYTES = int(os.environ.get("STUDIO_USER_QUOTA_BYTES", str(5 * 1024**3)))


class QuotaExceeded(IngestError):
    pass


class Busy(RuntimeError):
    """Something is still working on it: stop that first."""


def _mb(value: int) -> str:
    return f"{value / 1024**3:.1f} GB" if value >= 1024**3 else f"{value / 1024**2:.0f} MB"


async def usage(user: str) -> int:
    return sum(int(a.get("size_bytes") or 0) for a in await repo.list_user_attachments(user))


async def ensure_room(user: str, size: int) -> None:
    used = await usage(user)
    if used + int(size or 0) > QUOTA_BYTES:
        raise QuotaExceeded(f"فضای فایل‌های شما پر است ({_mb(used)} از {_mb(QUOTA_BYTES)}). از بخش Files چند فایل را حذف کنید و دوباره امتحان کنید.")


# ── listing ────────────────────────────────────────────────────────────────────────────────────────────

def _outputs(project: dict) -> list[dict]:
    from app import jobs
    ref = project.get("external_ref")
    if not ref or project.get("engine") == "localize":
        return []
    job = jobs.get(ref)
    folder = (job.dir / "exports") if job else None
    if folder is None or not folder.is_dir():
        return []
    rows = []
    for path in sorted(folder.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]:
        rows.append({"path": path, "id": f"out:{project['id']}:{path.name}", "name": f"{project.get('title') or 'video'} — {path.name}"})
    return rows


def _motion_videos(conversation: dict, user: str) -> list[dict]:
    pointer = (conversation.get("state") or {}).get("motion")
    if not pointer:
        return []
    from app import motion_graphic
    try:
        directory = motion_graphic.locate(pointer["motion_id"], user)
        record = motion_graphic.load(directory)
    except (KeyError, OSError, ValueError):
        return []
    rows = []
    for version in (record.get("versions") or [])[-3:]:
        path = directory / f"v{version['n']}" / "motion.mp4"
        if path.is_file():
            rows.append({"path": path, "id": f"mot:{pointer['motion_id']}:{version['n']}", "name": f"{record.get('title') or conversation.get('title') or 'motion'} — v{version['n']}.mp4"})
    return rows


async def library(user: str) -> dict:
    conversations = {c["id"]: c for c in await repo.list_conversations(user)}
    projects = await repo.projects_for(list(conversations))
    items: list[dict] = []
    used = 0
    for a in await repo.list_user_attachments(user):
        used += int(a.get("size_bytes") or 0)
        if not Path(a["path"]).is_file():
            continue
        c = conversations.get(a["conversation_id"], {})
        items.append({"id": "att:" + a["id"], "name": a["filename"], "kind": a["kind"], "size": a["size_bytes"], "created_at": a["created_at"],
                      "source": "cloud" if (a.get("metadata") or {}).get("cloud") else "upload", "conversation_id": a["conversation_id"], "conversation_title": c.get("title", "")})

    def outputs() -> list[dict]:
        found = []
        for cid, conversation in conversations.items():
            for output in [*_motion_videos(conversation, user), *[o for p in projects.get(cid, []) for o in _outputs(p)]]:
                stat = output["path"].stat()
                found.append({"id": output["id"], "name": output["name"], "kind": "video", "size": stat.st_size, "created_at": _iso(stat.st_mtime), "source": "output",
                              "conversation_id": cid, "conversation_title": conversation.get("title", "")})
        return found
    items.extend(await asyncio.to_thread(outputs))
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"files": items, "usage": used, "quota": QUOTA_BYTES}


def _iso(timestamp: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


async def _resolve(user: str, file_id: str) -> tuple[Path, dict]:
    """The file on disk behind a library id, and what it belongs to. KeyError when it is not this person's or is gone."""
    kind, _, rest = file_id.partition(":")
    if kind == "att":
        row = next((a for a in await repo.list_user_attachments(user) if a["id"] == rest), None)
        if row is None or not Path(row["path"]).is_file():
            raise KeyError(file_id)
        return Path(row["path"]), {"kind": "att", "row": row}
    if kind == "out":
        pid, _, name = rest.partition(":")
        project = await repo.get_project(pid, user)
        from app import jobs
        job = jobs.get(project.get("external_ref") or "")
        path = (job.dir / "exports" / Path(name).name) if job else None
        if path is None or path.suffix != ".mp4" or not path.is_file():
            raise KeyError(file_id)
        return path, {"kind": "out", "project": project}
    if kind == "mot":
        motion_id, _, number = rest.partition(":")
        from app import motion_graphic
        directory = motion_graphic.locate(motion_id, user)
        if not number.isdigit():
            raise KeyError(file_id)
        path = directory / f"v{int(number)}" / "motion.mp4"
        if not path.is_file():
            raise KeyError(file_id)
        return path, {"kind": "mot", "directory": directory}
    raise KeyError(file_id)


# ── attach again ───────────────────────────────────────────────────────────────────────────────────────

async def attach(user: str, conversation_id: str, file_id: str) -> dict:
    """Put a file the person already has into this chat as an attachment. The bytes are not copied: the new name is a hard link (a copy only when the disk
    does not allow one)."""
    await repo.get_conversation(conversation_id, user)
    source, info = await _resolve(user, file_id)
    if info["kind"] == "att":
        existing = info["row"]
        if existing["conversation_id"] == conversation_id:
            return existing                                    # already in this chat
        name, mime = existing["filename"], existing["mime_type"]
        meta = existing.get("metadata") or {}
    else:
        name, mime, meta = source.name, "video/mp4", {}
    size = source.stat().st_size
    kind = kind_of(name) or "video"
    folder = attachment_folder(user, conversation_id)
    temporary = folder / f"library_{uuid.uuid4().hex}{source.suffix.lower()}"
    try:
        os.link(source, temporary)
    except OSError:
        await asyncio.to_thread(shutil.copy2, source, temporary)
    try:
        return await finalize(user, conversation_id, temporary, name, kind, mime, size, {**meta, "from_library": file_id})
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


# ── deleting ───────────────────────────────────────────────────────────────────────────────────────────

def _project_running(project: dict) -> bool:
    if project.get("status") == "running":
        return True
    ref = project.get("external_ref")
    if not ref:
        return False
    try:
        if project.get("engine") == "localize":
            from app import localize
            return str(localize.public(localize.load(ref)).get("status", "")) in {"running", "queued", "rendering"}
        from app import jobs
        job = jobs.get(ref)
        return bool(job and (job.render.status in {"queued", "running"} or job.generate.status in {"queued", "running"}))
    except Exception:
        return False


def _drop_project_files(project: dict) -> None:
    ref = project.get("external_ref")
    if not ref:
        return
    if project.get("engine") == "localize":
        from app import localize
        try:
            localize.delete(ref)
        except (KeyError, ValueError):
            pass
        return
    from app import jobs
    jobs.delete_job(ref)


async def delete_file(user: str, file_id: str) -> dict:
    path, info = await _resolve(user, file_id)
    size = path.stat().st_size
    if info["kind"] == "att":
        row = await repo.delete_attachment_row(info["row"]["id"], user)
        await asyncio.to_thread(path.unlink, missing_ok=True)
        return {"id": file_id, "freed": row["size_bytes"] if row else size}
    if info["kind"] == "out":
        if _project_running(info["project"]):
            raise Busy("این پروژه هنوز در حال کار است؛ ابتدا آن را متوقف کنید.")
    await asyncio.to_thread(path.unlink, missing_ok=True)
    return {"id": file_id, "freed": size}


async def delete_project(user: str, project_id: str) -> dict:
    project = await repo.get_project(project_id, user)
    if _project_running(project):
        raise Busy("این پروژه هنوز در حال کار است؛ ابتدا آن را متوقف کنید.")
    await repo.delete_project_row(project_id, user)
    await asyncio.to_thread(_drop_project_files, project)
    return {"id": project_id}


def _conversation_folder(user: str, conversation_id: str) -> Path:
    from app import studio_store
    return studio_store.ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", user) / conversation_id


async def delete_conversation(user: str, conversation_id: str) -> dict:
    from app import studio_orchestrator
    conversation = await repo.get_conversation(conversation_id, user)
    if studio_orchestrator.conversation_busy(conversation, user):
        raise Busy("در این چت کاری در جریان است؛ ابتدا آن را متوقف کنید.")
    projects = await repo.projects_for([conversation_id])
    if any(_project_running(p) for p in projects.get(conversation_id, [])):
        raise Busy("یکی از پروژه‌های این چت هنوز در حال کار است؛ ابتدا آن را متوقف کنید.")
    from app.agents import store as agent_store
    if any(r["status"] in {"queued", "running", "waiting_job", "waiting_approval"} for r in await agent_store.runs(conversation_id, user)):
        raise Busy("یک اجرای عامل در این چت ناتمام است؛ ابتدا آن را متوقف کنید.")
    removed = await repo.delete_conversation_rows(conversation_id, user)
    for project in removed:
        await asyncio.to_thread(_drop_project_files, project)
    await asyncio.to_thread(shutil.rmtree, _conversation_folder(user, conversation_id), True)
    return {"id": conversation_id, "projects": len(removed)}
