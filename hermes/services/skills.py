"""The 13 skills of instagram-agent-skill (MIT, vendor/instagram-agent-skill) as Hermes actions.

Each skill's own SKILL.md is the instruction of the model call; the account facts come from the person's Composio connection (profile and recent media,
read-only) when it exists, and the local checks of the skill (hook score, beats timing, caption lint, AI-sound audit) run on what the model wrote.
Nothing here publishes or messages anyone: results are drafts the person reviews, sends to the editor, or copies.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from fastapi import HTTPException

from hermes.services import composio_account

SKILL_DIR = Path(__file__).resolve().parents[2] / "vendor" / "instagram-agent-skill" / "skills"

# id -> (group, label, what to give it, produces a video brief, needs the account)
SKILLS: dict[str, dict] = {
    "profile": {"group": "understand", "label": "امتیاز پروفایل", "hint": "بیو، لینک و هایلایت‌ها را بچسبانید (یا خالی بگذارید تا از حساب وصل‌شده خوانده شود)", "video": False, "account": True},
    "audit": {"group": "understand", "label": "بازبینی محتوای قبلی", "hint": "اگر خالی بگذارید، پست‌های اخیر حساب وصل‌شده با آمارشان بررسی می‌شود", "video": False, "account": True},
    "viral": {"group": "understand", "label": "بنچمارک رقبا و فایل ایده (ig-viral)", "hint": "جدول ریلزهای رقبا را با تب بچسبانید: account، followers، median، views، hook (یک ریلز در هر سطر) تا رتبه‌بندی بر پایهٔ «چند برابر میانهٔ همان پیج» انجام شود؛ یا فقط هندل رقبا و توضیح نیش را بنویسید. جمع‌آوری خودکار از اینستاگرام انجام نمی‌شود (قانون خود اسکیل)", "video": False, "account": True},
    "plan": {"group": "plan", "label": "برنامه‌ی هفته", "hint": "موضوع، مخاطب و تعداد پست در هفته", "video": False, "account": True},
    "reel": {"group": "create", "label": "ریلز: هوک، متن و بیت‌ها", "hint": "ایده‌ی خام ریلز", "video": True, "account": True},
    "carousel": {"group": "create", "label": "کاروسل", "hint": "ایده یا فهرستی که باید کاروسل شود", "video": False, "account": True},
    "story": {"group": "create", "label": "سکانس استوری", "hint": "هدف امروز استوری (فروش، تعامل، ...)", "video": False, "account": True},
    "caption": {"group": "create", "label": "کپشن و هشتگ", "hint": "موضوع پست یا متن ریلز", "video": False, "account": True},
    "repurpose": {"group": "create", "label": "یک محتوای بلند را به ریلزها تقسیم کن", "hint": "متن پادکست/ویدیو/مقاله", "video": True, "account": False},
    "comment": {"group": "engage", "label": "کامنت برای پست دیگران", "hint": "متن پست یا ریلز مقصد", "video": False, "account": False},
    "reply": {"group": "engage", "label": "پاسخ به کامنت‌های خودم", "hint": "کامنت‌ها را بچسبانید", "video": False, "account": True},
    "dm": {"group": "engage", "label": "دایرکت و پیگیری", "hint": "به چه کسی و برای چه هدفی", "video": False, "account": False},
    "human": {"group": "quality", "label": "طبیعی‌کردن متن", "hint": "متنی که ماشینی به نظر می‌رسد", "video": False, "account": False},
}
FOLDER = {"profile": "ig-profile", "audit": "ig-audit", "viral": "ig-viral", "plan": "ig-plan", "reel": "ig-reel", "carousel": "ig-carousel", "story": "ig-story",
          "caption": "ig-caption", "repurpose": "ig-repurpose", "comment": "ig-comment", "reply": "ig-reply", "dm": "ig-dm", "human": "ig-human"}
SCHEMA = ('{"title": str, "summary": str, "sections": [{"heading": str, "body": str, "items": [str]}], "hooks": [str], "script": str, "caption": str, '
          '"hashtags": [str], "editor_brief": str, "next_steps": [str]}  (omit keys that do not apply; "editor_brief" is one paragraph an editor can produce a video from)')


# the result keys each skill is expected to fill; everything else is left out so the page shows only what belongs to the skill
KEYS = {"profile": "title, summary, sections, next_steps", "audit": "title, summary, sections, next_steps", "viral": "title, summary, sections, hooks, next_steps",
        "plan": "title, summary, sections, next_steps", "reel": "title, hooks, script, caption, hashtags, editor_brief, next_steps",
        "carousel": "title, summary, sections, caption, hashtags, editor_brief", "story": "title, sections, next_steps",
        "caption": "title, caption, hashtags", "repurpose": "title, summary, sections, hooks, editor_brief, next_steps",
        "comment": "title, sections", "reply": "title, sections", "dm": "title, sections, next_steps", "human": "title, script, summary"}


def swipe_from_text(text: str) -> dict | None:
    """The deterministic half of ig-viral: a pasted tab-separated table of reels (account, followers, median, views, hook) is ranked by how far each beat its OWN account's
    baseline and each hook is named by the skill's formulas (the skill's own swipe.py). None when the text holds no such table."""
    if "\t" not in (text or ""):
        return None
    import importlib.util
    import tempfile
    path = SKILL_DIR / "ig-viral" / "swipe.py"
    try:
        spec = importlib.util.spec_from_file_location("ig_viral_swipe", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)                     # type: ignore[union-attr]
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8") as handle:
            handle.write(text)
            name = handle.name
        try:
            rows = module.read_rows(name)
        finally:
            os.unlink(name)
        if len(rows) < 2:
            return None
        formulas = module.load_formulas(str(SKILL_DIR / "ig-reel" / "hooks.json"))
        analysis = module.analyse(rows, formulas)
    except Exception:
        return None
    reels = [{k: r.get(k) for k in ("account", "followers", "median", "views", "hook", "outlier", "formula", "words", "hook_score")} for r in analysis["reels"][:60]]
    return {**{k: analysis[k] for k in ("baseline", "n", "accounts", "top_formulas", "top_hook_score", "bottom_hook_score", "top_words", "bottom_words", "unclassified")}, "reels": reels,
            "confidence": ("کافی برای نتیجه‌گیری" if analysis["n"] >= 40 and analysis["accounts"] >= 6 else "نمونهٔ کم؛ فقط نشانه است، نه حکم")}


def catalog() -> list[dict]:
    return [{"id": key, **{k: v for k, v in spec.items()}} for key, spec in SKILLS.items()]


def _skill_text(skill: str) -> str:
    text = (SKILL_DIR / FOLDER[skill] / "SKILL.md").read_text(encoding="utf-8")
    return re.sub(r"\A---.*?---\s*", "", text, flags=re.S)[:14_000]


async def _account_context(user_id: str, wants: bool) -> dict:
    if not wants:
        return {}
    row = await composio_account.account(user_id)
    if not row:
        return {}
    media = []
    try:
        media = (await composio_account.posts(user_id))[:20]
    except HTTPException:
        pass
    return {"profile": {k: row.get(k) for k in ("username", "followers", "follows", "media_count")}, "recent_posts": media}


def _checks(skill: str, result: dict, language: str) -> dict:
    """The skill's own local checks on what the model wrote (hook score, beats, caption lint, how machine-like it sounds)."""
    from hermes.services.instagram_quality import evaluate
    out: dict = {}
    try:
        hooks = [h for h in (result.get("hooks") or []) if isinstance(h, str)][:5]
        if skill == "reel" and hooks:
            out["hooks"] = [{"hook": h, "check": evaluate("hook", h, language)} for h in hooks]
        if skill == "reel" and isinstance(result.get("script"), str) and result["script"].strip():
            out["beats"] = evaluate("beats", result["script"], language, wpm=150)
        if isinstance(result.get("caption"), str) and result["caption"].strip():
            out["caption"] = evaluate("caption", result["caption"], language)
        body = " ".join(filter(None, [result.get("script"), result.get("caption")]))
        if body.strip():
            out["sounds_like_ai"] = evaluate("audit_text", body, language)
    except Exception:
        pass                                              # checks are an aid; the draft is still returned
    return out


