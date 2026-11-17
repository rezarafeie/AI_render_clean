"""Telegram identity linking and a thin adapter to the existing Studio API."""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import time
from types import SimpleNamespace

from html import escape
import re

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit

from starlette.datastructures import Headers, UploadFile
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import auth
from app.config import settings
from app.routers import studio

router = APIRouter(prefix="/integrations/telegram", tags=["telegram"])
PREFIX = "editorgpt:telegram:"
PAIR_TTL = 600
log = logging.getLogger(__name__)
WORK = PREFIX + "pending-files"
WATCH = PREFIX + "watch"
REPLIES = PREFIX + "replies"
MODES = {"lite": "Lite", "medium": "Medium", "pro": "Pro"}
WORK_REQUEST = re.compile(
    r"(?:بساز|تولید کن|رندر بگیر|رندر کن|تدوین کن|ادیت کن|ویرایش کن|"
    r"زیرنویس (?:کن|بزن|اضافه کن)|کوتاه کن|ترجمه کن|اصلاح کن|عوض کن|تغییر بده|حذف کن|اضافه کن|ادامه بده|"
    r"^(?:(?:please|can you|could you|i want you to) )?(?:make|create|render|edit|cut|subtitle|transcribe|dub|localize|generate)\b)", re.I)


def _starts_work(text):
    text = text.strip().replace("‌", " ").replace("ي", "ی").replace("ك", "ک")
    if re.search(r"^(?:چطور|چگونه|آیا|چیست|فرق\s|تفاوت\s|what\b|how\b|why\b|can you explain\b)", text, re.I):
        return False
    return bool(WORK_REQUEST.search(text))



@asynccontextmanager
async def storage():
    if not settings.REDIS_URL:
        raise HTTPException(503, "Telegram integration requires Redis")
    from redis.asyncio import from_url
    client = from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


def _config():
    token = os.environ.get("EDITOR_TELEGRAM_BOT_TOKEN", "")
    secret = os.environ.get("EDITOR_TELEGRAM_WEBHOOK_SECRET", "")
    base = os.environ.get("EDITOR_TELEGRAM_STUDIO_URL", "").rstrip("/")
    if not token or not secret or not base.startswith("https://"):
        raise HTTPException(503, "Telegram integration is disabled")
    return token, secret, base


def _key(code):
    return PREFIX + "pair:" + hashlib.sha256(code.encode()).hexdigest()


class Pair(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{32}$")


# Check both directions and consume the code in a single transaction.
PAIR_SCRIPT = """
local telegram = redis.call('GET', KEYS[1])
if not telegram then return 0 end
local account = ARGV[1]
local by_tg = ARGV[2] .. 'tg:' .. telegram
local by_user = ARGV[2] .. 'user:' .. account
local old_account = redis.call('GET', by_tg)
local old_telegram = redis.call('GET', by_user)
if (old_account and old_account ~= account) or (old_telegram and old_telegram ~= telegram) then return -1 end
redis.call('SET', by_tg, account)
redis.call('SET', by_user, telegram)
redis.call('DEL', KEYS[1])
return telegram
"""


@router.get("/link")
async def link_status(request: Request):
    async with storage() as db:
        return {"linked": bool(await db.exists(PREFIX + "user:" + str(request.state.user.id)))}


@router.post("/link")
async def link(request: Request, body: Pair):
    token, _, base = _config()
    async with storage() as db:
        result = await db.eval(PAIR_SCRIPT, 1, _key(body.code), str(request.state.user.id), PREFIX)
    if result == -1:
        raise HTTPException(409, "یکی از حساب‌ها قبلاً متصل است. ابتدا اتصال قبلی را قطع کنید.")
    if not result:
        raise HTTPException(409, "این لینک منقضی شده است. در ربات دکمهٔ اتصال حساب را دوباره بزنید.")
    try:
        await _send(token, int(result), "حساب EditorGPT متصل شد.", buttons=_menu(base))
    except HTTPException:
        pass  # Linking is durable even when the confirmation message cannot be delivered.
    return {"linked": True}


@router.delete("/link")
async def unlink(request: Request):
    user = str(request.state.user.id)
    async with storage() as db:
        await db.eval("""
            local telegram = redis.call('GET', KEYS[1])
            if not telegram then return 0 end
            redis.call('DEL', KEYS[1], ARGV[1] .. 'tg:' .. telegram, ARGV[1] .. 'chat:' .. telegram, ARGV[1] .. 'reference:' .. telegram .. ':' .. ARGV[2])
            return 1
            """, 1, PREFIX + "user:" + user, PREFIX, user)
    return {"linked": False}


def _relay_headers():
    return {"x-relay-secret": os.environ.get("EDITOR_TELEGRAM_RELAY_SECRET", "")}


async def _bot_call(client, token, method, payload):
    relay = os.environ.get("EDITOR_TELEGRAM_BOT_RELAY_URL")
    if relay:
        return await client.post(relay, headers=_relay_headers(), json={"method": method, "payload": payload})
    return await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)


async def _relay_download(request, conversation_id, file, size):
    relay = os.environ.get("EDITOR_TELEGRAM_DOWNLOAD_RELAY_URL")
    if not relay:
        raise HTTPException(413, "این فایل را از بخش آپلود Studio داخل تلگرام بفرستید.")
    if type(size) is not int or not 0 < size <= studio.MAX_BYTES["video"]:
        raise HTTPException(413, "اندازهٔ فایل تلگرام معتبر نیست.")
    with tempfile.TemporaryFile() as download:
        async with httpx.AsyncClient(timeout=65) as client:
            session = None
            for offset in range(0, size, 1024**2):
                length = min(1024**2, size - offset)
                payload = {"fileId": file["file_id"], "offset": offset, "length": length, "session": session}
                for attempt in range(3):
                    try:
                        response = await client.post(relay, headers=_relay_headers(), json=payload)
                        if not response.is_success:
                            log.warning("Telegram MTProto chunk failed: HTTP %s, offset=%s", response.status_code, offset)
                        response.raise_for_status()
                        block = response.content
                        if len(block) != length or hashlib.sha256(block).hexdigest() != response.headers.get("x-content-sha256"):
                            raise ValueError("Invalid chunk")
                        break
                    except (httpx.HTTPError, ValueError):
                        if attempt == 2:
                            raise HTTPException(502, "انتقال فایل تلگرام ناموفق بود.") from None
                session = response.headers.get("x-telegram-session") or session
                download.write(block)
        download.seek(0)
        return await _ingest(request, conversation_id, file, download)


async def _send(token, chat, text, *, buttons=None, choices=None):
    body = {"chat_id": chat, "text": text}
    if buttons:
        body["reply_markup"] = {"inline_keyboard": buttons}
    if choices:
        body["reply_markup"] = {"keyboard": [[{"text": choice} for choice in choices]], "resize_keyboard": True, "one_time_keyboard": True}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await _bot_call(client, token, "sendMessage", body)
        if response.is_success and response.json().get("ok"):
            return response.json()["result"]["message_id"]
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    raise HTTPException(502, "Telegram could not deliver the message")


def _menu(base, conversation=None):
    def launch(label, path):
        return {"text": label, "web_app": {"url": base + path}}
    return [
        [launch("🎬 Studio", "/studio" + ("/" + conversation if conversation else "")),
         launch("📸 InstaGPT", "/insta")],
        [{"text": "موتور و تنظیمات", "callback_data": "studio:settings"},
         {"text": "گفتگوی جدید", "callback_data": "studio:new"}],
        [{"text": "گفتگو با هرمس", "callback_data": "studio:hermes"},
         launch("پروژه‌ها", "/projects")],
    ]


