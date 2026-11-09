"""Flow F — conversational revision.

A request like «هوک اول رو قوی‌تر کن، موشن‌ها سینمایی‌تر باشن و تصویر ثانیه ۱۲ رو عوض کن» becomes a short list
of typed operations against the *existing* project, so only what changed is re-rendered and nothing is rebuilt
from scratch. The model proposes operations; `apply_to_talking` turns them into engine changes using only the
fields the talking engine really exposes, and reports honestly what it could not do.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import llm
from .schemas import CreativeUnavailable

Op = Literal["rewrite_hook", "edit_caption", "remove_sentence", "remove_range", "set_render", "change_style", "replace_visual", "drop_visual", "set_cta", "clear_identity", "add_key_moment", "remove_key_moment", "add_effect", "remove_effect", "unsupported"]
VISUAL_TYPES = {"concept", "stat", "comparison", "steps", "ui_showcase", "media_collage", "chat", "map_route",
                "spec_callout", "kinetic_type", "before_after"}
STYLES = {"talking_1", "talking_2", "talking_3"}

# Render settings the model may change, with the engine's own limits (see app/talking_reel._clean_render_settings).
GRADE_LIMITS = {"brightness": (-30, 30), "contrast": (50, 160), "saturation": (0, 180), "temperature": (-50, 50), "vignette": (0, 100)}


class RevisionOp(BaseModel):
    model_config = ConfigDict(extra="ignore")
    op: Op
    sentence: int | None = None
    start: float | None = None
    end: float | None = None
    text: str = ""
    highlight: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    visual_type: str = ""
    fx: str = ""
    style: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""

    @field_validator("sentence", mode="before")
    @classmethod
    def _index(cls, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @field_validator("text", "reason", "visual_type", "style", "fx", mode="before")
    @classmethod
    def _text(cls, value):
        return " ".join(str(value or "").split())[:300]

    @field_validator("highlight", "items", mode="before")
    @classmethod
    def _list(cls, value):
        return [str(v).strip()[:80] for v in (value or []) if str(v).strip()][:6] if isinstance(value, list) else []

    @field_validator("settings", mode="before")
    @classmethod
    def _settings(cls, value):
        return value if isinstance(value, dict) else {}


class Revision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str = ""
    ops: list[RevisionOp] = Field(default_factory=list)

    @field_validator("ops", mode="before")
    @classmethod
    def _ops(cls, value):
        return [v for v in (value or []) if isinstance(v, dict)][:12]


SYSTEM = """You are the revision editor of a Persian video studio. The creator talks to you about an EXISTING video.
Translate their request into a short list of operations on that video. Change only what they asked; never rebuild.
You receive the transcript sentences (index: text), the current hook, captions, designed visuals ("storyboard"), render
settings and style. Return ONLY JSON: {"summary": "<one friendly Persian sentence saying what you will change>", "ops": [...]}.

Operations (use exactly these):
- {"op":"remove_range","start":<output seconds>,"end":<output seconds>} (Talking 1: a precise partial audio/video cut, with captions retimed.)
  Use output_words to identify boundaries. For a repeated false start, cut ONLY that false start, NOT the entire long sentence.
- {"op":"remove_sentence","sentence":<index>} (Talking 1: removes actual picture AND audio, not just caption.)
  User timestamps refer to OUTPUT time: use output_sentence_ranges, NOT raw source timestamps.
  Do not overrule a requested cut because you think a different sentence is more repetitive. Ask if the output timestamp is ambiguous.
- {"op":"rewrite_hook","text":"<new Persian hook, 3-8 words, faithful to what the speaker says>","highlight":["<1-2 words from the hook>"]}
- {"op":"edit_caption","sentence":<index>,"text":"<corrected caption>"}
- {"op":"set_render","settings":{ any of: "title_color":"#RRGGBB", "zoom_amount":0-200, "base_scale":100-180,"close_scale":100-220,"first_key_moment_enabled":bool,"bottom_shade":0-60,"zoom_enabled":bool, "outro_logo":bool,
    "key_moments":bool, "brightness":-30..30, "contrast":50..160, "saturation":0..180, "temperature":-50..50, "vignette":0..100 }}
    (a "cinematic" look = lower saturation, slightly higher contrast, warmer temperature and stronger vignette; "more energy" = larger zoom_amount)
    Frame zoom/crop means base_scale and close_scale, NOT zoom_amount (animation strength).
    A 10% larger full frame multiplies current base_scale and close_scale by 1.1.
    Disabling first_key_moment_enabled removes ONLY the opening teaser, keeping other moments.
    bottom_shade adds a soft black gradient under the lower-third in Talking 1; subtle=20-30.
