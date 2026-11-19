"""A person's files across every chat, and the deletion of files, projects and chats.

Uploads (from the device or imported from Google Drive) are kept on the server for good: nothing removes them by itself. This module makes them reachable
from any chat: it lists them together with the rendered videos and discovered clips, attaches one to the current chat again without uploading (a hard link, so no second copy
is made and deleting the older chat cannot break it), enforces a per-person space limit on uploads, and deletes on request.

File ids are plain strings: ``att:<attachment id>`` (an upload or a Drive import), ``out:<project id>:<file name>`` (a render in a project's exports) and
``mot:<motion id>:<version>`` (a motion graphic's video), and clip IDs for cuts from long videos.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from app.studio_ingest import IngestError, attachment_folder, finalize, kind_of
from app.studio_store import repo

log = logging.getLogger(__name__)
_CLIP_SLOTS = threading.BoundedSemaphore(2)
_CLIP_ERROR = "آماده‌سازی کلیپ انجام نشد. دوباره تلاش کنید."

QUOTA_BYTES = int(os.environ.get("STUDIO_USER_QUOTA_BYTES", str(5 * 1024**3)))


class QuotaExceeded(IngestError):
    pass


class Busy(RuntimeError):
    """Something is still working on it: stop that first."""


def _mb(value: int) -> str:
    return f"{value / 1024**3:.1f} GB" if value >= 1024**3 else f"{value / 1024**2:.0f} MB"


async def usage(user: str) -> int:
    return sum(int(a.get("size_bytes") or 0) for a in await repo.list_user_attachments(user))


def unlimited(user: str) -> bool:
    """Administrators (AI_ADMIN_USER_IDS) have no storage quota."""
    from app.config import settings
    return str(user) in {x.strip() for x in str(settings.AI_ADMIN_USER_IDS or "").split(",") if x.strip()}


async def ensure_room(user: str, size: int) -> None:
    if unlimited(user):
        return
    used = await usage(user)
    if used + int(size or 0) > QUOTA_BYTES:
        raise QuotaExceeded(f"فضای فایل‌های شما پر است ({_mb(used)} از {_mb(QUOTA_BYTES)}). از بخش Files چند فایل را حذف کنید و دوباره امتحان کنید.")


# ── listing ────────────────────────────────────────────────────────────────────────────────────────────

def _outputs(project: dict) -> list[dict]:
    from app import jobs
    ref = str(project.get("external_ref") or "")
    if not ref or project.get("engine") == "localize" or Path(ref).name != ref:
        return []
    # A job's folder is always JOBS_ROOT/<id> (app.jobs). jobs.get() opened a database session and loaded the whole plan for every project:
    # ~0.3 s each, 9 s for one person's library (36 s under load). The project already belongs to this person's chat, so the folder is enough.
    folder = jobs.JOBS_ROOT / ref / "exports"
    if not folder.is_dir():
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


def _discovery_clips(conversation: dict, user: str):
    """Read every analysis in an owned chat, including ones superseded by a later upload."""
    from app import long_video

    root = long_video.folder(user, conversation["id"], "")
    for directory in root.iterdir() if root.is_dir() else ():
        if not re.fullmatch(r"[a-f0-9]{12}", directory.name):
            continue
        try:
            analysis = long_video.load(directory)
        except (ValueError, OSError):
            continue
        if (analysis.get("user_key"), analysis.get("conversation_id"), analysis.get("id")) != (user, conversation["id"], directory.name):
            continue
        source = Path(analysis.get("source_path") or "")
        source_exists = source.is_file()
        for candidate in analysis.get("candidates", []):
            if candidate.get("hidden") or not re.fullmatch(r"c[a-f0-9]{9}", candidate.get("id", "")) or not candidate.get("ranges"):
                continue
            revision = long_video._preview_target(directory, candidate).stem
            target = directory / "clips" / f"library-{revision}.mp4"
            child = candidate.get("child_conversation_id") or ""
            prepared = long_video.ROOT / long_video._safe(user) / child / "attachments" / (candidate["id"] + ".mp4")
            path = target if target.is_file() else None
            if path is None and not candidate.get("child_stale") and re.fullmatch(r"[a-f0-9]{32}", child) and prepared.is_file():
                path = prepared
            if path is None and not source_exists:
                continue
            title = str(candidate.get("title") or "Discovery clip")
            yield {
                "id": f"clip:{conversation['id']}:{directory.name}:{revision}",
                "name": f"{title[:150]}.mp4",
                "kind": "video",
                "size": path.stat().st_size if path else 0,
                "created_at": _iso(candidate.get("created_at") or analysis.get("created_at") or 0),
                "source": "discovery",
                "folder": "discovery",
                "conversation_id": conversation["id"],
                "conversation_title": conversation.get("title", ""),
            }, path, target, source, candidate["ranges"]


def _render_discovery_clip(target: Path, source: Path, ranges: list) -> None:
    from app import long_video

    try:
        long_video.render_clip(source, ranges, target, small=False)
    except (OSError, subprocess.SubprocessError) as exc:
        target.with_suffix(".part.mp4").unlink(missing_ok=True)
        raise IngestError(_CLIP_ERROR) from exc


def _prepare_discovery_clip(target: Path, source: Path, ranges: list) -> Path:
    target.parent.mkdir(exist_ok=True)
    with target.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not target.is_file():
            _render_discovery_clip(target, source, ranges)
    return target


def _queue_discovery_clip(target: Path, source: Path, ranges: list) -> bool:
    """A short poll either finds the file or starts one encode across API processes."""
    if target.is_file():
        return True
    target.parent.mkdir(exist_ok=True)
    lock = target.with_suffix(".lock").open("a")
    handed_off = False
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        if target.is_file():
            return True

        failed = target.with_suffix(".failed")
        try:
            recently_failed = time.time() - failed.stat().st_mtime < 30
        except FileNotFoundError:
            recently_failed = False
        if recently_failed:
            raise IngestError(_CLIP_ERROR)
        if not _CLIP_SLOTS.acquire(blocking=False):
            return False

        def work() -> None:
            try:
                _render_discovery_clip(target, source, ranges)
                failed.unlink(missing_ok=True)
            except Exception:
                log.warning("Library cut failed for %s", target.stem, exc_info=True)
                failed.touch()
            finally:
                lock.close()
                _CLIP_SLOTS.release()

        try:
            threading.Thread(target=work, daemon=True, name="library-clip").start()
        except RuntimeError:
            _CLIP_SLOTS.release()
            raise
        handed_off = True
        return False
    finally:
        if not handed_off:
            lock.close()


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
            found.extend(row for row, *_ in _discovery_clips(conversation, user))
            parent = (conversation.get("state") or {}).get("parent") or {}
            from_discovery = bool(parent.get("analysis_id") and parent.get("candidate_id"))
            for output in [*_motion_videos(conversation, user), *[o for p in projects.get(cid, []) for o in _outputs(p)]]:
                stat = output["path"].stat()
                found.append({"id": output["id"], "name": output["name"], "kind": "video", "size": stat.st_size, "created_at": _iso(stat.st_mtime), "source": "output",
                              "conversation_id": cid, "conversation_title": conversation.get("title", ""),
                              **({"folder": "discovery"} if from_discovery else {})})
        return found
    items.extend(await asyncio.to_thread(outputs))
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"files": items, "usage": used, "quota": None if unlimited(user) else QUOTA_BYTES}


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

async def attach(user: str, conversation_id: str, file_id: str, *, defer: bool = False) -> dict | None:
    """Put a file the person already has into this chat as an attachment. The bytes are not copied: the new name is a hard link (a copy only when the disk
    does not allow one)."""
    await repo.get_conversation(conversation_id, user, message_limit=1)
    if file_id.startswith("clip:"):
        source_conversation_id = file_id.split(":", 2)[1]
        conversation = await repo.get_conversation(source_conversation_id, user, message_limit=1)
        clip = await asyncio.to_thread(lambda: next(
            (entry for entry in _discovery_clips(conversation, user) if entry[0]["id"] == file_id), None
        ))
        if clip is None:
            raise KeyError(file_id)
        row, source, target, original, ranges = clip
        if source is None:
            if defer:
                if not await asyncio.to_thread(_queue_discovery_clip, target, original, ranges):
                    return None
                source = target
            else:
                source = await asyncio.to_thread(_prepare_discovery_clip, target, original, ranges)
        info = {"kind": "clip", "name": row["name"]}
    else:
        source, info = await _resolve(user, file_id)
    if info["kind"] == "att":
        existing = info["row"]
        if existing["conversation_id"] == conversation_id:
            return existing                                    # already in this chat
        name, mime = existing["filename"], existing["mime_type"]
        meta = existing.get("metadata") or {}
    else:
        name, mime, meta = info.get("name", source.name), "video/mp4", {}
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