def _settings_menu(base, mode):
    return [
        [{"text": ("✓ " if value == mode else "") + label, "callback_data": "studio:" + value}
         for value, label in MODES.items()],
        [{"text": "تنظیمات حساب", "web_app": {"url": base + "/settings#integrations"}},
         {"text": "اتصال تلگرام", "web_app": {"url": base + "/telegram/link"}}],
        [{"text": "بازگشت", "callback_data": "studio:menu"}],
    ]


async def _edit_text(token, chat, message_id, text, buttons=None):
    body = {"chat_id": chat, "message_id": int(message_id), "text": text}
    if buttons is not None:
        body["reply_markup"] = {"inline_keyboard": buttons}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await _bot_call(client, token, "editMessageText", body)
    if not response.is_success and "message is not modified" not in response.text:
        raise HTTPException(502, "Telegram could not update the message")


async def _queue_reply(db, job_id, tg, account, text, service):
    data = {"tg": tg, "user": str(account.id), "text": text[:4000], "service": service}
    async with db.pipeline(transaction=True) as pipe:
        await pipe.set(PREFIX + "reply:" + job_id, json.dumps(data), ex=900).zadd(
            REPLIES, {job_id: time.time()}).execute()


async def _quick_text(user, text, history, on_text):
    from brain import lm_gateway
    messages = [
        {"role": "system", "content": "You are EditorGPT in Telegram. Answer briefly in the user's language. "
         "You can give advice, brainstorm and write text. You cannot start a Studio job or access the user's files here. "
         "Never claim you ran a tool or created a video. For video execution tell the user to use the Studio button."},
        *history, {"role": "user", "content": text},
    ]
    with lm_gateway.work_scope("telegram_reply", secrets.token_hex(12), user=user):
        stream = lm_gateway.stream_chat("general_chat", messages, tokens=650, timeout_seconds=35)
        result, last = "", 0.0
        try:
            while True:
                piece = await asyncio.to_thread(next, stream, None)
                if piece is None:
                    break
                result += piece
                now = time.monotonic()
                if now - last >= 1.4 and result.strip():
                    await on_text(result)
                    last = now
        finally:
            await asyncio.to_thread(stream.close)
    return result.strip()


async def _hermes_text(user, text, history):
    # The Hermes container uses the same EditorGPT auth store. Give the request a
    # short-lived access token for this authenticated user, only over the private network.
    access = auth.jwt.encode({"sub": user, "type": "access", "exp": time.time() + 90},
                             auth.jwt_secret(), algorithm=auth.JWT_ALGORITHM)
    async with httpx.AsyncClient(timeout=65) as client:
        response = await client.post(
            "http://hermes:8001/api/hermes/agent/chat",
            headers={"Authorization": "Bearer " + access, "Host": urlsplit(_config()[2]).hostname},
            json={"message": text, "history": [{"role": h["role"], "text": h["content"]} for h in history]},
        )
        response.raise_for_status()
        return str(response.json().get("reply") or "").strip()


async def _run_reply(db, token, job_id):
    key = PREFIX + "reply:" + job_id
    raw = await db.get(key)
    if not raw:
        await db.zrem(REPLIES, job_id)
        return
    job = json.loads(raw)
    tg, user, text, service = (job[name] for name in ("tg", "user", "text", "service"))
    if await db.get(PREFIX + f"tg:{tg}") != user:
        await db.zrem(REPLIES, job_id)
        await db.delete(key)
        return
    # Consume before calling a provider: a worker restart must not bill the same
    # quick answer twice. The user can send it again if the process was interrupted.
    await db.zrem(REPLIES, job_id)
    await db.delete(key)
    base = _config()[2]
    memory_key = PREFIX + f"reply-history:{tg}:{user}:{service}"
    history = json.loads(await db.get(memory_key) or "[]")
    buttons = ([[{"text": "📸 باز کردن InstaGPT", "web_app": {"url": base + "/insta"}},
                 {"text": "بازگشت به ادیتور", "callback_data": "studio:editor"}]]
               if service == "hermes" else
               [[{"text": "🎬 انجام همین درخواست در Studio", "callback_data": "studio:work:" + job_id}]])
    if service != "hermes":
        await db.set(PREFIX + "quick-work:" + job_id, json.dumps([tg, user, text]), ex=3600)
    message_id = await _send(token, tg, "هرمس در حال بررسی…" if service == "hermes" else "در حال پاسخ…")
    shown = ""

    async def update(answer):
        nonlocal shown
        if await db.get(PREFIX + f"tg:{tg}") != user:
            raise HTTPException(403, "Telegram account disconnected")
        answer = answer.strip()[:3900]
        if answer and shown != answer:
            try:
                await _edit_text(token, tg, message_id, answer)
                shown = answer
            except (HTTPException, httpx.HTTPError):
                pass  # Keep consuming the provider stream and retry on the final response.

    try:
        if service == "hermes":
            answer = await _hermes_text(user, text, history)
        else:
            from app import credits
            await credits.gate(user)
            answer = await _quick_text(user, text, history, update)
        if not answer:
            raise ValueError("empty answer")
        history = [*history, {"role": "user", "content": text[:1200]},
                   {"role": "assistant", "content": answer[:1600]}][-8:]
        await db.set(memory_key, json.dumps(history, ensure_ascii=False), ex=86400)
    except Exception as exc:
        log.warning("Telegram %s reply: %s", service, type(exc).__name__)
        if isinstance(exc, HTTPException) and exc.status_code == 403:
            return
        detail = exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, str) else None
        answer = (shown + "\n\nپاسخ کامل نشد." if shown else detail or "پاسخ آماده نشد. دوباره امتحان کنید.")
    if await db.get(PREFIX + f"tg:{tg}") != user:
        return
    try:
        await _edit_text(token, tg, message_id, answer[:3900], buttons)
    except (HTTPException, httpx.HTTPError):
        await _send(token, tg, answer[:3900], buttons=buttons)


