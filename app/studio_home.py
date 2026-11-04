"""What the Studio start page shows: the person's latest edits with their real state, suggestions made from their own work, and the
InstaGPT (Hermes) connection with its recent chats.

Everything is read from what exists (conversations, projects, motion graphics, Hermes chats); nothing here generates media or spends
anything but one short text request for the suggestions, which is cached and has a plain fallback.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

KINDS = {"motion": "موشن‌گرافیک", "motion_graphic": "موشن‌گرافیک", "talking": "تدوین صحبتی", "localize": "دوبله و زیرنویس", "chat": "گفتگو"}
STATUS_LABELS = {"running": "در حال ساخت", "needs_input": "منتظر شما", "failed": "ناموفق", "ready": "آماده", "draft": "بدون خروجی"}
_GENERIC = [
    {"kind": "prompt", "label": "ساخت ریلز از ویدیوی من", "prompt": "از این ویدیو یک ریلز جذاب اینستاگرامی بساز"},
    {"kind": "prompt", "label": "زیرنویس فارسی خوانا", "prompt": "برای این ویدیو زیرنویس خوانا و حرفه‌ای بساز"},
    {"kind": "prompt", "label": "حذف مکث‌ها و اشتباه‌ها", "prompt": "مکث‌ها و اشتباه‌های این ویدیو را حذف کن"},
    {"kind": "prompt", "label": "تیزر موشن برای محصول", "prompt": "برای این محصول یک تیزر موشن ۳۰ ثانیه‌ای بساز"},
]
_CACHE: dict[str, tuple[str, float, list[dict]]] = {}
CACHE_SECONDS = 3600


def status_of(projects: list[dict], motion: dict | None) -> str:
    """One word for where this conversation's work stands: running > needs_input > failed > ready > draft."""
    states: list[str] = []
    if motion:
        raw = motion.get("status")
        states.append("running" if raw in ("queued", "writing", "checking", "rendering") else "needs_input" if raw == "needs_input"
                      else "failed" if raw == "failed" else "ready" if raw == "completed" else "draft")
    for project in projects:
        raw = str(project.get("status") or "")
        state = project.get("state") or {}
        if raw in ("running", "queued", "pending"): states.append("running")
        elif raw == "awaiting_confirmation": states.append("needs_input")
        elif raw == "error": states.append("failed")
        elif raw in ("done", "completed", "ready") or state.get("output") or state.get("candidate_output"): states.append("ready")
        else: states.append("draft")
    for wanted in ("running", "needs_input", "failed", "ready"):
        if wanted in states:
            return wanted
    return "draft"


def kind_of(conversation: dict, projects: list[dict]) -> str:
    if (conversation.get("state") or {}).get("motion"):
        return "motion"
    latest = max(projects, key=lambda p: str(p.get("updated_at") or ""), default=None)
    return (latest or {}).get("engine") or "chat"


def _motion_view(user_key: str, conversation: dict) -> dict | None:
    pointer = (conversation.get("state") or {}).get("motion")
    if not pointer:
        return None
    try:
        from app import motion_graphic
        directory = motion_graphic.locate(pointer["motion_id"], user_key)
        record = motion_graphic.load(directory)
        return {"id": record["id"], "status": record["status"], "version": record.get("current") or None, "completed": bool(record.get("versions"))}
    except Exception:
        return None


def summarize(conversation: dict, projects: list[dict], motion: dict | None) -> dict:
    kind = kind_of(conversation, projects)
    status = status_of(projects, motion)
    thumb = f"/studio/motion/{motion['id']}/thumb" if motion and motion.get("completed") else None
    return {"id": conversation["id"], "title": conversation.get("title") or "", "updated_at": conversation.get("updated_at"), "kind": kind,
            "kind_label": KINDS.get(kind, "گفتگو"), "status": status, "status_label": STATUS_LABELS[status], "thumb": thumb}


async def _projects_by_conversation(ids: list[str]) -> dict[str, list[dict]]:
    from app.studio_store import repo
    return await repo.projects_for(ids)


async def hermes_state(user_key: str) -> dict:
    """The InstaGPT connection (Instagram through Composio, as InstaGPT itself reads it) with the page's public numbers and the latest chat titles.
    `connected` is None when the answer is not known yet (slow or unreachable), never a guess; the function never raises (Hermes may be off)."""
    import asyncio
    state: dict = {"connected": None, "username": None, "followers": None, "follows": None, "media_count": None, "picture": None, "chats": []}
    try:
        from hermes.services import chats, composio_account
        try:
            row = await asyncio.wait_for(composio_account.account(user_key), 6)
            state["connected"] = bool(row)
            if row:
                state.update({k: row.get(k) for k in ("username", "followers", "follows", "media_count", "picture")})
                if str(row.get("username") or "") == "instagram":
                    state["username"] = None
        except asyncio.TimeoutError:
            pass
        state["chats"] = [c["title"] for c in (await chats.list_chats(user_key))[:5] if c.get("title") and c["title"] != "گفتگوی جدید"]
    except Exception as exc:
        log.info("hermes state unavailable: %s", type(exc).__name__)
    return state