HERMES_ROUTE = "hermes_agent"      # brain/lm_tasks.py: the models and their order are set in the application's AI settings


def _complete(system: str, user: str, model: str | None = None, *, route: str = HERMES_ROUTE, tokens: int = 6000):
    """Through the platform's LM router (the Hermes tasks of the AI settings, then the gateway's direct fallbacks); no model is chosen here."""
    from brain.llm import gateway_json
    try:
        data, _usage = gateway_json(system, user, route, tokens)
    except Exception as exc:
        raise HTTPException(502, detail={"code": "HERMES_AI_UNAVAILABLE"}) from exc
    if not isinstance(data, dict):
        raise HTTPException(502, detail={"code": "SKILL_INVALID_RESPONSE"})
    return data


async def run(user_id: str, skill: str, text: str, language: str = "fa", options: dict | None = None) -> dict:
    if skill not in SKILLS:
        raise HTTPException(404, detail={"code": "SKILL_NOT_FOUND"})
    spec = SKILLS[skill]
    ranked = await asyncio.to_thread(swipe_from_text, text) if skill == "viral" else None
    if skill == "viral" and not ranked:
        # Without the competitors' reels there is nothing to benchmark; a generic answer from the person's own page would pass for one. Say what is needed.
        raise HTTPException(422, detail="برای بنچمارک رقبا جدول ریل‌های رقبا لازم است. آن را در کادر بچسبانید (ستون‌ها با تب جدا: پیج، فالوور، میانه، بازدید، هوک). اتصال اینستاگرام از طریق Composio فقط پیج خودتان را می‌خواند، پس هرمس خودش ریل رقبا را پیدا نمی‌کند.")
    context = await _account_context(user_id, spec["account"])
    if spec["account"] and not text.strip() and not context:
        raise HTTPException(422, detail={"code": "SKILL_NEEDS_INPUT_OR_ACCOUNT"})
    voice = "Persian (Farsi), natural spoken style" if language == "fa" else "English"
    system = (f"You are Hermes, an Instagram strategist and writer. Follow this skill definition exactly.\n\n{_skill_text(skill)}\n\n"
              f"Write for the person in {voice}. Use only the facts given; never invent metrics, quotes or results. If account data is absent, say what is missing. "
              f"Return ONLY JSON in this shape: {SCHEMA}. For this skill fill ONLY these keys: {KEYS[skill]} (leave every other key out).")
    payload = {"request": text[:12_000], "options": options or {}, "account": context}
    if ranked:
        payload["ranked_by_the_skills_own_script"] = ranked           # computed, not guessed: the findings must rest on these numbers and say how big the sample is
        system += ("\n\nThe person pasted a table of reels. `ranked_by_the_skills_own_script` is its exact ranking (outlier multiple over each account's own baseline, formulas named, "
                   "hook scores). Base every finding on it, state the sample size and the confidence in plain words, and list the unclassified hooks to read by hand.")
    user = json.dumps(payload, ensure_ascii=False)
    result = await asyncio.to_thread(_complete, system, user)
    if not isinstance(result, dict):
        raise HTTPException(502, detail={"code": "SKILL_INVALID_RESPONSE"})
    checks = await asyncio.to_thread(_checks, skill, result, language)
    if ranked:
        checks["swipe"] = ranked
    if skill == "viral":
        await _remember_benchmark(user_id, text, result, ranked)
    return {"skill": skill, "result": result, "checks": checks, "account_used": bool(context),
            "can_produce": spec["video"] or bool(result.get("editor_brief"))}


