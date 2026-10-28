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
from datetime import datetime, timezone
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
    return {"version": 1, "answers": {}, "competitors": [], "profile": None, "media": [], "analysis": None, "questions": [], "proposals": [], "prefs": {"talking_share": 50},
            "run": {"status": "idle", "step": None, "error": None, "started_at": None, "finished_at": None}, "history": []}


STALE_AFTER = 600          # seconds without a write: the process that ran the review is gone (a restart), not slow


def _age(stamp) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(str(stamp))).total_seconds()
    except (TypeError, ValueError):
        return 0.0


def _expire(state: dict) -> None:
    """A review recorded as running whose writer stopped (the service was restarted) must not block the button forever."""
    run = state.get("run") or {}
    if run.get("status") == "running" and _age(run.get("updated_at") or run.get("started_at")) > STALE_AFTER:
        state["run"] = {**run, "status": "error", "error": "AGENT_INTERRUPTED", "finished_at": utcnow()}


async def load(user_id: str) -> dict:
    row = await get_row("settings", settings_row_id(user_id, PROVIDER))
    if row and str(row["user_id"]) != str(user_id):
        raise HTTPException(404, detail={"code": "AGENT_NOT_FOUND"})
    state = _empty()
    state.update((row or {}).get("encrypted_credentials") or {})
    _expire(state)
    return state


async def save(user_id: str, state: dict) -> None:
    row_id = settings_row_id(user_id, PROVIDER)
    row = await get_row("settings", row_id)
    now = utcnow()
    if (state.get("run") or {}).get("status") == "running":
        state["run"]["updated_at"] = now
    await save_row("settings", {"id": row_id, "user_id": int(user_id) if str(user_id).isdigit() else user_id, "provider": PROVIDER,
                                "encrypted_credentials": state, "created_at": row["created_at"] if row else now, "updated_at": now})


