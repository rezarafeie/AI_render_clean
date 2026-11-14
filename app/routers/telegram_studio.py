"""Telegram identity linking and a thin adapter to the existing Studio API."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path
from urllib.parse import quote

from starlette.datastructures import UploadFile
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


@router.post("/link")
async def link(request: Request, body: Pair):
    token, _, base = _config()
    async with storage() as db:
        result = await db.eval(PAIR_SCRIPT, 1, _key(body.code), str(request.state.user.id), PREFIX)
    if not result or result == -1:
        raise HTTPException(409, "کد منقضی شده یا یکی از حساب‌ها قبلاً متصل است.")
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
        return await studio.upload_attachment(request, conversation_id, UploadFile(
            download, filename=file.get("file_name") or "telegram-video.mp4"))


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
            return
    except (httpx.HTTPError, ValueError):
        pass
    raise HTTPException(502, "Telegram could not deliver the message")


def _menu(base, conversation=None):
    def launch(label, path):
        return {"text": label, "web_app": {"url": base + path}}
    return [
        [launch("EditorGPT", "/studio" + ("/" + conversation if conversation else "")), launch("InstaGPT", "/hermes")],
        [launch("پروژه‌ها", "/projects"), launch("کتابخانه", "/library"), launch("تنظیمات", "/settings")],
        [{"text": "گفتگوی جدید", "callback_data": "studio:new"}, {"text": "مراحل و نریشن", "callback_data": "studio:updates"}],
        [{"text": "دریافت خروجی", "callback_data": "studio:output"}, {"text": "توقف", "callback_data": "studio:cancel"}],
        [{"text": "EditorGPT Lite", "callback_data": "studio:lite"}, {"text": "EditorGPT Medium", "callback_data": "studio:medium"}],
        [{"text": "بررسی برنامه", "callback_data": "studio:approve"}],
    ]


@router.get("/media/{ticket}")
async def telegram_media(ticket: str):
    if len(ticket) != 43 or not all(c.isalnum() or c in "_-" for c in ticket):
        raise HTTPException(404)
    async with storage() as db:
        raw = await db.get(PREFIX + "media:" + hashlib.sha256(ticket.encode()).hexdigest())
    if not raw:
        raise HTTPException(404)
    path, kind = json.loads(raw)
    file = Path(path)
    if not file.is_file():
        raise HTTPException(404)
    return FileResponse(file, filename=file.name, media_type="audio/mpeg" if kind == "audio" else "video/mp4" if kind == "video" else "application/octet-stream",
                        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"})


async def _send_file(token, chat, path, kind):
    method = "sendAudio" if kind == "audio" else "sendVideo" if path.suffix.lower() == ".mp4" else "sendDocument"
    kind = "video" if method == "sendVideo" else kind
    if os.environ.get("EDITOR_TELEGRAM_BOT_RELAY_URL"):
        ticket = secrets.token_urlsafe(32)
        key = PREFIX + "media:" + hashlib.sha256(ticket.encode()).hexdigest()
        async with storage() as db:
            await db.set(key, json.dumps([str(path), kind]), ex=180)
        base = _config()[2]
        try:
            async with httpx.AsyncClient(timeout=26) as client:
                result = await _bot_call(client, token, method, {
                    "chat_id": chat, kind: base + "/api/integrations/telegram/media/" + ticket})
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
                return await studio.upload_attachment(request, conversation_id, UploadFile(
                    download, filename=file.get("file_name") or Path(path).name))
        except (httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(502, "دریافت فایل تلگرام انجام نشد.")


EVENT_LABELS = {
    "tool.started": "شروع", "tool.progress": "پیشرفت", "tool.completed": "پایان",
    "tool.failed": "خطا", "storyboard.ready": "استوری‌بورد", "render.started": "شروع رندر",
    "render.completed": "پایان رندر", "render.failed": "خطای رندر", "motion.progress": "موشن",
    "agent.thinking_summary": "بررسی", "agent.progress": "ایجنت", "work.state": "وضعیت",
}


def _activity(event):
    label = EVENT_LABELS.get(event["type"])
    data = event["data"]
    if not label:
        return None
    message = next((data[k] for k in ("message", "text", "stage") if isinstance(data.get(k), str) and data[k]), "")
    progress = data.get("progress")
    percent = f" · {progress}٪" if type(progress) in (int, float) and 0 <= progress <= 100 else ""
    return f"{label} · {message}{percent}" if message or percent else None


async def _updates(request, db, token, tg, conversation):
    user = studio._user(request)
    await studio.sync_conversation(conversation, user)
    cursor_key = PREFIX + f"cursor:{tg}:{user}:{conversation}"
    after = int(await db.get(cursor_key) or 0)
    events = await studio.repo.events(conversation, user, after, limit=60)
    seen = set()
    for event in events:
        kind, data, seq = event["type"], event["data"], event["seq"]
        if kind == "narration.ready" and type(data.get("event_seq")) is int:
            try:
                media = await studio.event_audio(request, conversation, data["event_seq"])
                await _send_file(token, tg, Path(media.path), "audio")
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
        elif kind == "assistant.response.completed":
            # The persisted messages below also include replies without streamed events.
            pass
        else:
            line = _activity(event)
            if line and line not in seen:
                await _send(token, tg, line[:3900])
                seen.add(line)
        await db.set(cursor_key, seq, ex=30 * 86400)
    chat = await studio.repo.get_conversation(conversation, user)
    sent = 0
    for message in chat.get("messages", []):
        if message.get("role") != "assistant" or not message.get("content"):
            continue
        key = cursor_key + ":message:" + str(message["id"])
        if not await db.exists(key):
            if sent == 20:
                break
            text = message["content"]
            for start in range(0, len(text), 3900):
                await _send(token, tg, text[start:start + 3900])
            await db.set(key, "1", ex=30 * 86400)
            sent += 1
    return len(events) + sent


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
    if callback:
        action = str(callback.get("data") or "")
        if action not in {"studio:" + x for x in ("new", "updates", "output", "cancel", "approve", "lite", "medium", "ref-content", "ref-style", "ref-both")}:
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
    async with storage() as db:
        claim = PREFIX + f"update:{update_id}"
        if not await db.set(claim, "1", nx=True, ex=172800):
            return {"ok": True}
        account = await db.get(PREFIX + f"tg:{tg}")
        user = await auth.db_get_user_by_id(account) if account and auth.USE_DB else auth._find_by_id(account) if account else None
        if not user:
            code = secrets.token_urlsafe(24)
            await db.set(_key(code), str(tg), ex=PAIR_TTL)
            await _send(token, tg, "برای اتصال، وارد حساب EditorGPT شوید و اتصال را تأیید کنید.",
                        buttons=[[{"text": "اتصال حساب", "url": base + "/telegram/link?code=" + code}]])
            return {"ok": True}
        chat_key = PREFIX + f"chat:{tg}"
        conversation_id = await db.get(chat_key)
        request.state.user = user
        draft_key = PREFIX + f"reference:{tg}:{user.id}"
        mode_key = PREFIX + f"mode:{tg}:{user.id}"
        if callback and command in {"/lite", "/medium"}:
            mode = command[1:]
            await db.set(mode_key, mode)
            await _send(token, tg, f"EditorGPT {mode.title()} انتخاب شد. درخواست را بفرستید.", buttons=_menu(base, conversation_id))
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
            await db.delete(draft_key)
            await db.delete(chat_key)
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
        elif (command and command not in ("/lite", "/medium")) or (not text and not attachment):
            await _send(token, tg, "متن، لینک یا فایل را بفرستید یا یکی از دکمه‌ها را انتخاب کنید.",
                        buttons=keyboard)
        else:
            mode, _, content = text.partition(" ") if command else ("", "", text)
            if not content.strip() and not attachment:
                await _send(token, tg, "درخواستتان را بعد از نام موتور بنویسید.", buttons=keyboard)
                return {"ok": True}
            if text in REFERENCE_CHOICES:
                reference = await db.getdel(draft_key)
                if not reference:
                    await _send(token, tg, "لینک رفرنس را دوباره بفرستید.", buttons=keyboard)
                    return {"ok": True}
                content = f"با این رفرنس یک ویدیوی تازه بساز. فقط از نقش انتخاب‌شده برای رفرنس استفاده کن: {REFERENCE_CHOICES[text]}.\n{reference}"
            elif not attachment and not command and text.startswith(("https://www.instagram.com/", "https://instagram.com/")) and len(text.split()) == 1:
                await db.set(draft_key, text, ex=900)
                await _send(token, tg, "این رفرنس را برای چه چیزی استفاده کنم؟", buttons=[[
                    {"text": label, "callback_data": "studio:ref-" + action}
                    for label, action in zip(REFERENCE_CHOICES, ("content", "style", "both"))
                ]])
                return {"ok": True}
            from brain.lm_gateway import user_context
            context = user_context.set(str(user.id))
            try:
                if not conversation_id:
                    chat = await studio.create_conversation(request, studio.ConversationCreate(title="تلگرام"))
                    conversation_id = chat["id"]
                    await db.set(chat_key, conversation_id)
                ids = []
                if attachment:
                    uploaded = await _attach(request, token, conversation_id, attachment)
                    ids.append(uploaded["id"])
                    content = content or str(message.get("caption") or "").strip() or "این فایل را بررسی کن و گزینه‌های استفاده از آن را بپرس."
                await studio.send_message(request, conversation_id, studio.MessageCreate(
                    content=content[:12000], attachment_ids=ids, render_target="server",
                    agent_mode=command.removeprefix("/") if mode else await db.get(mode_key)))
            except HTTPException as exc:
                await _send(token, tg, str(exc.detail)[:500], buttons=keyboard)
                return {"ok": True}
            finally:
                user_context.reset(context)
            await _send(token, tg, "درخواست در Studio ثبت شد.",
                        buttons=[[{"text": "مشاهدهٔ گفتگو", "web_app": {"url": base + "/studio/" + conversation_id}}]])
    return {"ok": True}
