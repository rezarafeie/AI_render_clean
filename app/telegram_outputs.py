"""Deliver persisted Studio completions from the API process that owns the bot."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

log = logging.getLogger(__name__)
EVENTS = {"render.completed", "motion.completed", "pro.output"}
HISTORY_SECONDS = 7 * 86400


def on_event(conversation_id: str, event_type: str, data: dict) -> None:
    """Compatibility for older workers. Delivery reads the committed event in the API."""


async def _output(conversation_id: str, owner: str, kind: str, data: dict):
    from app import media_archive
    from app.studio_store import repo

    if kind == "pro.output" and data.get("attachment_id"):
        attachment, = await repo.get_attachments([str(data["attachment_id"])], conversation_id, owner, restore_media=False)
        return Path(attachment["path"]), str(data.get("title") or attachment["filename"])
    if kind == "motion.completed" and data.get("motion_id"):
        from app import motion_graphic

        directory = motion_graphic.locate(str(data["motion_id"]), owner)
        version = int(data.get("version") or 0) or None
        return motion_graphic.media_path(directory, "video", version, restore_media=False), str(motion_graphic.load(directory).get("title") or "")
    if kind == "render.completed" and data.get("project_id"):
        from app import jobs, localize, talking_reel

        project = await repo.get_project(str(data["project_id"]), owner)
        if project["conversation_id"] != conversation_id:
            raise KeyError("project belongs to another conversation")
        ref = str(project.get("external_ref") or "")
        if not ref or Path(ref).name != ref:
            return None
        if project["engine"] == "localize":
            directory = localize.LOCALIZE_ROOT / ref
            name = localize.load(ref).get("output")
        else:
            job = jobs.get(ref)
            if not job:
                return None
            directory = job.dir
            name = talking_reel.load(directory).get("output") if project["engine"] == "talking" else job.render.output
            if name and Path(name).name == name:
                name = "exports/" + name
        if name:
            path = (directory / name).resolve()
            if path.is_relative_to(directory.resolve()) and media_archive.available(path, owner):
                return path, str(project.get("title") or "")
    return None


@asynccontextmanager
async def _delivery_lock(db, key):
    async with db.lock(key, timeout=180, blocking_timeout=0) as lock:
        async def renew():
            while True:
                await asyncio.sleep(45)
                await lock.extend(180, replace_ttl=True)
        lease = asyncio.create_task(renew())
        try:
            yield
        finally:
            lease.cancel()
            with suppress(asyncio.CancelledError):
                await lease


async def send_output(db, token, chat: str | int, conversation: str, owner: str, path: Path, title: str = "", *, link_only: bool = False) -> bool:
    """Return True for an acknowledged or previously delivered output."""
    from app import media_archive
    from app.routers import telegram_studio as tg
    from redis.exceptions import LockError

    size, modified = media_archive.media_size_time(path, owner)
    identity = hashlib.sha256(f"{path.resolve()}:{size}:{modified}".encode()).hexdigest()
    key = f"{tg.PREFIX}delivery:{chat}:{conversation}:{identity}"
    try:
        async with _delivery_lock(db, key + ":lock"):
            if await db.exists(key):
                return True
            if await db.get(tg.PREFIX + f"tg:{chat}") != owner or await db.get(tg.PREFIX + f"user:{owner}") != str(chat):
                return False
            await tg._send_output_file(db, token, int(chat), conversation, owner, path, size, title, identity, link_only=link_only)
            await db.set(key, "1", ex=HISTORY_SECONDS * 4)
            return True
    except LockError:
        return False


async def _collect(db, prefix: str) -> None:
    from sqlalchemy import func, select
    from app.models import StudioConversation, StudioEvent
    from app.studio_store import AsyncSessionLocal, DB_AVAILABLE

    if not DB_AVAILABLE:
        return
    watermark = prefix + "outbox:watermark"
    async with db.lock(prefix + "outbox:collect", timeout=30, blocking_timeout=0):
        cursor = await db.get(watermark)
        async with AsyncSessionLocal() as session:
            if cursor is None:
                cursor = await session.scalar(select(func.coalesce(func.max(StudioEvent.id), 0)))
                await db.set(watermark, cursor)
                return
            rows = (await session.execute(select(StudioEvent.id, StudioEvent.conversation_id, StudioEvent.event_type,
                                                 StudioEvent.data, StudioConversation.user_key)
                .join(StudioConversation, StudioConversation.id == StudioEvent.conversation_id)
                .where(StudioEvent.id > int(cursor), StudioEvent.event_type.in_(EVENTS))
                .order_by(StudioEvent.id).limit(80))).all()
        for identifier, conversation, kind, data, owner in rows:
            if await db.exists(prefix + "user:" + str(owner)):
                async with db.pipeline(transaction=True) as pipe:
                    pipe.set(prefix + f"outbox:event:{identifier}", json.dumps([conversation, kind, data or {}, str(owner)]), nx=True, ex=HISTORY_SECONDS)
                    pipe.zadd(prefix + "outbox", {str(identifier): time.time()}, nx=True)
                    pipe.set(watermark, identifier)
                    await pipe.execute()
            else:
                await db.set(watermark, identifier)


async def enqueue_attachment(db, conversation: str, owner: str, attachment_id: str) -> None:
    from app.routers.telegram_studio import PREFIX

    identifier = "attachment:" + attachment_id
    key = PREFIX + f"outbox:event:{identifier}"
    item = json.dumps([conversation, "pro.output", {"attachment_id": attachment_id}, owner])
    async with db.pipeline(transaction=True) as pipe:
        pipe.set(key, item, nx=True, ex=HISTORY_SECONDS)
        pipe.zadd(PREFIX + "outbox", {identifier: time.time()}, nx=True)
        await pipe.execute()


async def _sync_linked_conversations(db, prefix: str) -> None:
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from app.models import StudioProject
    from app.studio_orchestrator import sync_conversation
    from app.studio_store import AsyncSessionLocal, DB_AVAILABLE

    if not DB_AVAILABLE:
        return
    async with db.lock(prefix + "outbox:sync", timeout=60, blocking_timeout=0):
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(select(StudioProject.conversation_id, StudioProject.user_key)
                .where(StudioProject.status == "running",
                       StudioProject.updated_at >= datetime.now(timezone.utc) - timedelta(days=2))
                .distinct().limit(300))).all()
        for conversation, owner in rows:
            if await db.exists(prefix + "user:" + str(owner)):
                await sync_conversation(conversation, str(owner))


async def _send_pending(db, tg, token, identifier):
    from redis.exceptions import LockError

    prefix = tg.PREFIX
    queue = prefix + "outbox"
    item = prefix + f"outbox:event:{identifier}"
    try:
        async with _delivery_lock(db, item + ":lock"):
            await db.zadd(queue, {identifier: time.time() + 90}, xx=True)
            results = await db.get(item)
            if results:
                conversation, kind, data, owner = json.loads(results)
                chat = await db.get(prefix + "user:" + owner)
                if chat and await db.get(prefix + "tg:" + chat) == owner:
                    try:
                        output = await _output(conversation, owner, kind, data)
                    except KeyError:
                        output = None
                    if not output:
                        return
                    path, title = output
                    attempts = int(await db.get(item + ":failures") or 0)
                    if not await send_output(db, token, chat, conversation, owner, path, title, link_only=attempts >= 3):
                        return
            await db.zrem(queue, identifier)
            await db.delete(item, item + ":failures")
    except LockError:
        pass
    except Exception as error:
        async with db.pipeline(transaction=True) as pipe:
            pipe.incr(item + ":failures")
            pipe.expire(item + ":failures", HISTORY_SECONDS)
            await pipe.execute()
        log.warning("Telegram output delivery pending (%s)", type(error).__name__)


async def delivery_loop():
    from app.routers import telegram_studio as tg
    from redis.exceptions import LockError

    token, _, _ = tg._config()
    async with asyncio.TaskGroup() as tasks:
        async def collect():
            while True:
                try:
                    async with tg.storage() as db:
                        await _collect(db, tg.PREFIX)
                except LockError:
                    pass
                except Exception as error:
                    log.warning("Telegram output collection: %s", type(error).__name__)
                await asyncio.sleep(4)

        async def deliver():
            while True:
                try:
                    async with tg.storage() as db:
                        batch = await db.zrangebyscore(tg.PREFIX + "outbox", 0, time.time(), start=0, num=2)
                        await asyncio.gather(*(_send_pending(db, tg, token, identifier) for identifier in batch))
                except Exception as error:
                    log.warning("Telegram output queue: %s", type(error).__name__)
                await asyncio.sleep(2)

        async def synchronize():
            while True:
                try:
                    async with tg.storage() as db:
                        await _sync_linked_conversations(db, tg.PREFIX)
                except LockError:
                    pass
                except Exception as error:
                    log.warning("Telegram render synchronization: %s", type(error).__name__)
                await asyncio.sleep(20)

        tasks.create_task(synchronize())
        tasks.create_task(collect())
        tasks.create_task(deliver())