@router.get("/media/{ticket}")
async def telegram_media(ticket: str):
    if len(ticket) != 43 or not all(c.isalnum() or c in "_-" for c in ticket):
        raise HTTPException(404)
    async with storage() as db:
        raw = await db.get(PREFIX + "media:" + hashlib.sha256(ticket.encode()).hexdigest())
    if not raw:
        raise HTTPException(404)
    path, _ = json.loads(raw)
    file = Path(path)
    if not file.is_file():
        raise HTTPException(404)
    return FileResponse(file, filename=file.name, media_type=mimetypes.guess_type(file.name)[0] or "application/octet-stream",
                        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"})


async def _media_url(db, path, kind):
    ticket = secrets.token_urlsafe(32)
    key = PREFIX + "media:" + hashlib.sha256(ticket.encode()).hexdigest()
    await db.set(key, json.dumps([str(path), kind]), ex=180)
    return _config()[2] + "/api/integrations/telegram/media/" + ticket


async def _send_file(token, chat, path, kind):
    kind = "video" if kind == "document" and path.suffix.lower() == ".mp4" else kind
    method = {"audio": "sendAudio", "photo": "sendPhoto", "video": "sendVideo", "document": "sendDocument"}[kind]
    if os.environ.get("EDITOR_TELEGRAM_BOT_RELAY_URL"):
        async with storage() as db:
            url = await _media_url(db, path, kind)
        try:
            async with httpx.AsyncClient(timeout=26) as client:
                result = await _bot_call(client, token, method, {
                    "chat_id": chat, kind: url})
            if result.is_success and result.json().get("ok"):
                return
        except (httpx.HTTPError, ValueError):
            pass
        raise HTTPException(502, "تلگرام فایل را دریافت نکرد. آن را در Studio باز کنید.")
    with path.open("rb") as file:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                result = await client.post(f"https://api.telegram.org/bot{token}/{method}",
                                           data={"chat_id": chat}, files={kind: (path.name, file)})
            if result.is_success and result.json().get("ok"):
                return
        except (httpx.HTTPError, ValueError):
            pass
    raise HTTPException(502, "ارسال فایل به تلگرام انجام نشد.")


async def _ingest(request, conversation, file, download):
    mime = str(file.get("mime_type") or "application/octet-stream")
    name = str(file.get("file_name") or "")
    if not studio.kind_of(name):
        import mimetypes
        extension = mimetypes.guess_extension(mime)
        if extension and studio.kind_of("media" + extension):
            name = "telegram" + extension
        elif mime.startswith("video/") or not name:
            name = "telegram.mp4"
    try:
        return await studio.upload_attachment(request, conversation, UploadFile(
            download, filename=name, headers=Headers({"content-type": mime})))
    except HTTPException as exc:
        original = exc.__context__
        log.warning("Telegram ingest rejected: status=%s, cause=%s, suffix=%s", exc.status_code,
                    type(original).__name__ if original else str(exc.detail)[:120], Path(name).suffix)
        raise


async def _attach(request, token, conversation_id, file):
    size = file.get("file_size", 0)
    limit = 20 * 1024**2
    if size > limit or (size and os.environ.get("EDITOR_TELEGRAM_DOWNLOAD_RELAY_URL")):
        return await _relay_download(request, conversation_id, file, size)
    async with httpx.AsyncClient(timeout=45) as client:
        try:
            meta = await _bot_call(client, token, "getFile", {"file_id": file["file_id"]})
            meta.raise_for_status()
            path = meta.json()["result"]["file_path"]
            url = f"https://api.telegram.org/file/bot{token}/" + quote(path, safe="/")
            with tempfile.TemporaryFile() as download:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    received = 0
                    async for block in response.aiter_bytes(128 * 1024):
                        received += len(block)
                        if received > limit:
                            raise HTTPException(413, "این فایل را از بخش آپلود Studio بفرستید.")
                        download.write(block)
                download.seek(0)
                return await _ingest(request, conversation_id, {**file, "file_name": file.get("file_name") or Path(path).name}, download)
        except (httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(502, "دریافت فایل تلگرام انجام نشد.")


EVENT_LABELS = {
    "plan.ready": "برنامه آماده شد", "question.required": "انتخاب شما",
    "motion.completed": "موشن آماده شد", "assistant.error": "خطا",
    "tool.started": "شروع", "tool.progress": "پیشرفت", "tool.completed": "پایان",
    "tool.failed": "خطا", "storyboard.ready": "استوری‌بورد", "render.started": "شروع رندر",
    "render.completed": "پایان رندر", "render.failed": "خطای رندر", "motion.progress": "موشن",
    "agent.thinking_summary": "بررسی", "agent.progress": "ایجنت", "work.state": "وضعیت",
}


def _activity(event):
    label = EVENT_LABELS.get(event["type"])
    data = event["data"]
    if not label or data.get("thinking") or event["type"] == "agent.thinking_summary":
        return None
    message = next((data[k] for k in ("message", "text", "stage") if isinstance(data.get(k), str) and data[k]), "")
    progress = data.get("progress")
    percent = f" · {progress}٪" if type(progress) in (int, float) and 0 <= progress <= 100 else ""
    message = " ".join(message.split())
    message = re.split(r"\s*\(موضوع\s*:", message, maxsplit=1)[0].strip()
    if message.rstrip(".…") in {"در حال کار", "دارم کار می‌کنم", "در حال پردازش"} and not percent:
        return None
    if len(message) > 82:
        message = message[:80].rsplit(" ", 1)[0] + "…"
    return f"{label} · {message}{percent}" if message or percent else None


async def _updates(request, db, token, tg, conversation):
    user = studio._user(request)
    cursor_key = PREFIX + f"cursor:{tg}:{user}:{conversation}"
    if await db.set(cursor_key + ":sync", "1", nx=True, ex=8):
        await studio.sync_conversation(conversation, user)
    after = int(await db.get(cursor_key) or 0)
    events = await studio.repo.events(conversation, user, after, limit=60)
    await _live_replies(db, token, tg, conversation, cursor_key, events)
    timeline_key = cursor_key + ":timeline"
    lines = json.loads(await db.get(timeline_key) or "[]")
    stopped_key = cursor_key + ":stopped"
    for event in events:
        kind, data, seq = event["type"], event["data"], event["seq"]
        if kind == "message.stopped":
            if data.get("stopped") != ["message"] or not await db.exists(stopped_key):
                await db.set(stopped_key, json.dumps(data), ex=30 * 86400)
        elif kind == "job.failed" and data.get("stopped") and data.get("motion_id"):
            await db.set(stopped_key, json.dumps(data), ex=30 * 86400)
        elif kind == "message.started" or (kind == "motion.progress" and data.get("status") == "completed"):
            await db.delete(stopped_key)
        if kind == "narration.ready" and type(data.get("event_seq")) is int:
            try:
                media = await studio.event_audio(request, conversation, data["event_seq"])
                await _send_file(token, tg, Path(media.path), "audio")
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
        elif kind == "plan.ready" and data.get("project_id") and data.get("version_id"):
            action = secrets.token_urlsafe(18)
            await db.set(PREFIX + "approve:" + action, json.dumps([tg, user, data["project_id"], data["version_id"]]), ex=86400)
            base = _config()[2]
            await _send(token, tg, "برنامه آمادهٔ بررسی است.", buttons=[
                [{"text": "دیدن برنامه", "web_app": {"url": base + "/studio/" + conversation}}],
                [{"text": "تأیید و شروع رندر", "callback_data": "studio:plan:" + action}],
            ])
            lines = [*lines, "برنامه آمادهٔ بررسی است"]
            await db.set(timeline_key, json.dumps(lines, ensure_ascii=False), ex=30 * 86400)
        elif kind == "question.required" and data.get("kind") == "medium_approval" and data.get("run_id"):
            action = secrets.token_urlsafe(18)
            await db.set(PREFIX + "agent-approval:" + action,
                         json.dumps([tg, user, conversation, data["run_id"]]), ex=86400)
            await _send(token, tg, str(data.get("question") or "ادامهٔ این کار به تأیید شما نیاز دارد.")[:3900],
                        buttons=[[{"text": "تأیید و ادامه", "callback_data": "studio:agent:" + action}]])
        elif kind == "question.required" and isinstance(data.get("choices"), list):
            choices = [choice for choice in data["choices"] if isinstance(choice, str) and choice.strip()][:8]
            if choices:
                buttons = []
                for choice in choices:
                    action = secrets.token_urlsafe(18)
                    await db.set(PREFIX + "choice:" + action, json.dumps([tg, user, conversation, choice]), ex=86400)
                    buttons.append([{"text": choice[:64], "callback_data": "studio:choice:" + action}])
                await _send(token, tg, str(data.get("question") or "یک گزینه را انتخاب کنید.")[:3900], buttons=buttons)
        elif kind == "render.completed" and data.get("project_id"):
            media = await _ready_asset(studio.project_output(request, data["project_id"]))
            await _output_media(db, token, tg, conversation, cursor_key, media, f"render:{data['project_id']}")
            line = _activity(event)
            if line and (not lines or lines[-1] != line):
                lines.append(line)
                await db.set(timeline_key, json.dumps(lines, ensure_ascii=False), ex=30 * 86400)
        elif kind == "assistant.response.completed":
            # The persisted messages below also include replies without streamed events.
            pass
        else:
            line = _activity(event)
            if line and (not lines or lines[-1] != line):
                if lines and kind in {"tool.progress", "motion.progress"} and line.endswith("٪") and lines[-1].endswith("٪") and lines[-1].rsplit(" · ", 1)[0] == line.rsplit(" · ", 1)[0]:
                    lines[-1] = line
                else:
                    lines.append(line)
                await db.set(timeline_key, json.dumps(lines, ensure_ascii=False), ex=30 * 86400)
        await db.set(cursor_key, seq, ex=30 * 86400)
    chat = await studio.repo.get_conversation(conversation, user)
    sent = 0
    for message in chat.get("messages", []):
        if message.get("role") != "assistant" or not (message.get("content") or message.get("attachments")):
            continue
        key = cursor_key + ":message:" + str(message["id"])
        pending_media = key + ":pending-media"
        if not await db.exists(key):
            if sent == 20:
                break
            text = message.get("content") or ""
            for start in range(0, len(text), 3900):
                await _send(token, tg, text[start:start + 3900])
            if message.get("attachments"):
                await db.set(pending_media, "1", ex=86400)
            await db.set(key, "1", ex=30 * 86400)
            sent += 1
        if message.get("attachments") and await db.exists(pending_media):
            if await _message_assets(request, db, token, tg, conversation, cursor_key, message):
                await db.delete(pending_media)
    active = await _work_active(chat, user)
    await db.set(cursor_key + ":active", "1" if active else "0", ex=120)
    if lines:
        stopped = not active and bool(await db.exists(stopped_key))
        control = "stop" if active else "resume" if stopped else None
        text = _timeline_text(lines, active=active, stopped=stopped)
        signature = json.dumps([text, control], ensure_ascii=False)
        delivered = cursor_key + ":timeline-delivered"
        if await db.get(delivered) != signature:
            await _timeline(db, token, tg, cursor_key, text, conversation, control)
            await db.set(delivered, signature, ex=30 * 86400)
    if (chat.get("state") or {}).get("motion"):
        await _motion_assets(request, db, token, tg, conversation, cursor_key)
    return len(events) + sent


async def _live_replies(db, token, tg, conversation, cursor_key, events):
    from app import studio_live
    watermark = cursor_key + ":live"
    # Live IDs are process-local. Replaying a still-live delta after reload is safe.
    final = {event["data"].get("response_id") for event in events if
             event["type"] in {"assistant.response.completed", "assistant.response.failed"}}
    for event in studio_live.since(conversation, 0):
        response_id = event["data"].get("response_id")
        visible = event["data"].get("text")
        if not response_id or response_id in final or not isinstance(visible, str) or not visible.strip():
            continue
        key = f"{watermark}:{response_id}"
        old = json.loads(await db.get(key) or "null")
        text = visible.strip()[:3900]
        if old and (len(old) > 2 or old[1] == text):
            continue
        try:
            message_id = old[0] if old else await _send(token, tg, text)
            if old:
                await _edit_text(token, tg, old[0], text)
            await db.set(key, json.dumps([message_id, text]), ex=3600)
        except (HTTPException, httpx.HTTPError):
            log.warning("Telegram could not update Studio's live reply")
    for event in events:
        if event["type"] not in {"assistant.response.completed", "assistant.response.failed"}:
            continue
        data = event["data"]
        response_id = data.get("response_id")
        if not response_id:
            continue
        key = f"{watermark}:{response_id}"
        old = json.loads(await db.get(key) or "null")
        if not old:
            await db.set(key, json.dumps([None, "", "done"]), ex=3600)
            continue
        if len(old) > 2:
            continue
        text = str(data.get("text") or "").strip() or old[1] + "\n\nپاسخ کامل نشد."
        try:
            await _edit_text(token, tg, old[0], text[:3900])
            for offset in range(3900, len(text), 3900):
                await _send(token, tg, text[offset:offset + 3900])
            if data.get("message_id"):
                message_key = cursor_key + ":message:" + str(data["message_id"])
                if data.get("attachments"):
                    await db.set(message_key + ":pending-media", "1", ex=86400)
                await db.set(message_key, "1", ex=30 * 86400)
            # Keep the last live text until it ages out, so a completed delta
            # cannot recreate the card on the next polling cycle.
            await db.set(key, json.dumps([old[0], text[:3900], "done"]), ex=3600)
        except (HTTPException, httpx.HTTPError):
            log.warning("Telegram could not finalize Studio's live reply")


async def _message_assets(request, db, token, tg, conversation, cursor_key, message):
    photos = []
    complete = True
    for attachment_id in message["attachments"]:
        media = await _ready_asset(studio.get_attachment(request, conversation, attachment_id))
        if media is None:
            continue
        path = Path(media.path)
        if media.media_type in {"image/jpeg", "image/png"}:
            key = _asset_key(cursor_key, conversation, attachment_id, path)
            if not await db.exists(key):
                photos.append((key, path))
        elif path.stat().st_size <= 50_000_000:
            kind = "audio" if (media.media_type or "").startswith("audio/") else "document"
            key = _asset_key(cursor_key, conversation, attachment_id, path)
            if not await db.exists(key):
                complete = (await _deliver_motion_asset(db, token, tg, cursor_key, conversation, kind, media, attachment_id)
                            and complete)
        else:
            key = cursor_key + ":large:" + attachment_id
            if not await db.exists(key):
                await _send(token, tg, "فایل آماده است. برای دریافت فایل حجیم آن را در Studio باز کنید.", buttons=[
                    [{"text": "باز کردن Studio", "web_app": {"url": _config()[2] + "/studio/" + conversation}}]])
                await db.set(key, "1", ex=30 * 86400)
    return await _send_albums(db, token, tg, photos) and complete


async def _motion_assets(request, db, token, tg, conversation, cursor_key):
    try:
        motion = (await studio.conversation_motion(request, conversation))["motion"]
    except (HTTPException, KeyError, OSError, ValueError):
        return
    if not motion:
        return
    motion_id = motion["id"]
    # Use the same ownership-checked files displayed in Studio.
    voice = await _ready_asset(studio.motion_media(request, motion_id, "voice"))
    await _deliver_motion_asset(db, token, tg, cursor_key, motion_id, "audio", voice, "voice")
    # Both engines can publish draft snapshots during visual review and replace them
    # before rendering. Deliver that settled set as one album when it fits.
    if motion["status"] not in {"rendering", "completed"}:
        return
    pending = []
    for shot in motion.get("snapshots") or []:
        n = shot["n"]
        media = await _ready_asset(studio.motion_snapshot(request, motion_id, n))
        if media is None:
            return  # Wait for the published snapshot set to be readable.
        path = Path(media.path)
        try:
            key = _asset_key(cursor_key, motion_id, f"snapshot:{n}", path)
        except OSError:
            return
        if not await db.exists(key):
            pending.append((key, path))

    await _send_albums(db, token, tg, pending)
    if motion["status"] == "completed" and motion.get("current"):
        version = motion["current"]
        media = await _ready_asset(studio.motion_media(request, motion_id, "video", version))
        await _output_media(db, token, tg, conversation, cursor_key, media, f"motion:{motion_id}:{version}")


async def _output_media(db, token, tg, conversation, cursor_key, media, label):
    if media is None:
        return
    path = Path(media.path)
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size <= 50_000_000:
        await _deliver_motion_asset(db, token, tg, cursor_key, conversation, "document", media, label)
        return
    key = cursor_key + ":large:" + label
    if not await db.exists(key):
        await _send(token, tg, "ویدیو آماده است. فایل حجیم را از پیش‌نمایش Studio بگیرید.", buttons=[
            [{"text": "مشاهده و دانلود", "web_app": {"url": _config()[2] + "/studio/" + conversation}}]])
        await db.set(key, "1", ex=30 * 86400)


async def _send_albums(db, token, tg, pending):
    while pending:
        # Telegram albums accept 2–10 items. Avoid leaving a singleton tail.
        size = 9 if len(pending) == 11 else 10
        batch, pending = pending[:size], pending[size:]
        keys, paths = zip(*batch)
        retry_key = keys[0] + ":retry"
        if not await db.set(retry_key, "1", nx=True, ex=60):
            return False
        try:
            if len(paths) == 1:
                await _send_file(token, tg, paths[0], "photo")
            else:
                media = [{"type": "photo", "media": await _media_url(db, path, "photo")} for path in paths]
                async with httpx.AsyncClient(timeout=26) as client:
                    result = await _bot_call(client, token, "sendMediaGroup", {"chat_id": tg, "media": media})
                if not result.is_success or not result.json().get("ok"):
                    raise HTTPException(502, "Telegram album delivery failed")
        except (HTTPException, httpx.HTTPError, OSError, ValueError) as exc:
            log.warning("Telegram snapshot album delivery: %s", type(exc).__name__)
            return False
        async with db.pipeline(transaction=True) as pipe:
            for key in keys:
                pipe.set(key, "1", ex=30 * 86400)
            await pipe.execute()
    return True


def _asset_key(cursor_key, motion_id, label, path):
    stamp = path.stat()
    return f"{cursor_key}:asset:{motion_id}:{label}:{stamp.st_mtime_ns}:{stamp.st_size}"


async def _ready_asset(endpoint):
    try:
        return await endpoint
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return None


async def _deliver_motion_asset(db, token, tg, cursor_key, motion_id, kind, media, label):
    if media is None:
        return False
    path = Path(media.path)
    try:
        key = _asset_key(cursor_key, motion_id, label, path)
        if await db.exists(key):
            return False
        cooldown = key + ":retry"
        if not await db.set(cooldown, "1", nx=True, ex=60):
            return False
        await _send_file(token, tg, path, kind)
        await db.set(key, "1", ex=30 * 86400)
        return True
    except (HTTPException, OSError) as exc:
        log.warning("Telegram motion asset delivery: %s", type(exc).__name__)
        return False


async def _work_active(chat, user):
    from app.studio_orchestrator import conversation_busy
    if await asyncio.to_thread(conversation_busy, chat, user):
        return True
    if any(p.get("status") in {"queued", "running"} for p in chat.get("projects", [])):
        return True
    from app.agents import store
    return any(r["agent_mode"] in {"medium", "pro"} and r["status"] in {"queued", "running", "waiting_job"}
               for r in await store.runs(chat["id"], user))


async def _workflow_control(request, db, token, tg, action):
    _, control, conversation = action.split(":")
    user = studio._user(request)
    key = PREFIX + f"cursor:{tg}:{user}:{conversation}:stopped"
    try:
        async with db.lock(PREFIX + "control-lock:" + conversation, timeout=120, blocking_timeout=0):
            chat = await studio.repo.get_conversation(conversation, user)
            active = await _work_active(chat, user)
            if control == "stop" and active:
                await studio.stop_conversation(request, conversation)
            elif control == "resume" and not active:
                raw = await db.get(key)
                if not raw:
                    return
                stopped = json.loads(raw)
                if stopped.get("motion_id"):
                    await studio.motion_retry(request, stopped["motion_id"])
                elif stopped.get("analysis_id"):
                    await studio.discovery_resume(request, stopped["analysis_id"])
                elif "project" in stopped.get("stopped", []):
                    await studio.resume_stopped_project(request, chat["state"]["current_project_id"], studio.ResumeRequest(retry_confirmed=True))
                else:
                    previous = next((m for m in reversed(chat["messages"]) if m["role"] == "user"), None)
                    if previous is None:
                        return
                    await studio.send_message(request, conversation, studio.MessageCreate(
                        content=previous["content"], attachment_ids=previous.get("attachments") or [],
                        render_target="server", agent_mode=previous.get("agent_mode")))
                await db.delete(key)
            await db.zadd(WATCH, {json.dumps([tg, user, conversation]): time.time()})
    except KeyError:
        await _send(token, tg, "گفتگو یا اجرای قبلی پیدا نشد.")
    except HTTPException as exc:
        await _send(token, tg, str(exc.detail)[:500])
    except RuntimeError:
        await _send(token, tg, "وضعیت کار تغییر کرده است. کارت روند به‌روز می‌شود.")


def _timeline_text(lines, *, active=False, stopped=False):
    current, _, value = lines[-1].rpartition(" · ")
    percent = re.fullmatch(r"([0-9]{1,3})(?:\.([0-9]+))?٪", value)
    progress = float(value[:-1]) if percent else None
    if progress is None:
        current = lines[-1]
    stage = current.partition(" · ")[2] or current
    label = current.partition(" · ")[0]
    heading = ("⚙️ <b>در حال انجام</b>" if active else "⚠️ <b>نیاز به بررسی</b>" if label == "خطا" else "📋 <b>روند کار</b>")
    if stopped:
        heading = "⏸ <b>متوقف شد</b>"
        progress = None
    rows = [heading, ("🔹 " if active else "") + "<b>" + escape(stage[:105]) + "</b>"]
    if progress is not None and 0 <= progress <= 100:
        filled = int(progress // 10)
        rows.append(f"▫️ <code>{'━' * filled}{'─' * (10 - filled)}</code>  <b>{progress:g}٪</b>")
    recent = list(dict.fromkeys(reversed(lines[:-1])))
    recent = [line for line in recent if (line.partition(" · ")[2] or line).rsplit(" · ", 1)[0] != stage]
    if recent:
        rows.extend(["", "<b>پیش از این</b>"])
        for line in reversed(recent[:2]):
            kind, _, detail = line.partition(" · ")
            detail = re.sub(r"\s*·\s*\d+(?:\.\d+)?٪$", "", detail or kind)
            rows.append(("✓ " if kind in {"پایان", "پایان رندر"} else "• ") + escape(detail[:90]))
    return "\n".join(rows)


async def _timeline(db, token, tg, key, text, conversation, control=None):
    markup = {"inline_keyboard": [[{"text": "تاریخچه در Studio", "web_app": {"url": _config()[2] + "/studio/" + conversation}}]]}
    if control:
        label = "⏹ توقف" if control == "stop" else "▶️ ادامه"
        markup["inline_keyboard"].insert(0, [{"text": label, "callback_data": f"studio:{control}:{conversation}"}])
    message_id = await db.get(key + ":telegram")
    async with httpx.AsyncClient(timeout=15) as client:
        if message_id:
            response = await _bot_call(client, token, "editMessageText", {"chat_id": tg, "message_id": int(message_id), "text": text, "parse_mode": "HTML", "reply_markup": markup})
            if response.is_success or "message is not modified" in response.text:
                return
            if response.status_code != 400:
                response.raise_for_status()
        response = await _bot_call(client, token, "sendMessage", {"chat_id": tg, "text": text, "parse_mode": "HTML", "reply_markup": markup})
        response.raise_for_status()
        await db.set(key + ":telegram", response.json()["result"]["message_id"], ex=30 * 86400)


async def _run_upload(db, token, job_id):
    raw = await db.get(PREFIX + "file:" + job_id)
    if not raw:
        await db.zrem(WORK, job_id)
        return
    job = json.loads(raw)
    tg, user = job["tg"], job["user"]
    if await db.get(PREFIX + f"tg:{tg}") != user:
        await db.zrem(WORK, job_id)
        return
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id=user)))
    from brain.lm_gateway import user_context
    ctx = user_context.set(user)
    try:
        attachment_id = job.get("attachment_id")
        if not attachment_id:
            attachment_id = (await _attach(request, token, job["conversation"], job["file"]))["id"]
            job["attachment_id"] = attachment_id
            await db.set(PREFIX + "file:" + job_id, json.dumps(job), ex=86400)
        if job["content"]:
            await studio.send_message(request, job["conversation"], studio.MessageCreate(
                content=job["content"], attachment_ids=[attachment_id], render_target="server", agent_mode=job["mode"]))
        else:
            await db.set(PREFIX + "draft-file:" + job["conversation"], attachment_id, ex=86400)
    except HTTPException as exc:
        log.warning("Telegram file rejected: %s (%s)", exc.status_code, str(exc.detail)[:120])
        await _send(token, tg, str(exc.detail)[:500])
    else:
        await _send(token, tg, "فایل به گفتگو اضافه شد. روند کار همین‌جا نمایش داده می‌شود."
                    if job["content"] else "فایل دریافت شد. بگو می‌خواهی با این فایل چه کاری انجام بدهم.")
    finally:
        user_context.reset(ctx)
    await db.zrem(WORK, job_id)
    await db.expire(PREFIX + "file:" + job_id, 900)