async def _remember_benchmark(user_id: str, text: str, result: dict, ranked: dict | None) -> None:
    """What the benchmark found is kept with the person's Hermes agent, so the ideas it proposes later are grounded in it (formulas that over-index, what the top third share)."""
    try:
        from hermes.services import agent
        state = await agent.load(user_id)
        state["benchmark"] = {"at": agent.utcnow(), "summary": str(result.get("summary") or "")[:800], "hooks": [h for h in (result.get("hooks") or []) if isinstance(h, str)][:12],
                              "findings": [{"heading": str(x.get("heading") or ""), "body": str(x.get("body") or "")[:600], "items": [str(i)[:200] for i in (x.get("items") or [])[:8]]}
                                           for x in (result.get("sections") or []) if isinstance(x, dict)][:6],
                              "top_formulas": (ranked or {}).get("top_formulas", [])[:6], "sample": {"reels": (ranked or {}).get("n"), "accounts": (ranked or {}).get("accounts"),
                                                                                                    "confidence": (ranked or {}).get("confidence")},
                              "input": text[:1500]}
        if ranked:
            state["benchmark_input"] = text[:20_000]       # kept whole so the refresh can re-rank it without asking the model again
        await agent.save(user_id, state)
    except Exception:
        pass                                              # remembering is an aid: the result is still returned
