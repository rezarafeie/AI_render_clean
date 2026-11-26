"""Rafiei Hub API: Rafiei Hub (one.rafiei.co) runs EditorGPT inside its own UI, server to server.

    GET  /hub-api/health                    {"data": {"ok": true, "app": "editor", "version": "1"}}
    POST /hub-api/{action}                  JSON body; Authorization: Bearer <HUB_SHARED_SECRET>; X-Hub-User: URL-encoded JSON {hub_user_id, email, name}
    PUT  /hub-api/upload/{token}            the signed upload URL that upload.create returns (raw body, video/image/audio, up to 200 MB)
    GET  /hub-api/media/{ticket}            signed media URLs (video, thumbnail) that play in a <video> tag (range requests, inline)

The hub never signs in to EditorGPT: its shared secret is the authentication, and the person is the EditorGPT account with the verified email the hub
sends (created only by project.create). Every action runs as that person through the same routes the EditorGPT site uses - the same credit check and
deduction, the same engines, the same chat timeline - so work, credits, logs and files all stay in EditorGPT. A user id in the body is never trusted.
Responses: {"data": ...} or {"error": "<safe Persian message>"} with 400, 401, 402, 404, 409, 429 or 502; never a key, a trace or a provider's raw error.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse

from app.config import settings

log = logging.getLogger("hub_api")
router = APIRouter(prefix="/hub-api", tags=["hub-api"])

VERSION = "1"
PREFIX = "editorgpt:hub:"
ROOT = Path(settings.JOBS_DIR) / "hub_api"
UPLOADS = ROOT / "uploads"
THUMBS = ROOT / "thumbs"
MAX_UPLOAD = 200 * 1024 * 1024
MEDIA_TTL = 3 * 3600                     # signed media URLs live 3 hours (at least 1 hour was asked)
UPLOAD_TTL = 2 * 3600
PAGE = 30
ACTIONS = ["auth.capabilities", "account.resolve", "account.link", "credits.get", "project.list", "project.create", "project.message",
           "project.get", "project.cancel", "project.delete", "upload.create"]
SELF = "http://127.0.0.1:8000"


class HubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# ── plumbing ─────────────────────────────────────────────────────────────────

def _secret() -> str:
    value = os.environ.get("HUB_SHARED_SECRET", "").strip()
    if not value:
        try:
            value = (ROOT / "secret").read_text().strip()
        except OSError:
            value = ""
    return value


def _authorized(request: Request) -> bool:
    secret = _secret()
    header = request.headers.get("authorization", "")
    given = header[7:].strip() if header.startswith("Bearer ") else ""
    return bool(secret) and len(secret) >= 24 and hmac.compare_digest(given.encode(), secret.encode())


def _public_base() -> str:
    base = (os.environ.get("HUB_PUBLIC_BASE") or os.environ.get("EDITOR_TELEGRAM_STUDIO_URL") or "https://editor.rafiei.co").rstrip("/")
    return base + "/api"


async def _redis():
    from redis.asyncio import from_url
    if not settings.REDIS_URL:
        raise HubError(502, "سرویس موقتاً در دسترس نیست.")
    return from_url(settings.REDIS_URL, decode_responses=True)


def _audit(action: str, user: str | None, status: int, detail: str = "", started: float | None = None) -> None:
    """Every call, with source rafiei-hub: a log line and a JSON line in job_data/hub_api/calls.jsonl."""
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "rafiei-hub", "action": action, "user": user, "status": status,
           "detail": detail[:300], "ms": round((time.monotonic() - started) * 1000) if started else None}
    log.info("rafiei-hub %s user=%s status=%s %s", action, user, status, detail[:200])
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        with open(ROOT / "calls.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _identity(request: Request) -> dict:
    raw = request.headers.get("x-hub-user", "")
    try:
        value = json.loads(unquote(raw)) if raw else {}
    except ValueError:
        raise HubError(400, "اطلاعات کاربر هاب نامعتبر است.")
    email = str(value.get("email") or "").strip().lower()
    if not email or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HubError(400, "ایمیل کاربر هاب نامعتبر است.")
    return {"hub_user_id": str(value.get("hub_user_id") or "")[:120], "email": email, "name": str(value.get("name") or "").strip()[:120]}


async def _find_user(email: str):
    from app import auth
    return await auth.db_get_user(email) if auth.USE_DB else auth._find_by_email(email)


async def _user(request: Request, *, create: bool = False):
    """The EditorGPT account of the hub's person (by verified email). Created only when `create` (project.create); never a duplicate."""
    who = _identity(request)
    user = await _find_user(who["email"])
    if user is None and create:
        from app import auth
        name = who["name"] or who["email"].split("@")[0]
        password = secrets.token_urlsafe(32)                    # never used: a hub person signs in through the hub; a reset link sets one if wanted
        try:
            user = await auth.db_register(who["email"], name, password) if auth.USE_DB else auth.register(who["email"], name, password)
        except ValueError as exc:
            if "DUPLICATE" in str(exc):
                user = await _find_user(who["email"])
            else:
                raise HubError(400, "ساخت حساب ممکن نشد؛ نام و ایمیل را بررسی کنید.")
        _audit("account.created", str(user.id) if user else None, 201, who["email"])
    if user is None:
        raise HubError(404, "حسابی با این ایمیل در ادیتور پیدا نشد.")
    if not getattr(user, "is_active", True):
        raise HubError(401, "این حساب غیرفعال است.")
    return user, who