async def telegram_loop():
    if not os.environ.get("EDITOR_TELEGRAM_BOT_TOKEN"):
        return
    token, _, _ = _config()
    from app import studio_live
    studio_live.start_listener()

    async def transfer():
        while True:
            try:
                async with storage() as db:
                    for job_id in await db.zrangebyscore(WORK, 0, time.time(), start=0, num=1):
                        async with db.lock(PREFIX + "file-lock:" + job_id, timeout=900, blocking_timeout=0) as lock:
                            upload = asyncio.create_task(_run_upload(db, token, job_id))
                            try:
                                while not upload.done():
                                    await asyncio.wait({upload}, timeout=60)
                                    if not upload.done():
                                        await lock.extend(900, replace_ttl=True)
                                await upload
                            finally:
                                if not upload.done():
                                    upload.cancel()
            except Exception as exc:
                log.warning("Telegram upload worker: %s", type(exc).__name__)
                await asyncio.sleep(8)
            await asyncio.sleep(2)

    async def replies():
        while True:
            try:
                async with storage() as db:
                    ready = await db.zrangebyscore(REPLIES, 0, time.time(), start=0, num=4)

                    async def deliver(job_id):
                        try:
                            async with db.lock(PREFIX + "reply-lock:" + job_id, timeout=300, blocking_timeout=0):
                                await _run_reply(db, token, job_id)
                        except Exception as exc:
                            if type(exc).__name__ != "LockError":
                                log.warning("Telegram reply worker: %s", type(exc).__name__)

                    await asyncio.gather(*(deliver(job_id) for job_id in ready))
            except Exception as exc:
                log.warning("Telegram reply queue: %s", type(exc).__name__)
            await asyncio.sleep(0.5)

    async def monitor():
        while True:
            try:
                async with storage() as db:
                    now = time.time()
                    for entry in await db.zrangebyscore(WATCH, 0, now, start=0, num=12):
                        tg, user, conversation = json.loads(entry)
                        if await db.get(PREFIX + f"tg:{tg}") != user:
                            await db.zrem(WATCH, entry)
                            continue
                        try:
                            async with db.lock(PREFIX + "watch-lock:" + conversation, timeout=120, blocking_timeout=0):
                                due = await db.zscore(WATCH, entry)
                                if due is None or due > time.time():
                                    continue
                                await db.zadd(WATCH, {entry: time.time() + 4})
                                request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id=user)))
                                count = await asyncio.wait_for(_updates(request, db, token, tg, conversation), timeout=110)
                                active_key = PREFIX + f"cursor:{tg}:{user}:{conversation}:active"
                                if not count and await db.get(active_key) == "0":
                                    await db.zadd(WATCH, {entry: time.time() + 25}, xx=True, gt=True)
                        except KeyError:
                            await db.zrem(WATCH, entry)
                        except Exception as exc:
                            if type(exc).__name__ != "LockError":
                                log.warning("Telegram timeline delivery: %s", type(exc).__name__)
            except Exception as exc:
                log.warning("Telegram timeline worker: %s", type(exc).__name__)
            await asyncio.sleep(1)

    await asyncio.gather(transfer(), monitor(), replies())


