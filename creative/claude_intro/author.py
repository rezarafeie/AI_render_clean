"""A new composition for every intro: Opus writes this brand's own film (src/Custom.tsx) instead of filling the fixed template.

The templates (kit/src/Story.tsx, Reel.tsx) stay what they were made as: the craft bar and the fallback. For Story and Reel the author gets the content, the
timing plan and the sound events (music beats, effects) the film must land on, the kit (lib.tsx), the template as a reference of quality, a film style of the
library when one fits, and what this person's last intros looked like; it returns one TSX file. The engine builds it and takes key stills; a build error or a
fault in the stills goes back to the author once; if it still fails the template renders the film (never an empty film).

    design, code = author(kind, content, timing, events, work, recent=..., brief=...)
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from creative import claude_motion as cm

log = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent
KIT = HERE / "kit" / "src"
KINDS = {"story": "Story.tsx", "reel": "Reel.tsx"}          # Presenter is the person's footage, Film3D the Blender plates: their pictures are not templates


def enabled(kind: str) -> bool:
    return kind in KINDS and os.environ.get("INTRO_AUTHOR", "1").strip().lower() not in {"0", "false", "off", "no"}


GUIDE = """You are the art director and Remotion engineer of a Persian studio that makes short intro films for brands. A template made this kind of intro until
now, and every brand got the SAME film with other words. Your job: design and write a NEW film for THIS brand - another composition, another ground, another
way the character or the brand's mark behaves, other transitions and another signature move - while keeping what makes the format work (the story beats, their
timing, the music and the sound effects on the picture's events).

Decide the design quickly (the art director already chose it) and spend your effort on the code. Return ONLY the file, between these two marker lines (no markdown fence, nothing else):
=====FILE=====
// DESIGN: <one or two sentences: the idea of this film's look, its ground, palette, type attitude and signature move>
<the code of src/Custom.tsx>
=====END=====

THE FILE: `export const Custom: React.FC = () => { ... }` rendering the whole film with frame-based animation (useCurrentFrame()/fps; no CSS animations,
no timers, no randomness except rnd() from lib), deterministic, at the size and frame rate given. Imports allowed: React; {AbsoluteFill, useCurrentFrame,
Sequence, interpolate, Easing} from 'remotion'; anything exported by './lib' (its source is given: CONTENT, TIMING, Fonts, useFonts, fit, Words, Wipe, Mascot,
markPath, rnd, fa, easing helpers...). Nothing else: no images, no network, no other packages, no new files. Call useFonts() and render <Fonts/> like the template.

CONTENT AND TIME: every text comes from CONTENT (the fields are described below; never invent a claim, number or name, never hard-code the brand's words) and
every beat starts at the time the TIMING plan gives (the same keys the template reads). The SOUND EVENTS list says what sound plays when: the picture's
matching event must land on that time (a hit on a cut, a whoosh on a move, a click on a tick). The film ends at TIMING.total.

PERSIAN: right to left; Persian is never split into letters or animated letter by letter (whole words, word by word with Words, or a Wipe from the right);
Persian digits via fa(); keep text inside the frame with margins (fit() sizes a line to a width). Text never overlaps text.

CRAFT: real composition per beat (scale contrast, one focal point, negative space), eased motion with anticipation and settle, camera-like moves (push, pan,
parallax) where they help, a consistent art language from start to end. A FILM STYLE (when given) is the design language to bend for this brand; the brand's
accent colour (CONTENT.palette.accent / MASCOT_COLOR) stays its colour. Never copy the template's layout: the template is only the quality bar and shows how
CONTENT and TIMING are read. Keep it cheap to render (no big blur filters, at most a few hundred SVG elements per frame)."""


def _texts(kind: str, content, timing: dict, events: list[dict], recent: str, style_guide: str) -> str:
    from . import ENGINES
    engine = ENGINES[kind]
    parts = [f"THIS FILM: {kind}, {engine.WIDTH}x{engine.HEIGHT}, {engine.FPS} fps, {timing.get('total', 0):g} s.",
             "WHAT THE CONTENT FIELDS MEAN (the content writer's brief):\n" + engine.GUIDE,
             "CONTENT (src/content.json; read it through CONTENT, never copy its words into the code):\n" + json.dumps(content.model_dump(exclude={"questions"}), ensure_ascii=False, indent=1),
             "TIMING (CONTENT.timing, also exported as TIMING):\n" + json.dumps(timing, ensure_ascii=False),
             "SOUND EVENTS (seconds; the picture lands on them):\n" + json.dumps([{"t": e.get("t"), "sound": e.get("k")} for e in events][:80], ensure_ascii=False)]
    if style_guide:
        parts.append(style_guide)
    if recent:
        parts.append(recent)
    return "\n\n".join(parts)


def _system(kind: str) -> str:
    # identical for every film of this kind: read from the provider's cache after the first
    return (GUIDE + "\n\nTHE KIT, src/lib.tsx:\n" + (KIT / "lib.tsx").read_text(encoding="utf-8")
            + f"\n\nTHE TEMPLATE ({KINDS[kind]}; the quality bar and how CONTENT/TIMING are read; never its layout):\n" + (KIT / KINDS[kind]).read_text(encoding="utf-8"))


def _clean(code: str) -> tuple[str, str]:
    code = code.strip()
    design = ""
    m = re.search(r"//\s*DESIGN:\s*(.+)", code)
    if m:
        design = m.group(1).strip()[:400]
    if "export const Custom" not in code:
        raise ValueError("the file has no `export const Custom`")
    return design, code + "\n"


def write(kind: str, content, timing: dict, events: list[dict], *, recent: str = "", style_guide: str = "", previous: str = "", problem: str = "") -> tuple[str, str]:
    user = _texts(kind, content, timing, events, recent, style_guide)
    if previous:
        user += "\n\nYOUR PREVIOUS FILE:\n" + previous[:40000]
    if problem:
        user += "\n\nFIX THIS (return the complete file again, keep the design):\n" + problem[:5000]
    # low effort: on Jarvis, Opus's hidden thinking counts against max_tokens; at 16K and at 48K it thought for the whole budget and wrote no code (finish=length,
    # empty text); with reasoning_effort=low the same prompt returned the whole file in 44 s (2026-11-17)
    code = cm._one_ask(_system(kind), user, 32000, None, tries=3, seconds=900, effort="low",
                       label=("intro_author", "دارم طراحی و کد تازهٔ این ویدیوی معرفی را برای همین برند می‌نویسم." if not problem else "دارم ایرادهای طراحی تازه را درست می‌کنم."))
    return _clean(code)


def install(work: Path, code: str | None) -> None:
    """Custom.tsx into the project (or the fallback stub), and content.json told which composition renders."""
    src = work / "src"
    (src / "Custom.tsx").write_text(code or "export const Custom = () => null;\n", encoding="utf-8")
    data = json.loads((src / "content.json").read_text(encoding="utf-8"))
    data["custom"] = bool(code)
    (src / "content.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