def _token(user_id: str) -> str:
    from app import auth
    return auth.jwt.encode({"sub": str(user_id), "type": "access", "exp": time.time() + 300}, auth.jwt_secret(), algorithm=auth.JWT_ALGORITHM)


async def _call(user_id: str, method: str, path: str, **kwargs) -> httpx.Response:
    """The EditorGPT site's own route, as the person: same checks, same credit gate, same engines."""
    headers = {"Authorization": "Bearer " + _token(user_id), "Host": (os.environ.get("ALLOWED_HOSTS", "") or "editor.rafiei.co").split(",")[0].strip()}
    async with httpx.AsyncClient(base_url=SELF, timeout=120, trust_env=False) as client:
        return await client.request(method, path, headers=headers, **kwargs)


def _studio_error(response: httpx.Response, fallback: str) -> HubError:
    """The site's answer as a safe Persian error with the right status (credit, missing, busy, engine)."""
    status = response.status_code
    try:
        detail = str(response.json().get("detail") or "")
    except ValueError:
        detail = ""
    if status == 402 or "اعتبار" in detail:
        return HubError(402, "اعتبار کافی نیست")
    if status == 404:
        return HubError(404, "پروژه پیدا نشد.")
    if status == 409:
        return HubError(409, detail if re.search(r"[؀-ۿ]", detail) and len(detail) < 300 else "این پروژه الان در حال کار است؛ کمی بعد دوباره امتحان کنید.")
    if status == 429:
        return HubError(429, "درخواست‌ها زیاد است؛ کمی بعد دوباره امتحان کنید.")
    if status in (400, 413, 422):
        return HubError(400, "درخواست نامعتبر است.")
    return HubError(502, fallback)


async def _idempotent(request: Request, user_id: str, action: str):
    key = request.headers.get("idempotency-key", "").strip()
    if not key:
        return None, None
    if len(key) > 200:
        raise HubError(400, "کلید تکرار نامعتبر است.")
    name = PREFIX + f"idem:{user_id}:{action}:" + hashlib.sha256(key.encode()).hexdigest()
    db = await _redis()
    try:
        saved = await db.get(name)
    finally:
        await db.aclose()
    return name, (json.loads(saved) if saved else None)


async def _remember(name: str | None, value: dict) -> None:
    if not name:
        return
    db = await _redis()
    try:
        await db.set(name, json.dumps(value, ensure_ascii=False), ex=24 * 3600)
    finally:
        await db.aclose()


async def _sign(path: Path, owner: str, kind: str) -> str:
    """A signed HTTPS URL for a file (3 hours), served inline with range requests so a <video> on the hub plays and seeks it."""
    ticket = secrets.token_urlsafe(32)
    db = await _redis()
    try:
        await db.set(PREFIX + "media:" + hashlib.sha256(ticket.encode()).hexdigest(), json.dumps([str(path), owner, kind]), ex=MEDIA_TTL)
    finally:
        await db.aclose()
    return f"{_public_base()}/hub-api/media/{ticket}"


def _thumbnail(video: Path) -> Path | None:
    target = THUMBS / (hashlib.sha256(f"{video}:{video.stat().st_size}".encode()).hexdigest()[:24] + ".jpg")
    if target.is_file():
        return target
    THUMBS.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-2", str(target)],
                       check=True, timeout=60, capture_output=True)
        return target if target.is_file() else None
    except Exception:
        return None