def _private_message(update):
    callback = update.get("callback_query") or {}
    message = callback.get("message") or update.get("message") or {}
    sender, chat = (callback.get("from") if callback else message.get("from")) or {}, message.get("chat") or {}
    user_id = sender.get("id")
    if chat.get("type") == "private" and type(user_id) is int and user_id == chat.get("id") and not sender.get("is_bot"):
        return user_id, message
    return None, {}


REFERENCE_CHOICES = {
    "فقط محتوا": "محتوا و ساختار روایت",
    "فقط استایل": "سبک بصری، ریتم تدوین و موشن",
    "محتوا و استایل": "هم محتوا و هم سبک بصری و تدوین",
}


@router.post("/webhook")
async def webhook(request: Request):
    token, expected, base = _config()
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(expected.encode(), supplied.encode()):
        raise HTTPException(403, "Invalid Telegram webhook")
    update = await request.json()
    if not isinstance(update, dict):
        raise HTTPException(400, "Invalid Telegram update")
    tg, message = _private_message(update)
    update_id = update.get("update_id")
    if tg is None or type(update_id) is not int:
        return {"ok": True}
    callback = update.get("callback_query")
    force_work = False
    if callback:
        action = str(callback.get("data") or "")
        if not re.fullmatch(r"studio:(stop|resume):[a-f0-9]{32}", action) and not action.startswith(("studio:plan:", "studio:choice:", "studio:work:", "studio:agent:")) and action not in {"studio:" + x for x in ("new", "updates", "output", "cancel", "approve", "lite", "medium", "pro", "settings", "menu", "hermes", "editor", "ref-content", "ref-style", "ref-both", "product", "explainer")}:
            return {"ok": True}
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                await _bot_call(client, token, "answerCallbackQuery", {"callback_query_id": callback["id"]})
            except httpx.HTTPError:
                pass
        text = {"studio:ref-content": "فقط محتوا", "studio:ref-style": "فقط استایل",
                "studio:ref-both": "محتوا و استایل"}.get(action, "/" + action.split(":")[1])
        message = {}
    else:
        text = str(message.get("text") or message.get("caption") or "").strip()
    command = text.split(maxsplit=1)[0].split("@")[0] if text.startswith("/") else ""
    keyboard = _menu(base)
    attachment = message.get("video") or message.get("document") or message.get("audio")
    if not attachment and message.get("photo"):
        attachment = {**message["photo"][-1], "file_name": "telegram-photo.jpg", "mime_type": "image/jpeg"}
    if not attachment and message.get("voice"):
        attachment = {**message["voice"], "file_name": "telegram-voice.ogg", "mime_type": "audio/ogg"}
    async with storage() as db:
        claim = PREFIX + f"update:{update_id}"
        if not await db.set(claim, "1", nx=True, ex=172800):
            return {"ok": True}
        account = await db.get(PREFIX + f"tg:{tg}")
        user = await auth.db_get_user_by_id(account) if account and auth.USE_DB else auth._find_by_id(account) if account else None
        if not user or not getattr(user, "is_active", True):
            code = secrets.token_urlsafe(24)
            await db.set(_key(code), str(tg), ex=PAIR_TTL)
            await _send(token, tg, "برای اتصال، وارد حساب EditorGPT شوید و اتصال را تأیید کنید.",
                        buttons=[[{"text": "اتصال حساب", "url": base + "/telegram/link?code=" + code}]])
            return {"ok": True}
        chat_key = PREFIX + f"chat:{tg}"
        conversation_id = await db.get(chat_key)
        request.state.user = user
        draft_key = PREFIX + f"reference:{tg}:{user.id}"
        service_key = PREFIX + f"service:{tg}:{user.id}"
        source_key = PREFIX + f"source:{tg}:{user.id}"
        file_draft_key = PREFIX + f"pending-attachment:{tg}:{user.id}"
        from app.agents.store import preference

        if command in {"/start", "/menu", "/editor", "/hermes", "/settings"}:
            if command == "/start":
                await db.set(service_key, "editor")
            if command in {"/editor", "/hermes"}:
                await db.set(service_key, "hermes" if command == "/hermes" else "editor")
            if command == "/settings":
                mode = await preference(str(user.id))
                await _send(token, tg, "موتور پیش‌فرض Studio را انتخاب کنید. این تنظیم در وب هم اعمال می‌شود.",
                            buttons=_settings_menu(base, mode))
            elif command == "/hermes":
                await _send(token, tg, "سؤالتان دربارهٔ اینستاگرام را بفرستید.", buttons=[
                    [{"text": "📸 باز کردن InstaGPT", "web_app": {"url": base + "/insta"}},
                     {"text": "بازگشت به ادیتور", "callback_data": "studio:editor"}]])
            else:
                await _send(token, tg, "سؤال بپرسید یا درخواست ساخت و تدوین بفرستید.", buttons=_menu(base, conversation_id))
            return {"ok": True}

        if callback and action.startswith("studio:work:"):
            work_key = PREFIX + "quick-work:" + action.removeprefix("studio:work:")
            raw = await db.get(work_key)
            option = json.loads(raw) if raw else []
            if option[:2] != [tg, str(user.id)]:
                await _send(token, tg, "این دکمه منقضی شده است. درخواست را دوباره بفرستید.")
                return {"ok": True}
            if not await db.getdel(work_key):
                return {"ok": True}
            text, command, force_work = option[2], "", True
        if callback and re.fullmatch(r"studio:(stop|resume):[a-f0-9]{32}", action):
            await _workflow_control(request, db, token, tg, action)
            return {"ok": True}
        if callback and action.startswith("studio:choice:"):
            raw = await db.get(PREFIX + "choice:" + action.removeprefix("studio:choice:"))
            option = json.loads(raw) if raw else []
            if option[:3] != [tg, str(user.id), conversation_id]:
                await _send(token, tg, "این انتخاب دیگر برای گفتگوی فعلی معتبر نیست.")
                return {"ok": True}
            text, command, force_work = option[3], "", True

        if callback and action.startswith("studio:agent:"):
            approval_key = PREFIX + "agent-approval:" + action.removeprefix("studio:agent:")
            raw = await db.get(approval_key)
            details = json.loads(raw) if raw else []
            if len(details) != 4 or details[:2] != [tg, str(user.id)]:
                await _send(token, tg, "این دکمه منقضی شده است. همان گفتگو را در Studio باز کنید.")
                return {"ok": True}
            try:
                await studio.resume_agent(request, details[3], studio.AgentResume(decision="approve"))
            except HTTPException as exc:
                await _send(token, tg, str(exc.detail)[:500])
            else:
                await db.delete(approval_key)
                await db.zadd(WATCH, {json.dumps([tg, str(user.id), details[2]]): time.time()})
                await _send(token, tg, "تأیید شد. کار ادامه دارد.")
            return {"ok": True}

        if callback and action.startswith("studio:plan:"):
            raw = await db.get(PREFIX + "approve:" + action.removeprefix("studio:plan:"))
            details = json.loads(raw) if raw else []
            if details[:2] != [tg, str(user.id)]:
                await _send(token, tg, "این دکمه منقضی شده است. برنامه را در Studio باز کنید.")
                return {"ok": True}
            try:
                await studio.approve_project_plan(request, details[2], studio.PlanApproval(version_id=details[3]))
            except HTTPException as exc:
                await _send(token, tg, str(exc.detail)[:500])
            else:
                await db.delete(PREFIX + "approve:" + action.removeprefix("studio:plan:"))
                await _send(token, tg, "برنامه تأیید شد.")
        elif callback and command.removeprefix("/") in MODES:
            mode = await preference(str(user.id), command.removeprefix("/"))
            if conversation_id:
                try:
                    await studio.update_conversation(request, conversation_id, studio.ConversationUpdate(agent_mode=mode))
                except (KeyError, HTTPException):
                    pass
            await _edit_text(token, tg, callback["message"]["message_id"],
                             f"موتور پیش‌فرض Studio: {MODES[mode]}", _settings_menu(base, mode))
        elif command in {"/updates", "/output"} and conversation_id:
            try:
                if command == "/updates":
                    count = await _updates(request, db, token, tg, conversation_id)
                    if not count:
                        await _send(token, tg, "رویداد تازه‌ای نیست.", buttons=_menu(base, conversation_id))
                else:
                    chat = await studio.get_conversation(request, conversation_id, messages=1)
                    project = next((p for p in reversed(chat["projects"]) if p["status"] == "done"), None)
                    if not project:
                        raise HTTPException(409, "خروجی آماده‌ای پیدا نشد.")
                    result = await studio.project_output(request, project["id"])
                    path = Path(getattr(result, "path", ""))
                    if not path.is_file() or path.stat().st_size > 50_000_000:
                        await _send(token, tg, "خروجی را از تب پیش‌نمایش Studio بگیرید.", buttons=_menu(base, conversation_id))
                    else:
                        await _send_file(token, tg, path, "document")
            except (KeyError, HTTPException) as exc:
                await _send(token, tg, str(getattr(exc, "detail", "گفتگو پیدا نشد."))[:500],
                            buttons=_menu(base, conversation_id))
        elif command == "/new":
            await db.delete(draft_key, file_draft_key, source_key, chat_key)
            await db.set(service_key, "editor")
            await _send(token, tg, "درخواست پروژهٔ جدید را بفرستید.", buttons=keyboard)
        elif command in {"/approve", "/cancel"} and conversation_id:
            try:
                chat = await studio.get_conversation(request, conversation_id, messages=1)
                project_id = chat["state"].get("current_project_id")
                project = next((p for p in chat["projects"] if p["id"] == project_id), None)
                if not project:
                    raise HTTPException(409, "پروژهٔ فعالی وجود ندارد.")
                if command == "/cancel":
                    await studio.cancel_running_project(request, project_id)
                    await _send(token, tg, "درخواست توقف ثبت شد.", buttons=_menu(base, conversation_id))
                else:
                    # Require the explicit version displayed in Studio; a newer plan must never be approved by an old message.
                    version = text.partition(" ")[2].strip()
                    if not 8 <= len(version) <= 64:
                        await _send(token, tg, "برنامهٔ دقیق را از Studio بررسی و تأیید کنید.", buttons=_menu(base, conversation_id))
                    else:
                        await studio.approve_project_plan(request, project_id, studio.PlanApproval(version_id=version))
                        await _send(token, tg, "تأیید همین نسخه ثبت شد.", buttons=_menu(base, conversation_id))
            except HTTPException as exc:
                await _send(token, tg, str(exc.detail)[:500], buttons=_menu(base, conversation_id))
        elif command == "/status" and conversation_id:
            try:
                chat = await studio.repo.get_conversation(conversation_id, str(user.id))
            except KeyError:
                await db.delete(chat_key)
                await _send(token, tg, "گفتگو پیدا نشد. یک درخواست جدید بفرستید.", buttons=keyboard)
                return {"ok": True}
            latest = next((m.get("content") for m in reversed(chat.get("messages", [])) if m.get("role") == "assistant"), None)
            await _send(token, tg, (latest or "هنوز پاسخی ثبت نشده است.")[:3800],
                        buttons=[[{"text": "مشاهده و تأیید در Studio", "web_app": {"url": base + "/studio/" + conversation_id}}]])
        elif (command and command not in ("/lite", "/medium", "/pro", "/product", "/explainer")) or (not text and not attachment):
            await _send(token, tg, "متن، لینک یا فایل را بفرستید یا یکی از دکمه‌ها را انتخاب کنید.",
                        buttons=keyboard)
        else:
            mode, _, content = text.partition(" ") if command else ("", "", text)
            service = await db.get(service_key) or "editor"
            if callback and command in {"/product", "/explainer"}:
                source = await db.getdel(source_key)
                if not source:
                    await _send(token, tg, "لینک منبع را دوباره بفرستید.")
                    return {"ok": True}
                mode, force_work = "", True
                brief = ("از این صفحه ویدیوی معرفی محصول بساز" if command == "/product"
                         else "از محتوای این صفحه یک ویدیوی توضیحی بساز")
                content = brief + ": " + source
            if not content.strip() and not attachment:
                await _send(token, tg, "درخواستتان را بعد از نام موتور بنویسید.", buttons=keyboard)
                return {"ok": True}
            if text in REFERENCE_CHOICES:
                reference = await db.getdel(draft_key)
                if not reference:
                    await _send(token, tg, "لینک رفرنس را دوباره بفرستید.", buttons=keyboard)
                    return {"ok": True}
                force_work = True
                content = f"با این رفرنس یک ویدیوی تازه بساز. فقط از نقش انتخاب‌شده برای رفرنس استفاده کن: {REFERENCE_CHOICES[text]}.\n{reference}"
            elif service == "editor" and not attachment and not command and text.startswith(("https://www.instagram.com/", "https://instagram.com/")) and len(text.split()) == 1:
                await db.set(draft_key, text, ex=900)
                await _send(token, tg, "این رفرنس را برای چه چیزی استفاده کنم؟", buttons=[[
                    {"text": label, "callback_data": "studio:ref-" + action}
                    for label, action in zip(REFERENCE_CHOICES, ("content", "style", "both"))
                ]])
                return {"ok": True}
            pending_file = await db.get(file_draft_key)
            if attachment and not content.strip():
                await db.set(file_draft_key, json.dumps(attachment), ex=1800)
                await _send(token, tg, "فایل دریافت شد. بگویید با آن چه کار کنم.")
                return {"ok": True}
            if service == "editor" and not attachment and not force_work and re.fullmatch(r"https?://[^\s]+", content):
                await db.set(source_key, content, ex=900)
                await _send(token, tg, "از این لینک چه ویدیویی بسازم؟", buttons=[[
                    {"text": "معرفی محصول", "callback_data": "studio:product"},
                    {"text": "ویدیوی توضیحی", "callback_data": "studio:explainer"}]])
                return {"ok": True}
            if not (pending_file or attachment or force_work or mode):
                if service == "hermes" or not _starts_work(content):
                    await _queue_reply(db, str(update_id), tg, user, content, service)
                    return {"ok": True}
            if pending_file and not attachment:
                attachment = json.loads(pending_file)
            if not command and not callback and (source := await db.get(source_key)):
                content = content + "\n" + source
                await db.delete(source_key)
            from brain.lm_gateway import user_context
            context = user_context.set(str(user.id))
            try:
                mode = command.removeprefix("/") if mode else None
                if attachment or not conversation_id:
                    mode = mode or await preference(str(user.id))
                    from app import credits
                    from app.agents.dispatcher import ensure_available
                    await credits.gate(str(user.id))
                    try:
                        ensure_available(mode)
                    except ValueError as exc:
                        raise HTTPException(503, str(exc)) from exc
                    chat = await studio.create_conversation(request, studio.ConversationCreate())
                    conversation_id = chat["id"]
                    await db.set(chat_key, conversation_id)
                watch = json.dumps([tg, str(user.id), conversation_id])
                if attachment:
                    await db.zadd(WATCH, {watch: time.time() + 3})
                    job = {"tg": tg, "user": str(user.id), "conversation": conversation_id,
                           "file": attachment, "content": content[:12000], "mode": mode}
                    async with db.pipeline(transaction=True) as pipe:
                        await pipe.set(PREFIX + "file:" + str(update_id), json.dumps(job), ex=86400).zadd(
                            WORK, {str(update_id): time.time()}).execute()
                    await db.delete(file_draft_key)
                    await _send(token, tg, "فایل در صف دریافت است. روند کار همین‌جا نمایش داده می‌شود.")
                    return {"ok": True}
                draft = PREFIX + "draft-file:" + conversation_id
                attachment_id = await db.get(draft)
                await studio.send_message(request, conversation_id, studio.MessageCreate(
                    content=content[:12000], attachment_ids=[attachment_id] if attachment_id else [],
                    render_target="server", agent_mode=mode))
                if attachment_id:
                    await db.delete(draft)
            except HTTPException as exc:
                await _send(token, tg, str(exc.detail)[:500], buttons=keyboard)
                return {"ok": True}
            finally:
                user_context.reset(context)
            try:
                await _send(token, tg, "درخواست Studio ثبت شد. روند کار همین‌جا می‌آید.",
                            buttons=[[{"text": "مشاهدهٔ گفتگو", "web_app": {"url": base + "/studio/" + conversation_id}}]])
            finally:
                await db.zadd(WATCH, {watch: time.time()})
    return {"ok": True}
