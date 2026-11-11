"""A cheap, deterministic read of a motion plan *before* any scene is authored: does it look like a slideshow?

Advisory by default. `PLAN_CHECKS` unset/off → nothing runs; `PLAN_CHECKS=1` → the score is logged and stored in the plan record;
the verdict never blocks a render and costs no model call. Written from this project's own plan fields and failure modes.
"""
from __future__ import annotations

import os
import re
from collections import Counter

DIMENSIONS = ("variety", "text_only", "pacing", "copy", "motion", "narration")

# Generic marketing filler that says nothing about the subject (Persian and English), lower-cased.
GENERIC_PHRASES = (
    "با ما همراه باشید", "بهترین کیفیت", "کیفیت بی‌نظیر", "کیفیت بی نظیر", "تجربه‌ای متفاوت", "تجربه ای متفاوت", "دنیای جدید",
    "همین امروز", "فرصت را از دست ندهید", "حرفه‌ای‌ترین", "نوآوری و خلاقیت", "ما بهترین هستیم",
    "welcome to", "world-class", "next level", "game changer", "cutting-edge", "state of the art", "don't miss out", "unlock the power",
)


def mode() -> str:
    """'off' (default), 'log' (score and record it)."""
    value = os.environ.get("PLAN_CHECKS", "").strip().lower()
    return "off" if value in {"", "0", "false", "off", "no"} else "log"


def enabled() -> bool:
    return mode() != "off"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _share_of_top(values: list[str]) -> float:
    values = [v for v in values if v]
    if not values:
        return 0.0
    return Counter(values).most_common(1)[0][1] / len(values)


def _scene_kind(scene) -> str:
    """What carries the scene visually: a native component, a shotcraft shot, or plain designed text."""
    if getattr(scene, "native_component", None):
        return "native:" + scene.native_component.resource_id
    if getattr(scene, "shotcraft_component", None) or getattr(scene, "shotcraft_id", ""):
        return "shot:" + (scene.shotcraft_id or "component")
    return ""


def score_plan(plan) -> dict:
    """{score 0-5, verdict ok|revise|fail|strong, dimensions {name: 0-5}, violations [text]}. Never raises: on error → ok."""
    try:
        return _score(plan)
    except Exception as exc:  # advisory tool: a bug here must never block a film
        return {"score": 5.0, "verdict": "ok", "dimensions": {}, "violations": [], "error": str(exc)[:200]}


def _score(plan) -> dict:
    scenes = list(getattr(plan, "scenes", None) or [])
    if len(scenes) < 3:
        return {"score": 5.0, "verdict": "ok", "dimensions": {}, "violations": []}
    dims: dict[str, float] = {}
    problems: list[str] = []

    kinds = [_scene_kind(s) for s in scenes]
    top = _share_of_top(kinds)
    transitions = [s.transition for s in scenes]
    heads = [_norm(s.headline) for s in scenes]
    v = 5.0
    if top > 0.5 and sum(1 for k in kinds if k) >= 3:
        v -= 2.0 + 2.0 * (top - 0.5)
        problems.append(f"{round(top * 100)}% of the visual scenes reuse the same layout/resource")
    if _share_of_top(transitions) > 0.6 and len(set(transitions)) <= 2:
        v -= 1.0
        problems.append("almost every scene enters the same way")
    if len(set(heads)) < len(heads):
        v -= 1.5
        problems.append("two scenes carry the same headline")
    dims["variety"] = max(0.0, v)

    plain = sum(1 for k in kinds if not k)
    ratio = plain / len(scenes)
    dims["text_only"] = 5.0 if ratio <= 0.4 else max(0.0, 5.0 - (ratio - 0.4) * 8.0)
    if ratio > 0.7:
        problems.append(f"{round(ratio * 100)}% of the scenes have no component, only text")

    lengths = [max(0.1, float(s.end) - float(s.start)) for s in scenes]
    mean = sum(lengths) / len(lengths)
    spread = (sum((x - mean) ** 2 for x in lengths) / len(lengths)) ** 0.5 / mean
    dims["pacing"] = 5.0 if spread >= 0.18 else max(0.0, 5.0 - (0.18 - spread) * 20.0)
    if spread < 0.08 and len(scenes) >= 4:
        problems.append("every scene has nearly the same length (metronome pacing)")

    text = " ".join(_norm(s.headline) + " " + _norm(s.narration) for s in scenes)
    hits = [p for p in GENERIC_PHRASES if p in text]
    dims["copy"] = max(0.0, 5.0 - 1.5 * len(hits))
    if hits:
        problems.append("generic filler copy: " + ", ".join(hits[:3]))

    moving = sum(1 for s in scenes if getattr(s, "native_component", None) or getattr(s, "shotcraft_component", None) or getattr(s, "shotcraft_id", ""))
    dims["motion"] = 5.0 if moving >= max(1, len(scenes) // 3) else 2.0
    if moving == 0:
        problems.append("no scene uses a motion component")

    spoken = [s for s in scenes if (s.narration or "").strip()]
    dims["narration"] = 5.0 if len(spoken) == len(scenes) or not spoken else 5.0 - 3.0 * (1 - len(spoken) / len(scenes))
    if spoken and len(spoken) < len(scenes):
        problems.append(f"{len(scenes) - len(spoken)} scene(s) have no narration while others do")

    score = round(sum(dims.values()) / len(dims), 2)
    verdict = "strong" if score >= 4.6 and not problems else "ok" if score >= 3.5 else "revise" if score >= 2.5 else "fail"
    return {"score": score, "verdict": verdict, "dimensions": {k: round(x, 2) for k, x in dims.items()}, "violations": problems}


# --- delivery promise: a film that was planned with designed motion must not silently ship as plain text cards ---

def promise_enabled() -> bool:
    return os.environ.get("DELIVERY_PROMISE", "").strip().lower() not in {"", "0", "false", "off", "no"}


def plain_scenes(plan, drafts: dict, fallback) -> list[int]:
    """Scene numbers whose built draft is exactly the always-valid plain fallback (the designer's scene was dropped)."""
    out = []
    for n in range(1, len(plan.scenes) + 1):
        draft = drafts.get(n)
        if draft is None:
            continue
        try:
            if draft.html == fallback(plan, n).html and draft.build_js == fallback(plan, n).build_js:
                out.append(n)
        except Exception:
            continue
    return out


def promise_broken(plan, drafts: dict, fallback, limit: float = 0.4) -> dict | None:
    """None when the delivered scenes keep the promise; else {scenes, share} (advisory: the film is not blocked, the person is told)."""
    count = len(plan.scenes)
    plain = plain_scenes(plan, drafts, fallback)
    if count and len(plain) / count >= limit:
        return {"scenes": plain, "share": round(len(plain) / count, 2)}
    return None