# ── the project view (chat → hub shape) ─────────────────────────────────────

FAIL = {"tool.failed", "job.failed", "pro.failed", "assistant.response.failed"}
OUTPUTS = {"render.completed", "motion.completed", "pro.output"}
STOPPED = "شما این کار را متوقف کردید"
HEARTBEAT = ("از شروع این مرحله", "هنوز گزارش پیشرفت")      # the engine's "still working" notes: kept in steps, not repeated as messages
# Project (engine job) states: the agent can be finished while the engine it started still works (a talking reel, a dub, a storyboard render).
PROJECT_ACTIVE = {"queued", "planning", "running", "rendering", "generating", "processing"}
PROJECT_WAITING = {"awaiting_confirmation", "awaiting_input", "needs_input", "paused"}


def _turn_of(at: str, turns: list[str]) -> int:
    """Which run (user message) an event belongs to: 1 for the first message, 2 for the second, …"""
    from bisect import bisect_right
    return max(1, bisect_right(turns, at or ""))


def _steps(events: list[dict], turns: list[str], *, running: bool, failed: bool) -> list[dict]:
    """The chat's timeline as rows: one per step of each run (a new message starts new rows), updated in place within a run.
    Each row: id, run, status (running|done|failed), title, log, created_at, updated_at (and the older kind/detail fields)."""
    rows: dict[str, dict] = {}
    order: list[str] = []
    current = len(turns) or 1

    def put(key, kind, title, detail, at):
        if not title:
            return
        turn = _turn_of(at, turns)
        key = f"r{turn}:{key}"
        if key not in rows:
            order.append(key)
            rows[key] = {"id": key, "run": turn, "kind": kind, "title": title[:300], "detail": detail[:600], "created_at": at, "updated_at": at}
        else:
            row = rows[key]
            row.update(kind=kind, title=title[:300] or row["title"], detail=(detail or row["detail"])[:600], updated_at=at or row["updated_at"])

    for event in events:
        kind, data, at = event.get("type"), event.get("data") or {}, event.get("created_at")
        key = str(data.get("activity_id") or data.get("id") or data.get("key") or data.get("tool") or kind)
        text = str(data.get("message") or data.get("label") or data.get("text") or data.get("title") or "")
        detail = str(data.get("detail") or data.get("stage") or "")
        if kind == "message.started":
            put(f"msg-{event.get('seq')}", "think", "در حال بررسی درخواست", "", at)
        elif kind in ("agent.thinking_summary", "agent.narration"):
            put(f"think-{event.get('seq')}", "think", text or str(data.get("summary") or ""), "", at)
        elif kind == "plan.ready":
            put(f"plan-{event.get('seq')}", "plan", text or "برنامه آماده شد", detail, at)
        elif kind in ("tool.started", "tool.progress"):
            put("tool-" + key, "action", text or key, detail, at)
        elif kind == "tool.completed":
            put("tool-" + key, "done", text or key, detail, at)
        elif kind == "motion.log":
            state = str(data.get("state") or "")
            put("motion-" + str(data.get("motion_id")) + "-" + str(data.get("key")), "error" if state == "failed" else "done" if state == "done" else "action",
                text, str(data.get("detail") or ""), at)
        elif kind == "motion.progress":
            put("motion-progress-" + str(data.get("motion_id")), "action", text or "در حال ساخت", f"{data.get('progress', '')}%", at)
        elif kind in FAIL:
            put(f"error-{event.get('seq')}", "error", text or str(data.get("error") or "خطا"), "", at)
        elif kind in OUTPUTS or kind == "pro.finished":
            put(f"done-{event.get('seq')}", "done", "ویدیو آماده شد" if kind in OUTPUTS else "کار تمام شد", "", at)
    out = [rows[k] for k in order]
    for index, row in enumerate(out):
        later = any(r["run"] == row["run"] for r in out[index + 1:])
        if row["kind"] == "error":
            row["status"] = "failed"
        elif row["kind"] == "done":
            row["status"] = "done"
        elif row["run"] < current or not running:
            # A step of an earlier run, or of a run that has ended: done, unless the run failed and this was its last open step.
            row["status"] = "failed" if (failed and row["run"] == current and not later) else "done"
        elif row["kind"] in ("think", "plan"):
            row["status"] = "done" if later else "running"
        else:
            row["status"] = "running"                    # an engine step of the run in progress, not completed yet
        row["log"] = row["detail"]
    return out


