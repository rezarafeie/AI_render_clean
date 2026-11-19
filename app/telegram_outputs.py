"""Finished outputs of ANY chat go to the person's Telegram when they linked it (Settings → Telegram).

The bot already sends everything of the chat it is working in (app.routers.telegram_studio, the `chat:<tg>` pointer). This covers every other chat
(Studio on the web, Lite, Medium, Pro): a final video becomes a Telegram message with the file (or a link when it is over the 50 MB bot limit) and a
button that opens the chat. Triggered by the studio's own events (`render.completed`, `motion.completed`, `pro.output`), once per output.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)
EVENTS = {"render.completed", "motion.completed", "pro.output"}
LIMIT = 50_000_000                           # the Telegram bot upload limit


def on_event(conversation_id: str, event_type: str, data: dict) -> None:
    """Called after a studio event is saved; never raises and never blocks the caller."""
    if event_type not in EVENTS:
        return
    try:
        threading.Thread(target=lambda: asyncio.run(_deliver(conversation_id, event_type, dict(data or {}))), daemon=True,
                         name="telegram-output").start()
    except Exception:
        log.debug("telegram output not scheduled", exc_info=True)


async def _owner(conversation_id: str) -> str | None:
    from app.studio_store import AsyncSessionLocal, DB_AVAILABLE
    if not DB_AVAILABLE:
        return None
    from app.models import StudioConversation
    async with AsyncSessionLocal() as db:
        row = await db.get(StudioConversation, conversation_id)
        return str(row.user_key) if row else None


async def _output(conversation_id: str, user: str, event_type: str, data: dict) -> tuple[Path | None, str, str]:
    """(file, a unique label of this output, its title)."""
    from app.studio_store import repo
    if event_type == "pro.output" and data.get("attachment_id"):
        rows = await repo.get_attachments([str(data["attachment_id"])], conversation_id, user)
        if rows:
            return Path(rows[0]["path"]), f"pro:{data['attachment_id']}", str(data.get("title") or rows[0]["filename"])
    if event_type == "motion.completed" and data.get("motion_id"):
        from app import motion_graphic
        try:
            directory = motion_graphic.locate(str(data["motion_id"]), user)
            version = int(data.get("version") or motion_graphic.load(directory).get("current") or 0)
            path = motion_graphic.media_path(directory, "video", version)
            return path, f"motion:{data['motion_id']}:{version}", str(motion_graphic.load(directory).get("title") or "")
        except (KeyError, OSError, ValueError):
            return None, "", ""
    if event_type == "render.completed" and data.get("project_id"):
        try:
            project = await repo.get_project(str(data["project_id"]), user)
        except KeyError:
            return None, "", ""
        ref = str(project.get("external_ref") or "")
        path = None
        if project["engine"] == "localize" and ref:
            from app import localize
            path = localize.LOCALIZE_ROOT / ref / (localize.load(ref).get("output") or "")
        elif ref and Path(ref).name == ref:
            from app import jobs
            exports = jobs.JOBS_ROOT / ref / "exports"
            videos = sorted(exports.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if exports.is_dir() else []
            path = next((v for v in videos if "preview" not in v.name), videos[0] if videos else None)
        if path and path.is_file():
            stamp = path.stat()
            return path, f"render:{project['id']}:{path.name}:{stamp.st_size}", str(project.get("title") or "")
    return None, "", ""


async def _deliver(conversation_id: str, event_type: str, data: dict) -> None:
    try:
        from app.routers import telegram_studio as tg
        try:
            token, _, base = tg._config()
        except Exception:
            return                                            # the Telegram integration is off on this server
        user = await _owner(conversation_id)
        if not user:
            return
        async with tg.storage() as db:
            chat = await db.get(tg.PREFIX + "user:" + user)
            if not chat:
                return                                        # not linked
            if await db.get(tg.PREFIX + "chat:" + chat) == conversation_id:
                return                                        # the bot is working in this chat and sends its outputs itself
            path, label, title = await _output(conversation_id, user, event_type, data)
            if not path or not path.is_file():
                return
            if not await db.set(tg.PREFIX + "out:" + conversation_id + ":" + label, "1", nx=True, ex=30 * 86400):
                return                                        # already sent
            open_button = [[{"text": "باز کردن در استودیو", "web_app": {"url": base + "/studio/" + conversation_id}}]]
            name = f"«{title.strip()[:80]}»" if title.strip() else "شما"
            if path.stat().st_size <= LIMIT:
                await tg._send_file(token, int(chat), path, "video" if path.suffix.lower() == ".mp4" else "document")
                await tg._send(token, int(chat), f"خروجی {name} آماده شد.", buttons=open_button)
            else:
                await tg._send(token, int(chat), f"خروجی {name} آماده شد. حجمش از حد تلگرام بیشتر است؛ از استودیو دانلودش کنید.", buttons=open_button)
    except Exception:
        log.warning("telegram output for %s not sent", conversation_id, exc_info=True)
