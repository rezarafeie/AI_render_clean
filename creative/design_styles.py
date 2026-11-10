"""The look of a video, decided before its scenes are designed: from the person's reference when there is one, else by the studio; when the studio is not
sure, the person sees a picture of each candidate look and chooses (or describes the look, or gives a reference).

This is the LOOK (palette, type voice, how things move), never the scenario. Used by every engine that designs motion."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import llm
from .schemas import CreativeUnavailable

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
CONFIDENT = 0.72                       # below this (or without a clear gap to the runner-up) the person is asked
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class Palette(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bg: str = "#0F172A"
    surface: str = "#1E293B"
    ink: str = "#F8FAFC"
    accent: str = "#F59E0B"
    accent2: str = "#38BDF8"

    @field_validator("bg", "surface", "ink", "accent", "accent2", mode="before")
    @classmethod
    def _hex(cls, value):
        text = str(value or "").strip()
        if len(text) == 4 and text.startswith("#"):
            text = "#" + "".join(c * 2 for c in text[1:])
        return text if _HEX.match(text) else "#888888"


class StyleOption(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str
    name: str
    description: str = ""          # what it looks like and why it suits this content (Persian, short)
    palette: Palette = Field(default_factory=Palette)
    type_voice: str = ""           # the typography in words ("Ray 900 درشت با یک کلمهٔ برجسته")
    motion: str = ""               # how things move

    @field_validator("name", "description", "type_voice", "motion", mode="before")
    @classmethod
    def _short(cls, value):
        return " ".join(str(value or "").split())[:240]


class StyleProposal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    options: list[StyleOption] = Field(default_factory=list, max_length=4)
    recommended: str = ""
    confidence: float = 0.0
    reason: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, value):
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0


SYSTEM = """You are the art director of a Persian short-video studio. Before any scene is designed, you propose THREE clearly different looks (not three
variations of one) for the video described below: palette, typography voice and how things move. Return ONLY JSON:
{"options":[{"key":"a","name":"<2-3 Persian words>","description":"<one Persian sentence: what it looks like and why it suits THIS content>",
 "palette":{"bg":"#RRGGBB","surface":"#RRGGBB","ink":"#RRGGBB","accent":"#RRGGBB","accent2":"#RRGGBB"},"type_voice":"<typography in words>","motion":"<how things move>"}, ...],
 "recommended":"a","confidence":0.0,"reason":"<one Persian sentence>"}
Rules: palettes come from the product, its audience and the feeling, not from habit; ink must read on bg (contrast 4.5:1+); the accent must be vivid. The three looks must
differ in mood, not just hue (for example precise-technical, bold-energetic, warm-editorial). `confidence` is how sure you are that ONE look is clearly the best for this
content and audience (0.9 = obviously, 0.5 = a real toss-up): say so honestly. If the person gave a style note, every option must respect it."""


def propose(brief_text: str, concept_text: str, *, note: str = "", used: list[str] | None = None) -> StyleProposal:
    user = f"Content:\n{brief_text}\n\nChosen idea:\n{concept_text}" + (f"\n\nThe person's style note: {note}" if note else "")
    proposal = llm.ask(StyleProposal, SYSTEM, user, route=llm.DIRECTOR_ROUTE, tokens=1800, used=used)
    if len(proposal.options) < 2:
        raise CreativeUnavailable("fewer than two looks were proposed")
    keys = []
    for index, option in enumerate(proposal.options):
        option.key = re.sub(r"\W", "", option.key.lower()) or "abcd"[index]
        if option.key in keys:
            option.key = "abcd"[index]
        keys.append(option.key)
    if proposal.recommended not in keys:
        proposal.recommended = keys[0]
    return proposal


def decide(proposal: StyleProposal, *, reference_usable: bool = False, note: str = "") -> tuple[str, str]:
    """('auto', key) when a reference or a clear favourite settles it; ('ask', recommended key) when the person should look and choose."""
    if reference_usable or note.strip():
        return "auto", proposal.recommended
    return ("auto" if proposal.confidence >= CONFIDENT else "ask"), proposal.recommended


def reference_text(reference: dict | None) -> str:
    """What was observed in the person's reference video, as the style the designers must echo (never its words)."""
    if not reference or reference.get("status") != "analyzed":
        return ""
    fields = (("palette", "colours"), ("typography", "typography"), ("composition", "composition"), ("motion_language", "motion"), ("transitions", "transitions"),
              ("visual_density", "density"), ("hook_structure", "hook"), ("overall_feel", "feel"))
    parts = []
    for key, label in fields:
        value = reference.get(key)
        if value:
            parts.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
    if reference.get("avg_shot_s"):
        parts.append(f"average shot {reference['avg_shot_s']:g}s, {reference.get('cuts_per_second', 0):g} cuts/s")
    return "; ".join(parts)[:1800]