def _messages(messages: list[dict], events: list[dict]) -> list[dict]:
    """Saved messages plus the assistant's narration as it is produced (narration events, and a reply still being streamed)."""
    rows = [{"id": str(m.get("id")), "role": m.get("role"), "content": m.get("content") or "", "created_at": m.get("created_at")} for m in messages]
    saved = {(m.get("content") or "").strip() for m in messages if m.get("role") == "assistant"}
    streaming: dict[str, dict] = {}
    for event in events:
        kind, data = event.get("type"), event.get("data") or {}
        if kind == "agent.narration":
            text = str(data.get("text") or data.get("message") or "").strip()
            if text and text not in saved and not text.startswith(HEARTBEAT) and (len(rows) == 0 or rows[-1]["content"] != text):
                rows.append({"id": f"ev-{event.get('seq')}", "role": "assistant", "kind": "narration", "content": text, "created_at": event.get("created_at")})
        elif kind == "assistant.response.delta":
            streaming[str(data.get("response_id"))] = {"text": str(data.get("text") or ""), "at": event.get("created_at"), "seq": event.get("seq")}
        elif kind in ("assistant.response.completed", "assistant.response.failed"):
            streaming.pop(str(data.get("response_id")), None)
    for rid, part in streaming.items():
        if part["text"].strip() and part["text"].strip() not in saved:
            rows.append({"id": f"ev-{part['seq']}", "role": "assistant", "kind": "partial", "content": part["text"], "created_at": part["at"]})
    return sorted(rows, key=lambda r: r.get("created_at") or "")


async def _project_view(user_id: str, project_id: str) -> dict:
    conversation = await _call(user_id, "GET", f"/studio/conversations/{project_id}", params={"messages": 100})
    if conversation.status_code != 200:
        raise _studio_error(conversation, "خواندن پروژه ممکن نشد.")
    value = conversation.json()
    events, after = [], 0
    for _ in range(20):                                      # the whole timeline, 500 events per page
        page = await _call(user_id, "GET", f"/studio/conversations/{project_id}/event-history", params={"after": after})
        batch = page.json() if page.status_code == 200 else []
        events += batch
        if len(batch) < 500:
            break
        after = max(e["seq"] for e in batch)
    messages = value.get("messages") or []
    users = [m for m in messages if m.get("role") == "user"]
    turns = sorted(m.get("created_at") or "" for m in users)
    last_user_at = turns[-1] if turns else ""
    since = [e for e in events if (e.get("created_at") or "") >= last_user_at]
    output = {}
    output_at = ""
    from app import telegram_outputs
    for event in reversed(events):
        if event.get("type") in OUTPUTS:
            try:
                found = await telegram_outputs._output(project_id, str(user_id), event["type"], event.get("data") or {})
            except Exception:
                found = None
            if found and Path(found[0]).is_file():
                video = Path(found[0])
                output["video_url"] = await _sign(video, str(user_id), "video")
                thumb = await asyncio.to_thread(_thumbnail, video)
                if thumb:
                    output["thumbnail_url"] = await _sign(thumb, str(user_id), "image")
                output_at = event.get("created_at") or ""
                break
    # Working = the server's busy flag (a message, an agent run, a motion film) OR an engine job of this chat still running (talking reel, dub, storyboard).
    projects = value.get("projects") or []
    engine_active = [p for p in projects if str(p.get("status") or "") in PROJECT_ACTIVE]
    waiting = [p for p in projects if str(p.get("status") or "") in PROJECT_WAITING]
    agent_active = any(r.get("status") in ("queued", "running", "waiting_job") for r in value.get("agent_runs") or [])
    busy = bool(value.get("busy")) or bool(engine_active) or agent_active
    failed = next((e for e in reversed(since) if e.get("type") in FAIL), None)
    replies = [m for m in messages if m.get("role") == "assistant" and (m.get("created_at") or "") >= last_user_at]
    stopped = bool(replies) and (replies[-1].get("content") or "").startswith(STOPPED)

    def at_render(event: dict) -> bool:
        data = event.get("data") or {}
        marks = " ".join(str(data.get(k) or "") for k in ("status", "stage", "tool", "state", "key")).lower()
        return "render" in marks or "cloud_render" in marks
    recent = [e for e in since[-12:] if e.get("type") in ("tool.started", "tool.progress", "motion.progress", "motion.log", "pro.job")]
    phase = None
    if busy:
        status = "running"
        phase = "rendering" if (recent and at_render(recent[-1])) or any(str(p.get("status")) == "rendering" for p in engine_active) else "working"
    elif stopped:
        status = "cancelled"
    elif waiting and not (output_at and output_at >= last_user_at):
        status, phase = "running", "needs_input"            # the studio waits for an answer in the EditorGPT chat (a plan or a choice)
    elif output_at and output_at >= last_user_at:
        status = "done"
    elif failed and not (output_at and output_at >= failed.get("created_at", "")):
        status = "failed"
    elif not since and users:
        status = "queued"
    else:
        status = "done"
    error = None
    if status == "failed":
        error = (replies[-1]["content"] if replies else "ساخت ویدیو کامل نشد.")[:500]
    steps = _steps(events, turns, running=status in ("running", "queued"), failed=status == "failed")
    updated = max([s.get("updated_at") or "" for s in steps] + [m.get("created_at") or "" for m in messages[-1:]] + [""])
    return {"id": project_id, "title": value.get("title") or "", "prompt": users[0]["content"] if users else "", "status": status,
            **({"phase": phase} if phase else {}), **({"error": error} if error else {}), "run": len(turns), "updated_at": updated,
            "messages": _messages(messages, events), "steps": steps, "output": output}