def instagram_summary(state: dict) -> dict:
    """The few fields the header button shows."""
    return {k: state.get(k) for k in ("connected", "username", "followers", "follows", "media_count", "picture")}


def fallback_suggestions(recent: list[dict], hermes: dict) -> list[dict]:
    out: list[dict] = []
    waiting = next((r for r in recent if r["status"] in ("needs_input", "failed")), None)
    if waiting:
        out.append({"kind": "open", "label": f"ادامهٔ «{waiting['title'][:40]}»", "conversation_id": waiting["id"], "reason": waiting["status_label"]})
    finished = next((r for r in recent if r["status"] == "ready" and r["id"] != (waiting or {}).get("id")), None)
    if finished:
        out.append({"kind": "open", "label": f"ویرایش یا نسخهٔ جدید «{finished['title'][:40]}»", "conversation_id": finished["id"], "reason": "آماده"})
    if hermes.get("chats"):
        out.append({"kind": "prompt", "label": f"ریلز از ایدهٔ «{hermes['chats'][0][:36]}»", "prompt": f"از ایدهٔ «{hermes['chats'][0]}» که در InstaGPT داشتم یک ریلز بساز", "reason": "از InstaGPT"})
    for item in _GENERIC:
        if len(out) >= 4: break
        out.append(item)
    return out[:4]


def _signature(recent: list[dict], hermes: dict) -> str:
    return hashlib.sha256(json.dumps([[r["id"], r["updated_at"], r["status"]] for r in recent] + [hermes.get("chats", [])], ensure_ascii=False).encode()).hexdigest()


def _ask_model(recent: list[dict], hermes: dict) -> list[dict] | None:
    from brain.lm_gateway import configured
    if not configured():
        return None
    from brain.llm import gateway_json
    system = ("You suggest what a person could do next in a video-editing assistant, from THEIR OWN recent work. Return only JSON "
              '{"suggestions":[{"label":"short button text, max 7 words","prompt":"what to send to the assistant, one or two sentences","for":"conversation id when it continues one of the listed edits, else empty"}]}. '
              "Exactly 4 suggestions, different from each other: (1) finish or fix the most recent edit that is waiting or failed, if any; (2) a new variation or a next piece "
              "based on a finished edit; (3) one from their InstaGPT chat topics if any are listed; (4) one general useful idea fitting what they usually make. "
              "Write in Persian unless their titles are mostly English. Use only facts in the data; never invent products, numbers or names.")
    data = {"recent_edits": [{"id": r["id"], "title": r["title"], "kind": r["kind_label"], "state": r["status_label"]} for r in recent[:6]],
            "instagpt_chat_topics": hermes.get("chats", [])[:4]}
    try:
        answer, _ = gateway_json(system, json.dumps(data, ensure_ascii=False), "intent_classification", 700)
    except Exception as exc:
        log.info("suggestions from the model failed: %s", type(exc).__name__)
        return None
    known = {r["id"] for r in recent}
    out = []
    for item in (answer.get("suggestions") or [])[:4] if isinstance(answer, dict) else []:
        label, prompt = str(item.get("label") or "").strip()[:80], str(item.get("prompt") or "").strip()[:400]
        if not label or not prompt:
            continue
        target = str(item.get("for") or "")
        out.append({"kind": "open", "label": label, "conversation_id": target, "reason": ""} if target in known else {"kind": "prompt", "label": label, "prompt": prompt, "reason": ""})
    return out if len(out) >= 3 else None


async def suggestions(user_key: str, recent: list[dict], hermes: dict) -> list[dict]:
    import asyncio
    key = _signature(recent, hermes)
    cached = _CACHE.get(user_key)
    if cached and cached[0] == key and cached[1] > time.monotonic():
        return cached[2]
    found = await asyncio.to_thread(_ask_model, recent, hermes) if recent or hermes.get("chats") else None
    result = found or fallback_suggestions(recent, hermes)
    if found:
        _CACHE[user_key] = (key, time.monotonic() + CACHE_SECONDS, result)
        if len(_CACHE) > 500:
            _CACHE.pop(next(iter(_CACHE)))
    return result


async def build(user_key: str) -> dict:
    from app.studio_store import repo
    conversations = (await repo.list_conversations(user_key))[:8]
    by_id = await _projects_by_conversation([c["id"] for c in conversations])
    import asyncio
    motions = await asyncio.gather(*(asyncio.to_thread(_motion_view, user_key, c) for c in conversations))
    recent = [summarize(c, by_id.get(c["id"], []), m) for c, m in zip(conversations, motions)]
    recent = [r for r in recent if not (r["kind"] == "chat" and r["status"] == "draft")][:6] or recent[:3]          # a chat nothing was made in is not "work"
    hermes = await hermes_state(user_key)
    return {"recent": recent, "suggestions": await suggestions(user_key, recent, hermes), "instagpt": {**instagram_summary(hermes), "chats": hermes["chats"][:3]}}