def _font(name: str, size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(ROOT / "presets" / "fonts" / name), size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        return ImageFont.load_default()


def write(draw, xy, text: str, font, fill: str, anchor: str) -> None:
    """Persian text needs the Raqm layout engine (the server has it); without it the text is drawn plainly rather than failing the preview."""
    try:
        draw.text(xy, text, font=font, fill=fill, anchor=anchor, direction="rtl", language="fa")
    except Exception:
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def preview(option: StyleOption, picture: Path | None, headline: str, out: Path) -> Path:
    """A 540x960 picture of the look: its palette as a backdrop, the product in a card, the real headline in its type voice, accent rule and swatches."""
    from PIL import Image, ImageDraw
    p = option.palette
    w, h = 540, 960
    base = Image.new("RGB", (w, h), p.bg)
    draw = ImageDraw.Draw(base)

    def rgb(color: str):
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))

    top, bottom = rgb(p.surface), rgb(p.bg)
    for y in range(h):                                        # a soft vertical blend from the surface colour into the background
        t = y / (h - 1)
        draw.line([(0, y), (w, y)], fill=tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3)))
    glow = Image.new("RGB", (w, h), p.accent)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([w * .1, h * .22, w * .9, h * .62], fill=70)
    from PIL import ImageFilter
    base.paste(glow, (0, 0), mask.filter(ImageFilter.GaussianBlur(70)))
    draw = ImageDraw.Draw(base)
    if picture and picture.is_file():
        try:
            with Image.open(picture) as image:
                image = image.convert("RGB")
                image.thumbnail((400, 400))
                card = Image.new("RGB", (image.width + 24, image.height + 24), (255, 255, 255))
                card.paste(image, (12, 12))
                base.paste(card, ((w - card.width) // 2, 250))
        except Exception:
            pass
    size = 54 if len(headline) <= 14 else 42
    text = headline.strip() or option.name
    font = _font("RAY-BLACK.TTF", size)
    write(draw, (w - 40, 90), text, font, p.ink, "ra")
    draw.rounded_rectangle([w - 40 - 130, 90 + size + 22, w - 40, 90 + size + 30], radius=4, fill=p.accent)
    label = _font("RAY-BOLD.TTF", 30)
    write(draw, (w // 2, h - 190), option.name, label, p.ink, "ma")
    for i, color in enumerate((p.bg, p.surface, p.accent, p.accent2, p.ink)):
        x = w // 2 - 5 * 26 + i * 52
        draw.ellipse([x, h - 120, x + 40, h - 80], fill=color, outline=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, "PNG")
    return out


def direction_text(option: StyleOption, extra: str = "") -> str:
    """The chosen look as the design direction the planner and scene designers follow."""
    p = option.palette
    return (f"{option.name}: {option.description} Palette bg {p.bg}, surface {p.surface}, ink {p.ink}, accent {p.accent}, accent2 {p.accent2}. "
            f"Typography: {option.type_voice}. Motion: {option.motion}." + (f" The person's own words about the look: {extra}" if extra else ""))
