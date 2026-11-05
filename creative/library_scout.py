"""The library scout: lets a planned film use the ready-made, browser-checked components where one really fits a scene.

The planner and the scene designers are text models that write every scene from nothing; asked to choose a component and fill its strict
parameters in the same breath, they never did (0 of 96 scenes across the studio's motion films). The scout is a separate, optional step after the
plan: an image-capable model looks at pictures of every component next to the scenes and may suggest a few; each suggestion then gets its own
parameters, is checked by the same rules a planner's choice would be, and is dropped (the scene stays custom) at the first doubt. Nothing here
is required, and a failure of any part leaves the plan exactly as it was.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import llm
from .schemas import CreativeUnavailable

log = logging.getLogger(__name__)
SHEETS = Path(__file__).resolve().parent / "library_sheets"


def enabled() -> bool:
    return os.environ.get("MOTION_LIBRARY_SCOUT", "1") != "0"


class _Pick(BaseModel):
    scene: int
    resource_id: str
    reason: str = ""


class _Picks(BaseModel):
    picks: list[_Pick] = Field(default_factory=list)


class _Spec(BaseModel):
    """The component's own inputs for one scene (the headline itself is not written here: it is the scene's exact headline)."""
    parameters: dict[str, str | float | bool] = Field(default_factory=dict)
    button_label: str = ""
    accent: str = "blue"
    start_value: int = 0
    end_value: int = 100
    prefix: str = ""
    suffix: str = ""
    locale: str = "fa-IR"


PICK_SYSTEM = """You are the art director who knows a library of ready-made motion components. You are shown pictures of every component (each tile is
labelled with its name; the library id is "hyperframes:" plus that name) and the scenes of a film that is already planned. Decide whether any scene is
BETTER made from a ready component than from a custom drawing, and answer with JSON only: {"picks":[{"scene":3,"resource_id":"hyperframes:count-up","reason":"..."}]}

Rules
- Prefer none. An empty list is a good answer. Illustrated, story-driven or explanatory scenes stay custom: that is what the studio does well.
- Pick a component only when its shown design and behaviour clearly say what the scene says (a counter for a real number in the scene, a checklist or
  timeline for real steps, a notification stack for real notifications, a closing lockup for the call to action) AND its look suits this film's palette and design direction.
- A component may only restate words that are already in the scene's headline, narration or the request. Never pick one that would need an invented number, name, claim or logo.
- At most one scene in three, never two neighbouring scenes, never the first scene unless it is a pure title. Respect each component's minimum seconds.
- "reason": one short sentence in the language of the film."""

SPEC_SYSTEM = """You fill the inputs of ONE ready-made motion component for ONE scene of a film. Return JSON only:
{"parameters": {...}, "button_label": "", "accent": "blue", "start_value": 0, "end_value": 100, "prefix": "", "suffix": "", "locale": "fa-IR"}
- `parameters` holds exactly the component's own inputs listed in the schema; give EVERY required_content input (an explicit empty string is allowed for optional copy), respecting types, options, min, max and maxLength.
- Use only words and numbers that appear in the scene's headline, narration or the request, in the language of the film. Never invent statistics, names, prices or claims, and never keep a demo text.
- Comma-separated and pipe-separated lists must have exactly the counts the schema and the scene need.
- Colours: hex values from the film's palette when the component takes a colour."""


def _sheet_images() -> tuple[list[Path], list[dict]]:
    try:
        index = json.loads((SHEETS / "index.json").read_text())["sheets"]
    except (OSError, ValueError, KeyError):
        return [], []
    paths = [SHEETS / item["file"] for item in index if (SHEETS / item["file"]).is_file()]
    return paths, index


def _row(entry: dict) -> dict:
    return {"id": entry["id"], "what": entry["description"][:170], "best_for": entry.get("best_for", [])[:2], "min_seconds": entry["minimum_seconds"]}


def _scene_view(plan, n: int) -> dict:
    scene = plan.scenes[n - 1]
    return {"scene": n, "seconds": round(scene.end - scene.start, 1), "headline": scene.headline, "idea": scene.idea[:220], "narration": scene.narration[:200]}


def _trial_problems(plan, n: int, spec) -> list[str]:
    """The planner's own checks for this scene, with the component in place."""
    from . import motion_graphic as mg
    trial = plan.model_copy(deep=True)
    trial.scenes[n - 1].native_component = spec
    before = set(mg.validate_plan(plan, max_scenes=99))                 # what was already said about the plan is not the component's doing
    return [p for p in mg.validate_plan(trial, max_scenes=99) if p.startswith(f"scene {n}:") and p not in before]


