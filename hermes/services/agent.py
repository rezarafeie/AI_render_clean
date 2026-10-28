"""The Hermes Instagram agent: reads the connected account, understands it, asks what it cannot know, proposes content for the editor's engines,
and learns from what was made and published. Everything is stored per user (one JSON state row), so the page never depends on a live call.

Phases of one run: sync (profile, recent media through Composio, with retries) -> analyze (profile score, content audit, strategy; questions when something
is missing) -> propose (ideas and scripts per editor engine, each with the brief the editor produces from). A person approves a proposal; the editor
makes it; the result waits in the publish queue. Reading other accounts and trends depends on what the person gives (handles, pasted posts): those
sources are not read automatically yet, and the agent says so instead of inventing them.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from uuid import uuid4

from fastapi import HTTPException

from hermes.config import settings_row_id
from hermes.database import get_row, save_row
from hermes.security import utcnow
from hermes.services import composio_account, skills

log = logging.getLogger(__name__)
PROVIDER = "agent"
MAX_PROPOSALS = 24
ENGINES = {
    "talking": "صحبتی: گوینده جلوی دوربین، برش و زیرنویس، پنل‌های موشن (مناسب آموزش، نظر شخصی، داستان)",
    "explainer": "اکسپلینر: ویدیوی توضیحی با موشن‌گرافیک و روایت صوتی (مناسب مفاهیم، مقایسه، فرایند)",
}
STEPS = ("sync", "analyze", "propose")


def _empty() -> dict:
    return {"version": 1, "answers": {}, "competitors": [], "profile": None, "media": [], "analysis": None, "questions": [], "proposals": [],
            "run": {"status": "idle", "step": None, "error": None, "started_at": None, "finished_at": None}, "history": []}


async def load(user_id: str) -> dict:
    row = await get_row("settings", settings_row_id(user_id, PROVIDER))
    if row and str(row["user_id"]) != str(user_id):
        raise HTTPException(404, detail={"code": "AGENT_NOT_FOUND"})
    state = _empty()
    state.update((row or {}).get("encrypted_credentials") or {})
    return state


async def save(user_id: str, state: dict) -> None:
    row_id = settings_row_id(user_id, PROVIDER)
    row = await get_row("settings", row_id)
    now = utcnow()
    await save_row("settings", {"id": row_id, "user_id": int(user_id) if str(user_id).isdigit() else user_id, "provider": PROVIDER,
                                "encrypted_credentials": state, "created_at": row["created_at"] if row else now, "updated_at": now})


def public(state: dict) -> dict:
    """What the page needs; the raw media snapshot is trimmed."""
    return {**{k: state.get(k) for k in ("answers", "competitors", "profile", "analysis", "questions", "proposals", "run", "history")},
            "media": (state.get("media") or [])[:12], "engines": ENGINES}


async def _with_retries(call, attempts: int = 3):
    for attempt in range(attempts):
        try:
            return await call()
        except HTTPException as exc:
            if exc.status_code not in (429, 502, 503, 504) or attempt == attempts - 1:
                raise
            await asyncio.sleep(2 + attempt * 3)


async def sync(user_id: str, state: dict) -> None:
    composio_account.forget(user_id)
    row = await _with_retries(lambda: composio_account.account(user_id, fresh=True))
    if not row:
        raise HTTPException(409, detail={"code": "AGENT_NO_ACCOUNT"})
    state["profile"] = {k: row.get(k) for k in ("username", "followers", "follows", "media_count", "ig_user_id")}
    try:
        state["media"] = (await _with_retries(lambda: composio_account.posts(user_id, strict=True)))[:50]
    except HTTPException:
        state["media"] = state.get("media") or []
        state["questions"] = [q for q in state.get("questions", []) if q["id"] != "media_unavailable"] + [{
            "id": "media_unavailable", "kind": "info", "text": "نتوانستم پست‌های اخیر را از اینستاگرام بخوانم (اتصال به Composio ناپایدار بود). دوباره تلاش می‌کنم؛ تا آن موقع تحلیل محتوا محدود است."}]


def _json(system: str, payload: dict, tokens: int = 6000) -> dict:
    return skills._complete(system, json.dumps(payload, ensure_ascii=False)[:60_000], None)


ANALYZE_SCHEMA = ('{"profile": {"score": int 0-100, "parts": [{"part": str, "score": int, "note": str, "rewrite": str}]}, '
                  '"content": {"top": [{"post": str, "why": str}], "weak": [{"post": str, "why": str}], "patterns": [str], "do_more": [str], "stop": [str]}, '
                  '"strategy": {"niche": str, "audience": str, "pillars": [str], "format_mix": str}, '
                  '"questions": [{"id": str, "kind": "text|handles|choice", "text": str}], "data_gaps": [str]}')


async def analyze(user_id: str, state: dict) -> None:
    system = ("You are Hermes, an Instagram strategist. Study the account with the two skills below, using ONLY the data given (profile counts, recent posts with likes/"
              "comments, the person's answers). When the data is thin say so in data_gaps and ask the questions you need (niche, goal, audience, competitors as "
              "@handles) in questions; never invent metrics or posts. Persian output.\n\n=== ig-profile ===\n" + skills._skill_text("profile")[:6000]
              + "\n\n=== ig-audit ===\n" + skills._skill_text("audit")[:6000] + f"\n\nReturn ONLY JSON: {ANALYZE_SCHEMA}")
    result = await asyncio.to_thread(_json, system, {"profile": state.get("profile"), "recent_posts": state.get("media"), "answers": state.get("answers"),
                                                    "competitors": state.get("competitors")})
    state["analysis"] = {k: result.get(k) for k in ("profile", "content", "strategy", "data_gaps")} | {"at": utcnow()}
    keep = [q for q in state.get("questions", []) if q.get("kind") == "info"]
    answered = set(state.get("answers", {}))
    state["questions"] = keep + [q for q in (result.get("questions") or []) if isinstance(q, dict) and q.get("id") and q["id"] not in answered][:5]


PROPOSE_SCHEMA = ('{"proposals": [{"title": str, "engine": "talking|explainer", "format": "reel", "why": str, "hook": str, "script": str, "caption": str, '
                  '"hashtags": [str], "editor_brief": str, "length_seconds": int}]}')


async def propose(user_id: str, state: dict, count: int = 4) -> None:
    system = ("You are Hermes writing Instagram reel proposals for EditorGPT's production engines. Base every proposal on the analysis and the person's answers (their "
              "niche, audience, what worked, what to stop). Each proposal names the engine that should make it: " + "; ".join(f"{k} = {v}" for k, v in ENGINES.items())
              + ". Use the hook formulas and structure of this skill, and write Persian spoken script (short sentences, no machine phrasing). editor_brief is one "
              "paragraph the editor can produce the video from (topic, angle, structure, tone, call to action). Do not repeat earlier proposals.\n\n=== ig-reel ===\n"
              + skills._skill_text("reel")[:9000] + f"\n\nReturn ONLY JSON: {PROPOSE_SCHEMA} with exactly {count} proposals.")
    earlier = [{"title": p["title"], "status": p["status"]} for p in state.get("proposals", [])][-12:]
    result = await asyncio.to_thread(_json, system, {"profile": state.get("profile"), "analysis": state.get("analysis"), "answers": state.get("answers"),
                                                    "earlier": earlier, "recent_posts": (state.get("media") or [])[:15]})
    for item in (result.get("proposals") or [])[:count]:
        if not isinstance(item, dict) or not item.get("title") or not (item.get("script") or item.get("editor_brief")):
            continue
        checks = {}
        try:
            from hermes.services.instagram_quality import evaluate
            if item.get("hook"):
                checks["hook"] = evaluate("hook", str(item["hook"]), "fa")
            if item.get("script"):
                checks["beats"] = evaluate("beats", str(item["script"]), "fa", wpm=150)
        except Exception:
            pass
        state["proposals"].append({"id": uuid4().hex[:12], "status": "proposed", "created_at": utcnow(), "checks": checks,
                                   "engine": item.get("engine") if item.get("engine") in ENGINES else "talking",
                                   **{k: item.get(k) for k in ("title", "why", "hook", "script", "caption", "hashtags", "editor_brief", "length_seconds")}})
    state["proposals"] = state["proposals"][-MAX_PROPOSALS:]


async def run(user_id: str, steps: tuple[str, ...] = STEPS, count: int = 4) -> None:
    """One agent pass; progress and the failing step are written to the state after every step so the page can show them."""
    state = await load(user_id)
    state["run"] = {"status": "running", "step": steps[0], "error": None, "started_at": utcnow(), "finished_at": None}
    await save(user_id, state)
    try:
        for step in steps:
            state["run"]["step"] = step
            await save(user_id, state)
            if step == "sync":
                await sync(user_id, state)
            elif step == "analyze":
                await analyze(user_id, state)
            elif step == "propose":
                await propose(user_id, state, count)
        state["run"].update(status="done", step=None, finished_at=utcnow())
        state["history"] = (state.get("history") or [])[-19:] + [{"at": utcnow(), "steps": list(steps)}]
    except HTTPException as exc:
        state["run"].update(status="error", error=str(exc.detail.get("code") if isinstance(exc.detail, dict) else exc.detail), finished_at=utcnow())
    except Exception as exc:
        log.warning("agent run failed at %s: %s", state["run"].get("step"), type(exc).__name__)
        state["run"].update(status="error", error=f"{type(exc).__name__}", finished_at=utcnow())
    await save(user_id, state)


async def set_status(user_id: str, proposal_id: str, status: str, **extra) -> dict:
    state = await load(user_id)
    for item in state["proposals"]:
        if item["id"] == proposal_id:
            item.update(status=status, updated_at=utcnow(), **extra)
            await save(user_id, state)
            return item
    raise HTTPException(404, detail={"code": "PROPOSAL_NOT_FOUND"})


async def answer(user_id: str, key: str, value) -> dict:
    state = await load(user_id)
    state["answers"][key[:40]] = value if not isinstance(value, str) else value[:2000]
    if key == "competitors" or key.endswith("handles"):
        state["competitors"] = [h.strip().lstrip("@")[:60] for h in str(value).replace("\n", ",").split(",") if h.strip()][:10]
    state["questions"] = [q for q in state["questions"] if q.get("id") != key]
    await save(user_id, state)
    return state


CHAT_SCHEMA = '{"reply": str, "suggestions": [str], "action": null | {"type": "run_agent"|"open_tab", "tab": "overview|content|analytics|settings"}}'


async def chat(user_id: str, message: str, page: dict | None, history: list[dict] | None) -> dict:
    """The agent talks with the person about what is on their screen. It sees the agent state and the text the open page gave it (page.title / page.text)."""
    state = await load(user_id)
    brief = {"profile": state.get("profile"), "strategy": (state.get("analysis") or {}).get("strategy"), "profile_score": ((state.get("analysis") or {}).get("profile") or {}).get("score"),
             "data_gaps": (state.get("analysis") or {}).get("data_gaps"), "open_questions": [q.get("text") for q in state.get("questions", []) if q.get("kind") != "info"],
             "proposals": [{"title": p.get("title"), "engine": p.get("engine"), "status": p.get("status")} for p in state.get("proposals", [])[-8:]],
             "recent_posts": [{"caption": (m.get("caption") or "")[:100], "likes": m.get("likes"), "comments": m.get("comments")} for m in (state.get("media") or [])[:10]]}
    system = ("You are Hermes, the Instagram agent inside EditorGPT's Instagram studio. Talk Persian, short and concrete. The person is looking at the page described in PAGE; "
              "answer about what they see first, using AGENT (what you know about their account) for context. Never invent numbers or posts; say what is missing. "
              "You can suggest running a new analysis (action run_agent) or opening a tab (action open_tab), only when it helps. "
              f"Return ONLY JSON: {CHAT_SCHEMA}")
    payload = {"agent": brief, "page": {"title": str((page or {}).get("title") or "")[:120], "text": str((page or {}).get("text") or "")[:6000]},
               "history": [{"role": h.get("role"), "text": str(h.get("text") or "")[:1500]} for h in (history or [])[-8:]], "message": message[:4000]}
    result = await asyncio.to_thread(lambda: skills._complete(system, json.dumps(payload, ensure_ascii=False), route="hermes_chat", tokens=2500))
    action = result.get("action") if isinstance(result.get("action"), dict) and result["action"].get("type") in ("run_agent", "open_tab") else None
    return {"reply": str(result.get("reply") or "")[:4000], "suggestions": [str(x)[:120] for x in (result.get("suggestions") or [])][:4], "action": action}