# ── actions ─────────────────────────────────────────────────────────────────

async def _capabilities(request, body):
    return {"identity_sync": True, "actions": ACTIONS}


async def _resolve(request, body):
    who = _identity(request)
    user = await _find_user(who["email"])
    if user is None and body.get("create_if_missing"):
        user, who = await _user(request, create=True)
    return {"source_user_id": str(user.id) if user else None, "email": who["email"], "name": (user.name if user else who["name"]) or who["name"],
            "email_verified": True}


async def _link(request, body):
    user, who = await _user(request)
    if str(body.get("source_user_id") or "") not in ("", str(user.id)):
        raise HubError(409, "این حساب متعلق به ایمیل دیگری است.")
    if not who["hub_user_id"]:
        raise HubError(400, "شناسهٔ کاربر هاب لازم است.")
    db = await _redis()
    try:
        linked = await db.get(PREFIX + f"link:{user.id}")
        if linked and linked != who["hub_user_id"]:
            raise HubError(409, "این حساب ادیتور به کاربر دیگری در هاب متصل است.")
        await db.set(PREFIX + f"link:{user.id}", who["hub_user_id"])
    finally:
        await db.aclose()
    return {"ok": True}


async def _credits(request, body):
    user, _ = await _user(request)
    from app import credits
    state = await credits.account(str(user.id))
    return {"balance": int(state.get("balance") or 0), "unit": "credit", "unlimited": bool(state.get("unlimited"))}


async def _list(request, body):
    user, _ = await _user(request)
    response = await _call(str(user.id), "GET", "/studio/conversations")
    if response.status_code != 200:
        raise _studio_error(response, "خواندن فهرست پروژه‌ها ممکن نشد.")
    rows = response.json() if isinstance(response.json(), list) else response.json().get("items", [])
    try:
        start = max(0, int(body.get("cursor") or 0))
    except (TypeError, ValueError):
        raise HubError(400, "مقدار cursor نامعتبر است.")
    page = rows[start:start + PAGE]
    thumbs = await _list_thumbnails(str(user.id), [r.get("id") for r in page])
    items = [{"id": r.get("id"), "title": r.get("title") or "", "status": "running" if r.get("busy") else (r.get("status") or "done"),
              **({"thumbnail_url": thumbs[r.get("id")]} if thumbs.get(r.get("id")) else {}), "updated_at": r.get("updated_at")} for r in page]
    return {"items": items, "next_cursor": str(start + PAGE) if start + PAGE < len(rows) else None}


async def _list_thumbnails(user_id: str, ids: list) -> dict:
    """A thumbnail for each listed project that made a video: its latest output (render, motion graphic, Pro delivery), one frame, signed."""
    if not ids:
        return {}
    from sqlalchemy import select
    from app.models import StudioEvent
    from app.studio_store import AsyncSessionLocal
    from app import telegram_outputs
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(StudioEvent.conversation_id, StudioEvent.event_type, StudioEvent.data, StudioEvent.seq)
                                 .where(StudioEvent.conversation_id.in_(ids), StudioEvent.event_type.in_(OUTPUTS)).order_by(StudioEvent.seq))).all()
    latest = {}
    for cid, kind, data, _seq in rows:
        latest[cid] = (kind, data or {})
    out = {}

    async def one(cid, kind, data):
        try:
            found = await telegram_outputs._output(cid, user_id, kind, data)
            if found and Path(found[0]).is_file():
                thumb = await asyncio.to_thread(_thumbnail, Path(found[0]))
                if thumb:
                    out[cid] = await _sign(thumb, user_id, "image")
        except Exception:
            pass
    await asyncio.gather(*(one(cid, *value) for cid, value in latest.items()))
    return out