def public(state: dict) -> dict:
    """What the page needs; the raw media snapshot is trimmed."""
    return {**{k: state.get(k) for k in ("answers", "competitors", "profile", "analysis", "questions", "proposals", "run", "history", "prefs")},
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


TALKING_SCHEMA = ('{"proposals": [{"title": str, "why": str, "hook": str, "script": str, "on_screen": [str], "shooting_tips": [str], "caption": str, "hashtags": [str], '
                  '"length_seconds": int}]}')
EXPLAINER_SCHEMA = ('{"proposals": [{"title": str, "concept": str, "why": str, "hook": str, "style": str, "mood": str, "music": str, '
                    '"scenes": [{"seconds": number, "visual": str, "on_screen_text": str, "narration": str}], "script": str, "cta": str, "caption": str, '
                    '"hashtags": [str], "editor_brief": str, "length_seconds": int}]}')


def _share(state: dict) -> int:
    try:
        return max(0, min(100, int((state.get("prefs") or {}).get("talking_share", 50))))
    except (TypeError, ValueError):
        return 50


def _split(count: int, share: int) -> tuple[int, int]:
    talking = round(count * share / 100)
    return talking, count - talking


def _context(state: dict, count: int) -> dict:
    earlier = [{"title": p["title"], "status": p["status"]} for p in state.get("proposals", [])][-12:]
    return {"profile": state.get("profile"), "analysis": state.get("analysis"), "answers": state.get("answers"), "earlier": earlier,
            "recent_posts": (state.get("media") or [])[:15], "count": count}


TALKING_SYSTEM = ("You are Hermes writing TALKING reels for an Instagram creator who will film themselves. Base every idea on the analysis and the person's answers (niche, "
                  "audience, what worked, what to stop). `script` is the COMPLETE spoken text, word for word, ready to read to camera: natural Persian speech, short sentences, "
                  "no machine phrasing, opening with the hook and ending with one clear call to action; target the length_seconds at about 150 words per minute. `hook` is the "
                  "first line only. `on_screen` lists the few key words/phrases to show as captions or panels. `shooting_tips` are 2-3 concrete tips (framing, energy, pauses). "
                  "Use the hook formulas and structure of this skill. Do not repeat earlier proposals.\n\n=== ig-reel ===\n")

EXPLAINER_SYSTEM = ("You are Hermes, a creative director for viral Instagram reels that EditorGPT PRODUCES from scratch (no one films anything): voiced explainer / story / "
                    "motion videos with a narrator, animated visuals, on-screen text and music. Each idea must be scroll-stopping, emotionally engaging and shareable, not a dry "
                    "explainer. For every idea give: `concept` (the one-sentence big idea and the twist that makes people watch to the end); `hook` (what is said AND shown in the "
                    "first 2 seconds, a pattern interrupt or a bold claim); `style` (a concrete visual language: e.g. bold kinetic typography on warm paper texture, cinematic "
                    "macro product shots, hand-drawn infographic, split-screen comparison; name colors, type, motion feel); `mood` (the feeling, e.g. urgent, curious, nostalgic, "
                    "reflective, triumphant); `music` (genre and energy curve); `scenes` (5-9 beats, each with seconds, what we SEE, the exact on-screen text in Persian, and the "
                    "narration line); `script` (the complete narration, Persian, spoken-natural, short sentences, built around ONE story or tension with a payoff, ending on a "
                    "loop or a call to action); `cta`; `editor_brief` (a paragraph a video editor can produce from: topic, angle, structure, tone, pacing, look). Vary the styles "
                    "and moods between ideas. Use the hook formulas and structure of this skill. Do not repeat earlier proposals.\n\n=== ig-reel ===\n")


async def _propose_batch(state: dict, engine: str, count: int) -> list[dict]:
    if count <= 0:
        return []
    system = (TALKING_SYSTEM if engine == "talking" else EXPLAINER_SYSTEM) + skills._skill_text("reel")[:9000] \
        + f"\n\nReturn ONLY JSON: {TALKING_SCHEMA if engine == 'talking' else EXPLAINER_SCHEMA} with exactly {count} proposals."
    result = await asyncio.to_thread(_json, system, _context(state, count))
    return [item for item in (result.get("proposals") or [])[:count] if isinstance(item, dict) and item.get("title") and (item.get("script") or item.get("editor_brief"))]


async def _write_batch(user_id: str, state: dict, engine: str, count: int) -> None:
    """One kind of idea: written, stored and saved as soon as it is ready, so the page shows it while the other kind is still being written."""
    for item in await _propose_batch(state, engine, count):
        checks = {}
        try:
            from hermes.services.instagram_quality import evaluate
            if item.get("hook"):
                checks["hook"] = evaluate("hook", str(item["hook"]), "fa")
            if item.get("script"):
                checks["beats"] = evaluate("beats", str(item["script"]), "fa", wpm=150)
        except Exception:
            pass
        keys = ("title", "why", "hook", "script", "caption", "hashtags", "editor_brief", "length_seconds", "on_screen", "shooting_tips", "concept", "style", "mood", "music", "scenes", "cta")
        state["proposals"].append({"id": uuid4().hex[:12], "status": "proposed", "created_at": utcnow(), "checks": checks, "engine": engine, **{k: item.get(k) for k in keys}})
        state["run"]["ideas"] = state["run"].get("ideas", 0) + 1
    state["proposals"] = state["proposals"][-MAX_PROPOSALS:]
    await save(user_id, state)


async def propose(user_id: str, state: dict, count: int = 4) -> None:
    talking, produced = _split(count, _share(state))
    results = await asyncio.gather(_write_batch(user_id, state, "talking", talking), _write_batch(user_id, state, "explainer", produced), return_exceptions=True)
    for engine, result in zip(("talking", "explainer"), results):
        if isinstance(result, Exception):
            log.warning("proposal batch %s failed: %s", engine, type(result).__name__)
    if all(isinstance(r, Exception) for r in results):
        raise results[0]                                            # nothing could be written: the run reports why


async def run(user_id: str, steps: tuple[str, ...] = STEPS, count: int = 4) -> None:
    """One agent pass; progress and the failing step are written to the state after every step so the page can show them."""
    state = await load(user_id)
    state["run"] = {"status": "running", "step": steps[0], "error": None, "started_at": utcnow(), "finished_at": None, "ideas": 0, "ideas_total": count if "propose" in steps else 0}
    await save(user_id, state)
    try:
        for step in steps:
            state["run"]["step"] = step
            await save(user_id, state)
            if step == "sync":
                await sync(user_id, state)
                state["run"]["posts"] = len(state.get("media") or [])
            elif step == "analyze":
                await analyze(user_id, state)
            elif step == "propose":
                await propose(user_id, state, count)
            await save(user_id, state)                 # whatever this step produced is on the page before the next one starts
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


async def set_prefs(user_id: str, talking_share: int) -> dict:
    state = await load(user_id)
    state["prefs"] = {**(state.get("prefs") or {}), "talking_share": max(0, min(100, int(talking_share)))}
    await save(user_id, state)
    return state


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
    consulted = [{"label": "خواندن محتوای صفحه‌ی باز", "tool": "page"}] if payload["page"]["text"] else []
    consulted.append({"label": "بررسی اطلاعات پیج و تحلیل ذخیره‌شده", "tool": "account"})
    return {"activity": consulted, "reply": str(result.get("reply") or "")[:4000], "suggestions": [str(x)[:120] for x in (result.get("suggestions") or [])][:4], "action": action}
