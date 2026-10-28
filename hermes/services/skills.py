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

from brain.llm import chat_json
from hermes.services import composio_account

SKILL_DIR = Path(__file__).resolve().parents[2] / "vendor" / "instagram-agent-skill" / "skills"

# id -> (group, label, what to give it, produces a video brief, needs the account)
SKILLS: dict[str, dict] = {
    "profile": {"group": "understand", "label": "امتیاز پروفایل", "hint": "بیو، لینک و هایلایت‌ها را بچسبانید (یا خالی بگذارید تا از حساب وصل‌شده خوانده شود)", "video": False, "account": True},
    "audit": {"group": "understand", "label": "بازبینی محتوای قبلی", "hint": "اگر خالی بگذارید، پست‌های اخیر حساب وصل‌شده با آمارشان بررسی می‌شود", "video": False, "account": True},
    "viral": {"group": "understand", "label": "فایل ایده از ویدیوهای موفق", "hint": "لینک یا متن ریلزهای رقیب/نیش را بچسبانید؛ جستجوی خودکار اینستاگرام در این نسخه نیست", "video": False, "account": False},
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


def _complete(system: str, user: str, model: str | None):
    """The platform's LM gateway (the route the creative director uses) first, then the Hermes advisor's own provider."""
    try:
        from brain.llm import gateway_json
        from creative import llm as creative_llm
        if creative_llm.configured():
            data, _usage = gateway_json(system, user, creative_llm.DIRECTOR_ROUTE, 6000)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    data, _usage = chat_json(system, user, max_tokens=4500, temperature=0.4, model=model)
    return data


async def run(user_id: str, skill: str, text: str, language: str = "fa", options: dict | None = None) -> dict:
    if skill not in SKILLS:
        raise HTTPException(404, detail={"code": "SKILL_NOT_FOUND"})
    spec = SKILLS[skill]
    context = await _account_context(user_id, spec["account"])
    if spec["account"] and not text.strip() and not context:
        raise HTTPException(422, detail={"code": "SKILL_NEEDS_INPUT_OR_ACCOUNT"})
    voice = "Persian (Farsi), natural spoken style" if language == "fa" else "English"
    system = (f"You are Hermes, an Instagram strategist and writer. Follow this skill definition exactly.\n\n{_skill_text(skill)}\n\n"
              f"Write for the person in {voice}. Use only the facts given; never invent metrics, quotes or results. If account data is absent, say what is missing. "
              f"Return ONLY JSON in this shape: {SCHEMA}")
    user = json.dumps({"request": text[:12_000], "options": options or {}, "account": context}, ensure_ascii=False)
    model = os.environ.get("HERMES_LLM_MODEL")
    result = await asyncio.to_thread(_complete, system, user, model)
    if not isinstance(result, dict):
        raise HTTPException(502, detail={"code": "SKILL_INVALID_RESPONSE"})
    return {"skill": skill, "result": result, "checks": await asyncio.to_thread(_checks, skill, result, language), "account_used": bool(context),
            "can_produce": spec["video"] or bool(result.get("editor_brief"))}