def _hints(body: dict) -> str:
    parts = []
    ratio = str(body.get("aspect_ratio") or "")
    if ratio:
        names = {"9:16": "عمودی ۹:۱۶", "16:9": "افقی ۱۶:۹", "1:1": "مربع ۱:۱"}
        if ratio not in names:
            raise HubError(400, "نسبت تصویر باید 9:16، 16:9 یا 1:1 باشد.")
        parts.append(f"قطع {names[ratio]}")
    if body.get("duration_s") not in (None, ""):
        try:
            seconds = int(float(body["duration_s"]))
        except (TypeError, ValueError):
            raise HubError(400, "مدت ویدیو نامعتبر است.")
        if not 3 <= seconds <= 600:
            raise HubError(400, "مدت ویدیو باید بین ۳ تا ۶۰۰ ثانیه باشد.")
        parts.append(f"حدود {seconds} ثانیه")
    return ("\n\n(" + "، ".join(parts) + ")") if parts else ""


async def _attach(user_id: str, project_id: str, upload_ids: list) -> list[str]:
    from app.studio_ingest import attachment_folder, finalize, IngestError
    ids = []
    db = await _redis()
    try:
        for item in upload_ids[:20]:
            upload_id = str((item or {}).get("upload_id") if isinstance(item, dict) else item or "")
            raw = await db.get(PREFIX + f"upload:{upload_id}") if re.fullmatch(r"[0-9a-f]{32}", upload_id) else None
            meta = json.loads(raw) if raw else None
            if not meta or meta["user"] != user_id or not meta.get("done"):
                raise HubError(400, "فایل بارگذاری‌شده پیدا نشد یا کامل نیست.")
            source = Path(meta["path"])
            folder = attachment_folder(user_id, project_id)
            temporary = folder / f"uploading_{upload_id}{Path(meta['filename']).suffix.lower()}"
            await asyncio.to_thread(shutil.move, str(source), str(temporary))
            try:
                attachment = await finalize(user_id, project_id, temporary, meta["filename"], meta["kind"], meta["content_type"], temporary.stat().st_size)
            except IngestError:
                temporary.unlink(missing_ok=True)
                raise HubError(400, "فایل بارگذاری‌شده قابل استفاده نیست.")
            await db.delete(PREFIX + f"upload:{upload_id}")
            ids.append(attachment["id"])
    finally:
        await db.aclose()
    return ids


async def _create(request, body):
    if str(body.get("app") or "editor") != "editor":
        raise HubError(400, "این سرویس فقط برای ادیتور است.")
    prompt = str(body.get("prompt") or "").strip()
    if not prompt or len(prompt) > 10000:
        raise HubError(400, "متن درخواست خالی یا خیلی بلند است.")
    hints = _hints(body)
    user, _ = await _user(request, create=True)
    uid = str(user.id)
    name, saved = await _idempotent(request, uid, "project.create")
    if saved:
        return saved
    from app import credits
    try:
        await credits.require(uid)                         # the same gate the site uses for a new request; never a top-up
    except credits.CreditsExhausted:
        raise HubError(402, "اعتبار کافی نیست")
    created = await _call(uid, "POST", "/studio/conversations", json={"title": prompt[:60]})
    if created.status_code not in (200, 201):
        raise _studio_error(created, "ساخت پروژه ممکن نشد.")
    project_id = created.json()["id"]
    attachment_ids = await _attach(uid, project_id, list(body.get("assets") or []))
    sent = await _call(uid, "POST", f"/studio/conversations/{project_id}/messages", json={"content": prompt + hints, "attachment_ids": attachment_ids})
    if sent.status_code not in (200, 201, 202):
        raise _studio_error(sent, "شروع ساخت ویدیو ممکن نشد؛ مشکل از موتور ساخت است، نه اعتبار. کمی بعد دوباره امتحان کنید.")
    result = {"id": project_id}
    await _remember(name, result)
    return result