- {"op":"change_style","style":"talking_1|talking_2|talking_3"}   (re-plans the edit in that style)
- {"op":"replace_visual","sentence":<index>,"text":"<2-6 word Persian title>","visual_type":"<concept|stat|comparison|steps|ui_showcase|media_collage|chat|map_route|spec_callout|kinetic_type|before_after>","items":["<up to 4 facts the speaker says>"]}
- {"op":"drop_visual","sentence":<index>}
- {"op":"set_cta","text":"<call to action>"}
- {"op":"add_key_moment","sentence":<index>,"text":"<2-4 Persian words: the takeaway shown big over that moment, or empty>"}
  (Talking 1: the moment turns black-and-white with its takeaway in white. Add one per moment the creator asks for; when they ask for N more
  moments without naming them, choose N strong, different sentences spread over the talk. Never colour them.)
- {"op":"remove_key_moment","sentence":<index>}
- {"op":"add_effect","fx":"<id>","start":<output seconds>,"end":<output seconds>,"text":"<optional label, Persian>","settings":{<optional numbers/colour of that effect>}}
  (An effect that follows the speaker's face, laid over the finished video for 0.4-8 seconds. Use output_words / output_sentence_ranges to turn "when I say X" or
  "in the first 3 seconds" into output seconds. Ids: {EFFECT_IDS}. {EFFECT_HELP})
- {"op":"remove_effect","fx":"<id>"}   (removes every effect of that kind; leave fx empty to remove all effects)
- {"op":"clear_identity"} (remove an incorrect/unverified speaker name and role; never invent a replacement identity)
- {"op":"unsupported","reason":"<what was asked that cannot be done with these operations, in Persian>"}