def _spec_for(plan, n: int, entry: dict, brief: str, used: list[str] | None):
    from .native_motion import NativeMotion
    scene = plan.scenes[n - 1]
    headline = scene.headline.strip()
    if not 1 <= len(headline) <= 64:
        return None, ["the headline does not fit the component's text limit"]
    base = (f"COMPONENT {entry['id']}\n{json.dumps(entry, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"SCENE\n{json.dumps(_scene_view(plan, n), ensure_ascii=False)}\nthe scene's exact headline (the component shows it as its main text): {headline}\n"
            f"FILM: {plan.title}; {plan.format}; palette {plan.palette.model_dump_json()}\nORIGINAL REQUEST:\n{brief.strip()[:1200]}")
    problems: list[str] = []
    for _attempt in range(2):
        user = base if not problems else base + "\n\nYour previous inputs were rejected. Fix every point:\n- " + "\n- ".join(problems)
        try:
            got = llm.ask(_Spec, SPEC_SYSTEM, user, route=llm.DIRECTOR_ROUTE, tokens=1500, attempts=2, used=used)
            spec = NativeMotion.model_validate({"resource_id": entry["id"], "text": headline, "button_label": got.button_label[:24], "accent": got.accent if got.accent in ("green", "blue", "violet") else "blue",
                                                "start_value": got.start_value, "end_value": got.end_value, "prefix": got.prefix[:12], "suffix": got.suffix[:12],
                                                "locale": got.locale if got.locale in ("fa-IR", "en-US") else "fa-IR", "parameters": got.parameters})
        except CreativeUnavailable:
            raise
        except Exception as exc:                                    # a pydantic ValidationError names the offending input
            problems = [str(exc).splitlines()[0][:220]]
            continue
        problems = _trial_problems(plan, n, spec)
        if not problems:
            return spec, []
    return None, problems


def scout(plan, brief: str, *, used: list[str] | None = None) -> tuple[Any, dict]:
    """(plan with the accepted components in place, a report of what was considered). The plan is returned unchanged on any failure."""
    from .native_motion import catalog
    report: dict[str, Any] = {"status": "skipped", "reason": "", "picks": [], "offered": 0}
    if not enabled():
        report["reason"] = "disabled"
        return plan, report
    if plan.format != "vertical":
        report["reason"] = "the ready components are checked for vertical films only"
        return plan, report
    paths, _ = _sheet_images()
    rows = [_row(e) for e in catalog()]
    report["offered"] = len(rows)
    eligible = [n for n, s in enumerate(plan.scenes, 1) if not s.native_component and not s.shotcraft_component and s.end - s.start >= 2.5]
    if not paths or len(eligible) < 2:
        report["reason"] = "no pictures of the components" if not paths else "too few scenes"
        return plan, report
    try:
        from brain.llm import chat_vision
        user = (f"FILM: {plan.title} — {plan.summary}\nformat {plan.format}; palette {plan.palette.model_dump_json()}\nsignature device: {plan.signature or 'none'}\n"
                f"design direction: {plan.design_direction[:600]}\n\nSCENES\n" + json.dumps([_scene_view(plan, n) for n in eligible], ensure_ascii=False)
                + f"\n\nCOMPONENTS (tiles in the pictures are in this order, 15 per picture)\n{json.dumps(rows, ensure_ascii=False, separators=(',', ':'))}\n\nORIGINAL REQUEST:\n{brief.strip()[:1200]}")
        data, usage = chat_vision(PICK_SYSTEM, user, images=paths, max_tokens=1800, temperature=0.2, return_json=True, route="video_understanding")
        if used is not None and getattr(usage, "model", None) and usage.model not in used:
            used.append(usage.model)
        picks = _Picks.model_validate(data if isinstance(data, dict) else {"picks": []}).picks
    except Exception as exc:
        log.warning("library scout could not look at the components: %s", str(exc)[:200])
        report["reason"] = "the image model was not available"
        return plan, report
    by_id = {e["id"]: e for e in catalog()}
    limit = max(1, len(plan.scenes) // 3)
    taken: list[int] = []
    result = plan
    for pick in picks:
        n, entry = pick.scene, by_id.get(pick.resource_id)
        item = {"scene": n, "resource_id": pick.resource_id, "reason": pick.reason[:160], "used": False}
        report["picks"].append(item)
        if n not in eligible or entry is None:
            item["why_not"] = "not an eligible scene or an unknown component"
            continue
        if len(taken) >= limit or any(abs(n - m) < 2 for m in taken):
            item["why_not"] = "kept custom: at most one scene in three, never neighbours"
            continue
        try:
            spec, problems = _spec_for(result, n, entry, brief, used)
        except CreativeUnavailable as exc:
            item["why_not"] = "the model was not available for its inputs"
            log.warning("library scout inputs for scene %d failed: %s", n, str(exc)[:160])
            continue
        if spec is None:
            item["why_not"] = "kept custom: " + "; ".join(problems)[:200]
            continue
        result = result.model_copy(deep=True)
        result.scenes[n - 1].native_component = spec
        taken.append(n)
        item["used"] = True
    report["status"] = "used" if taken else "none-fits"
    return result, report