async def _message(request, body):
    user, _ = await _user(request)
    uid = str(user.id)
    project_id, prompt = str(body.get("id") or ""), str(body.get("prompt") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", project_id) or not prompt or len(prompt) > 10000:
        raise HubError(400, "شناسهٔ پروژه یا متن پیام نامعتبر است.")
    name, saved = await _idempotent(request, uid, "project.message:" + project_id)
    if saved:
        return saved
    sent = await _call(uid, "POST", f"/studio/conversations/{project_id}/messages", json={"content": prompt, "attachment_ids": []})
    if sent.status_code not in (200, 201, 202):
        raise _studio_error(sent, "ارسال پیام به موتور ساخت ممکن نشد؛ کمی بعد دوباره امتحان کنید.")
    await _remember(name, {"ok": True})
    return {"ok": True}


async def _get(request, body):
    user, _ = await _user(request)
    project_id = str(body.get("id") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", project_id):
        raise HubError(400, "شناسهٔ پروژه نامعتبر است.")
    return await _project_view(str(user.id), project_id)


async def _delete(request, body):
    user, _ = await _user(request)
    project_id = str(body.get("id") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", project_id):
        raise HubError(400, "شناسهٔ پروژه نامعتبر است.")
    response = await _call(str(user.id), "DELETE", f"/studio/conversations/{project_id}")
    if response.status_code not in (200, 204):
        raise _studio_error(response, "حذف پروژه ممکن نشد.")
    return {"ok": True}


async def _cancel(request, body):
    """project.cancel: stop whatever the project is doing (the site's Stop button), then report it as cancelled."""
    user, _ = await _user(request)
    project_id = str(body.get("id") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", project_id):
        raise HubError(400, "شناسهٔ پروژه نامعتبر است.")
    response = await _call(str(user.id), "POST", f"/studio/conversations/{project_id}/stop")
    if response.status_code not in (200, 202, 204):
        raise _studio_error(response, "توقف پروژه ممکن نشد.")
    return {"ok": True, "id": project_id, "status": "cancelled"}


async def _upload_create(request, body):
    user, _ = await _user(request, create=True)
    from app.studio_ingest import kind_of
    filename = Path(str(body.get("filename") or "")).name[:200]
    kind = kind_of(filename) if filename else None
    content_type = str(body.get("content_type") or mimetypes.guess_type(filename)[0] or "")[:100]
    try:
        size = int(body.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if not kind or not content_type.split("/")[0] in ("video", "image", "audio"):
        raise HubError(400, "فقط فایل ویدیو، تصویر یا صدا پذیرفته می‌شود.")
    if not 0 < size <= MAX_UPLOAD:
        raise HubError(400, "حجم فایل باید حداکثر ۲۰۰ مگابایت باشد.")
    upload_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    meta = {"user": str(user.id), "filename": filename, "content_type": content_type, "size": size, "kind": kind,
            "path": str(UPLOADS / f"{upload_id}{Path(filename).suffix.lower()}"), "done": False}
    db = await _redis()
    try:
        await db.set(PREFIX + f"upload:{upload_id}", json.dumps(meta), ex=UPLOAD_TTL)
        await db.set(PREFIX + "upload-token:" + hashlib.sha256(token.encode()).hexdigest(), upload_id, ex=UPLOAD_TTL)
    finally:
        await db.aclose()
    expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + UPLOAD_TTL))
    return {"upload_id": upload_id, "upload_url": f"{_public_base()}/hub-api/upload/{token}", "expires_at": expires}


HANDLERS = {"auth.capabilities": _capabilities, "account.resolve": _resolve, "account.link": _link, "credits.get": _credits, "project.list": _list,
            "project.create": _create, "project.message": _message, "project.get": _get, "project.cancel": _cancel, "project.delete": _delete, "upload.create": _upload_create}


# ── routes ──────────────────────────────────────────────────────────────────

def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status, headers={"Cache-Control": "no-store, max-age=0"})


@router.get("/health")
async def health(request: Request):
    """With the hub's secret: ok, the app and the actions. Without it (or a wrong one): 401, never a 404 or a page."""
    if not _authorized(request):
        _audit("health", None, 401, "bad or missing secret")
        return _error(401, "دسترسی مجاز نیست.")
    return {"data": {"ok": True, "app": "editor", "version": VERSION, "actions": ["health", *ACTIONS]}}


@router.post("")
@router.post("/")
async def run_body(request: Request):
    """The hub's other form: POST /hub-api with {"action": "...", ...} in the body."""
    try:
        body = await request.json()
        action = str(body.get("action") or "") if isinstance(body, dict) else ""
    except ValueError:
        action = ""
    if action == "health":
        return await health(request)
    return await run(action or "-", request)


@router.post("/{action}")
async def run(action: str, request: Request):
    started = time.monotonic()
    if not _authorized(request):
        _audit(action, None, 401, "bad or missing secret", started)
        return _error(401, "دسترسی مجاز نیست.")
    handler = HANDLERS.get(action)
    if handler is None:
        _audit(action, None, 404, "unknown action", started)
        return _error(404, "این عملیات وجود ندارد.")
    try:
        body = await request.json() if (await request.body()) else {}
        if not isinstance(body, dict):
            raise ValueError
        body.pop("action", None)
    except ValueError:
        _audit(action, None, 400, "bad json", started)
        return _error(400, "بدنهٔ درخواست باید JSON معتبر باشد.")
    who = None
    try:
        try:
            who = _identity(request)["email"] if action != "auth.capabilities" else None
        except HubError:
            if action != "auth.capabilities":
                raise
        data = await handler(request, body)
        _audit(action, who, 200, "", started)
        # Live state: never cached by the relay, a CDN or the browser (project.get is polled every few seconds).
        return JSONResponse({"data": data}, headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache", "CDN-Cache-Control": "no-store"})
    except HubError as exc:
        _audit(action, who, exc.status, exc.message, started)
        return _error(exc.status, exc.message)
    except Exception:
        log.exception("rafiei-hub %s failed", action)
        _audit(action, who, 502, "internal error", started)
        return _error(502, "خطای داخلی ادیتور؛ کمی بعد دوباره امتحان کنید.")


@router.put("/upload/{token}")
async def upload(token: str, request: Request):
    """The signed upload URL: the raw file body (one PUT), at most the size declared in upload.create and 200 MB."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return _error(404, "لینک بارگذاری نامعتبر است.")
    db = await _redis()
    try:
        upload_id = await db.get(PREFIX + "upload-token:" + hashlib.sha256(token.encode()).hexdigest())
        raw = await db.get(PREFIX + f"upload:{upload_id}") if upload_id else None
        if not raw:
            return _error(404, "لینک بارگذاری منقضی شده است.")
        meta = json.loads(raw)
        if meta.get("done"):
            return _error(409, "این فایل قبلاً بارگذاری شده است.")
        limit, written, target = min(MAX_UPLOAD, int(meta["size"]) + 1024), 0, Path(meta["path"])
        partial = target.with_suffix(target.suffix + ".part")
        with open(partial, "wb") as handle:
            async for chunk in request.stream():
                written += len(chunk)
                if written > limit:
                    handle.close()
                    partial.unlink(missing_ok=True)
                    return _error(400, "حجم فایل بیشتر از مقدار اعلام‌شده است.")
                handle.write(chunk)
        if written == 0:
            partial.unlink(missing_ok=True)
            return _error(400, "فایل خالی است.")
        partial.replace(target)
        meta.update(done=True, size=written)
        await db.set(PREFIX + f"upload:{upload_id}", json.dumps(meta), ex=UPLOAD_TTL)
        await db.delete(PREFIX + "upload-token:" + hashlib.sha256(token.encode()).hexdigest())
        _audit("upload.put", meta["user"], 200, f"{written} bytes")
        return {"data": {"upload_id": upload_id, "size": written}}
    finally:
        await db.aclose()


@router.get("/media/{ticket}")
async def media(ticket: str, request: Request):
    """A signed media URL: inline (plays in a <video> on the hub, range requests for seeking), private, never cached by a shared cache."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", ticket):
        return _error(404, "لینک نامعتبر است.")
    db = await _redis()
    try:
        raw = await db.get(PREFIX + "media:" + hashlib.sha256(ticket.encode()).hexdigest())
    finally:
        await db.aclose()
    if not raw:
        return _error(404, "لینک منقضی شده است.")
    path, owner, _kind = json.loads(raw)
    file = Path(path)
    media_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    if file.is_file():
        response = FileResponse(file, media_type=media_type, filename=file.name, content_disposition_type="inline")
    else:
        from app import media_archive
        response = await asyncio.to_thread(media_archive.serve, request, file, owner, filename=file.name, media_type=media_type, inline_name=file.name)
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    return response