Rules: when asked to fix the output, address the supplied quality_review/last_failure, not just aesthetic preferences.
Use clear_identity if the review flags an incorrect default speaker name. Do not invent a person's identity.
Refer to moments by sentence index (convert a timestamp using the [start-end] times given). Use `unsupported` instead of
guessing. Never invent facts or numbers the speaker did not say. A request that does not change the video (a question) gets
an empty ops list and an answer in `summary`."""


def _system() -> str:
    from engine import face_effects as effects
    help_text = " ".join(f'{item["id"]}={item["description"]}' for item in effects.CATALOG)
    return SYSTEM.replace("{EFFECT_IDS}", ", ".join(item["id"] for item in effects.CATALOG)).replace("{EFFECT_HELP}", help_text)


def interpret(request: str, context: dict) -> Revision:
    """Ask the revision route for operations; raises CreativeUnavailable if the model cannot answer."""
    user = f"Creator's request: {request}\n\nCurrent video:\n{llm.dumps(context)}"
    return llm.ask(Revision, _system(), user, route=llm.REVISION_ROUTE, tokens=3000, attempts=3)


@dataclass
class TalkingChange:
    changes: dict = field(default_factory=dict)       # for app.talking_reel.update()
    applied: list[str] = field(default_factory=list)  # human-readable, Persian
    unsupported: list[str] = field(default_factory=list)
    restyle: str | None = None

    @property
    def rerender(self) -> bool:
        return bool(self.changes)


def _clamp(value: Any, low: int, high: int) -> int | None:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return None


def apply_to_talking(public_state: dict, ops: list[RevisionOp], sentence_count: int, *, output_plan=None) -> TalkingChange:
    """Pure: map operations onto talking-engine edits. Anything outside the engine's real surface is reported, not faked."""
    out = TalkingChange()
    style = str(public_state.get("style") or "talking_1")
    settings = copy.deepcopy(public_state.get("render_settings") or {})
    board = [dict(item) for item in (public_state.get("storyboard") or []) if isinstance(item, dict)]
    captions: list[dict] = []
    touched_settings = False
    moments: dict[int, str] | None = None

    def known(i: int | None) -> bool:
        return i is not None and 0 <= i < sentence_count

    for op in ops:
        if op.op == 'remove_range':
            if style != 'talking_1' or output_plan is None or op.start is None or op.end is None:
                out.unsupported.append('برای برش جزئی باید نگاشت زمان خروجی در دسترس باشد.'); continue
            from engine.revision_timing import source_cuts
            try: cuts=source_cuts(output_plan, op.start, op.end)
            except ValueError as exc:
                out.unsupported.append(str(exc)); continue
            settings['source_cuts'] = (settings.get('source_cuts') or []) + cuts
            touched_settings = True
            out.applied.append(f'تصویر و صدا در بازهٔ {op.start:g} تا {op.end:g} خروجی حذف می‌شود؛ زیرنویس هم باززمان‌بندی می‌شود.')
            continue
        if op.op == 'remove_sentence':
            if style == 'talking_1' and known(op.sentence):
                settings['dropped_sentences'] = sorted(set(settings.get('dropped_sentences', [])) | {op.sentence})
                touched_settings = True
                out.applied.append(f'تصویر و صدای جملهٔ {op.sentence} از تدوین حذف می‌شود؛ زمان‌بندی زیرنویس دوباره محاسبه می‌شود.')
            else: out.unsupported.append('برش این جمله برای سبک فعلی تأیید نشده است.')
            continue
        if op.op in {"add_effect", "remove_effect"}:
            from engine import face_effects as effects
            current = [dict(item) for item in (settings.get("effects") or [])]
            if op.op == "add_effect":
                if op.start is None or op.end is None:
                    out.unsupported.append("زمان شروع و پایان افکت مشخص نشد."); continue
                item = {"fx": op.fx, "start": op.start, "end": op.end, **({"text": op.text} if op.text else {}), **(op.settings or {})}
                try:
                    settings["effects"] = effects.clean_plan(current + [item])
                except effects.EffectsError as exc:
                    out.unsupported.append(str(exc)); continue
                title = effects.BY_ID[settings["effects"][-1]["fx"]]["title"]
                out.applied.append(f"افکت «{title}» از ثانیهٔ {op.start:g} تا {op.end:g}")
            else:
                kept = [item for item in current if op.fx and item.get("fx") != op.fx]
                if len(kept) == len(current):
                    out.unsupported.append("افکتی برای برداشتن پیدا نشد."); continue
                settings["effects"] = kept
                out.applied.append("افکت‌ها برداشته شد" if not op.fx else f"افکت «{op.fx}» برداشته شد")
            touched_settings = True
            continue
        if op.op in {"add_key_moment", "remove_key_moment"}:
            if style != "talking_1":
                out.unsupported.append("لحظه‌های کلیدی سیاه‌وسفید فقط در سبک ۱ هستند."); continue
            if not known(op.sentence):
                out.unsupported.append("جملهٔ لحظهٔ کلیدی پیدا نشد."); continue
            moments = moments if moments is not None else {m["i"]: m.get("text", "") for m in (public_state.get("key_moments") or [])}
            if op.op == "add_key_moment":
                moments[op.sentence] = op.text if len(op.text.split()) <= 5 else " ".join(op.text.split()[:5])
                out.applied.append(f"لحظهٔ کلیدی جملهٔ {op.sentence}" + (f": «{op.text}»" if op.text else ""))
            else:
                moments.pop(op.sentence, None)
                out.applied.append(f"لحظهٔ کلیدی جملهٔ {op.sentence} برداشته شد")
            out.changes["key_moments"] = [{"i": i, "text": t} for i, t in sorted(moments.items())]
            continue
        if op.op == 'clear_identity':
            out.changes.update(name='', title='')
            out.applied.append('نام و سمت تأییدنشدهٔ گوینده حذف شد.')
            continue
        if op.op == "rewrite_hook" and op.text:
            out.changes["hook" if style == "talking_1" else "hook2"] = op.text
            out.changes["hook_highlight"] = [h for h in op.highlight if h in op.text][:2]
            out.applied.append(f"هوک جدید: «{op.text}»")
        elif op.op == "edit_caption" and known(op.sentence) and op.text:
            captions.append({"i": op.sentence, "text": op.text})
            out.applied.append(f"کپشن جملهٔ {op.sentence} اصلاح شد")
        elif op.op == "set_cta" and op.text:
            out.changes["cta"] = op.text
            out.applied.append(f"دعوت به اقدام: «{op.text}»")
        elif op.op == "change_style" and op.style in STYLES and op.style != style:
            out.restyle = op.style
            out.changes["style"] = op.style
            out.applied.append(f"سبک به {op.style} تغییر کرد (ادیت از نو برنامه‌ریزی می‌شود)")
        elif op.op == "set_render":
            s = op.settings
            grade = settings.setdefault("grade", {})
            zoom = settings.setdefault("zoom", {})
            labels = []
            if 'first_key_moment_enabled' in s:
                settings['first_key_moment_enabled'] = bool(s['first_key_moment_enabled']); touched_settings = True
                labels.append('لحظهٔ کلیدی اول ' + ('فعال' if settings['first_key_moment_enabled'] else 'خاموش'))
            for key, low, high in [('base_scale',100,180),('close_scale',100,220)]:
                if key in s and (value := _clamp(s[key], low, high)) is not None:
                    zoom[key] = value; touched_settings = True; labels.append(f'{key}={value}')
            if 'bottom_shade' in s and style == 'talking_1' and (value := _clamp(s['bottom_shade'],0,60)) is not None:
                settings['bottom_shade'] = value; touched_settings = True; labels.append(f'سایهٔ پایین قاب={value}')
            for key, (low, high) in GRADE_LIMITS.items():
                if key in s and (value := _clamp(s[key], low, high)) is not None:
                    grade[key] = value; labels.append(f"{key}={value}"); touched_settings = True
            if "zoom_amount" in s and (value := _clamp(s["zoom_amount"], 0, 200)) is not None:
                zoom["amount"] = value; labels.append(f"zoom={value}"); touched_settings = True
            if "zoom_enabled" in s:
                zoom["enabled"] = bool(s["zoom_enabled"]); labels.append(f"zoom {'on' if zoom['enabled'] else 'off'}"); touched_settings = True
            color = str(s.get("title_color") or "")
            if color.startswith("#") and len(color) == 7 and all(c in "0123456789abcdefABCDEF" for c in color[1:]):
                settings["title_color"] = color.upper(); labels.append(f"رنگ تیتر {color.upper()}"); touched_settings = True
            if "outro_logo" in s:
                settings.setdefault("outro_logo", {})["enabled"] = bool(s["outro_logo"]); labels.append("لوگوی پایانی " + ("روشن" if s["outro_logo"] else "خاموش")); touched_settings = True
            if "key_moments" in s:
                settings["key_moments_enabled"] = bool(s["key_moments"]); labels.append("لحظه‌های کلیدی " + ("روشن" if s["key_moments"] else "خاموش")); touched_settings = True
            if labels:
                out.applied.append("تنظیمات تصویر: " + "، ".join(labels))
        elif op.op in {"replace_visual", "drop_visual"} and style in {"talking_2", "talking_3"} and known(op.sentence):
            if op.op == "drop_visual":
                board = [b for b in board if b.get("i") != op.sentence]
                out.applied.append(f"گرافیک جملهٔ {op.sentence} حذف شد")
            elif op.text:
                visual_type = op.visual_type if op.visual_type in VISUAL_TYPES else "concept"
                item = {"i": op.sentence, "title": op.text, "visual_type": visual_type, "items": op.items}
                existing = next((b for b in board if b.get("i") == op.sentence), None)
                if existing:
                    existing.update(item)
                else:
                    board.append(item)
                out.applied.append(f"گرافیک جملهٔ {op.sentence}: «{op.text}» ({visual_type})")
            else:
                out.unsupported.append(f"برای جملهٔ {op.sentence} عنوان جدیدی مشخص نشد")
            out.changes["storyboard"] = board
        elif op.op in {"replace_visual", "drop_visual"}:
            out.unsupported.append("گرافیک‌های جداگانه فقط در سبک‌های ۲ و ۳ قابل ویرایش‌اند" if style not in {"talking_2", "talking_3"}
                                   else "جملهٔ مورد نظر در ویدیو پیدا نشد")
        elif op.op == "unsupported":
            out.unsupported.append(op.reason or "این درخواست هنوز پشتیبانی نمی‌شود")
        else:
            out.unsupported.append(f"عملیات «{op.op}» قابل اجرا نبود")
    if captions:
        out.changes["captions"] = captions
    if touched_settings:
        out.changes["render_settings"] = settings
    return out
