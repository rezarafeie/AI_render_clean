"""The Projects page: one card per chat that made something, with its kind, real state, thumbnail and the chat to open.

Read from what exists (conversations, their projects, motion films); thumbnails of finished talking / localized videos are one frame cut
from the output the first time and kept on disk (<JOBS_DIR>/thumbs)."""
from __future__ import annotations

import asyncio
import hashlib
import subprocess
from pathlib import Path

from app.config import settings
from app.studio_home import KINDS, STATUS_LABELS, _motion_view, kind_of, status_of

TYPE_LABELS = {**KINDS, "edit": "تدوین هوشمند", "chat": "گفتگو"}


def thumbs_dir() -> Path:
    path = Path(settings.JOBS_DIR) / "thumbs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cut_frame(video: Path, key: str) -> Path | None:
    """One 480 px wide frame (about a second in) of `video`, cached under a name that includes the file's size and time, so a new render gets a new picture."""
    stat = video.stat()
    target = thumbs_dir() / (hashlib.sha1(f"{key}|{stat.st_size}|{int(stat.st_mtime)}".encode()).hexdigest()[:24] + ".jpg")
    if target.is_file() and target.stat().st_size > 0:
        return target
    temporary = target.with_suffix(".tmp.jpg")
    for seek in ("1", "0"):
        done = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", seek, "-i", str(video), "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", str(temporary)],
                              capture_output=True, timeout=40)
        if done.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
            temporary.replace(target)
            return target
    temporary.unlink(missing_ok=True)
    return None


def summarize(conversation: dict, projects: list[dict], motion: dict | None) -> dict:
    kind = kind_of(conversation, projects)
    status = status_of(projects, motion)
    latest = max(projects, key=lambda p: str(p.get("updated_at") or ""), default=None)
    thumb = None
    if motion and motion.get("completed"):
        thumb = f"/studio/motion/{motion['id']}/thumb"
    elif latest and latest.get("engine") in ("talking", "localize") and status == "ready":
        thumb = f"/studio/projects/{latest['id']}/thumb"
    return {"id": conversation["id"], "title": conversation.get("title") or "", "updated_at": conversation.get("updated_at"), "kind": kind,
            "kind_label": TYPE_LABELS.get(kind, "تدوین هوشمند"), "status": status, "status_label": STATUS_LABELS[status], "thumb": thumb,
            "projects": len(projects), "refs": [p["external_ref"] for p in projects if p.get("external_ref")]}


async def build(user_key: str, limit: int = 400) -> dict:
    from app.studio_store import repo
    conversations = (await repo.list_conversations(user_key))[:limit]
    by_id = await repo.projects_for([c["id"] for c in conversations])
    motions = await asyncio.gather(*(asyncio.to_thread(_motion_view, user_key, c) for c in conversations))
    items = [summarize(c, by_id.get(c["id"], []), m) for c, m in zip(conversations, motions)]
    items = [i for i in items if not (i["kind"] == "chat" and i["status"] == "draft" and not i["projects"])]      # a chat nothing was made in is not a project
    return {"items": items}
