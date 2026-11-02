"""Talking-head style "صحبتی ۲" (talking_2): educational split screen.

* the top half shows a picture for the sentence (the creator's upload, a
  library asset or an AI image) in a rounded card with a slow zoom on a
  coloured background; the speaker fills the bottom half
* other stretches show the speaker full frame, punching in and out every
  2-3 seconds
* captions of one or two words on the seam: a small white lead word above a
  big yellow keyword, no box
* glassy grey chips pop in as a stacked list where the speaker lists things
* the first seconds open on the hook on the seam; a louder mix (-14 LUFS);
  the same CTA card and logo outro as "صحبتی ۱"

Shared plumbing (face tracking, cuts, outro, fonts) comes from talking_1,
which is frozen.
"""
from __future__ import annotations

import hashlib
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..localize import _ass_time, _rounded_rect, measure_text_boxes, probe_fps, probe_video
from ..render_ass import ass_burner_ffmpeg, subtitles_filter
from . import talking_1 as base
from .talking_1 import (W, H, _colour, _esc as _base_esc, _median, _spaced, cold_open_span, eval_fps, fonts_bundle,
                        music_bed, persian_digits, render_outro, speech_ranges, track_faces, vignette_png)

log = logging.getLogger(__name__)

__all__ = ["track_faces", "plan_reel", "render", "probe_video"]

SPLIT_Y = H // 2               # seam between the picture and the speaker
BG_COLOUR = "#0F4C55"          # teal background behind the picture card
CARD_MARGIN = 44               # card inset from the frame edges (px)
CARD_RADIUS = 34
YELLOW = "#F5E04A"
MIN_PIECE, MAX_PIECE = 1.8, 3.0   # cut rhythm (seconds)
PICTURE_ZOOM = 0.07            # slow push on the picture over a shot
MUSIC_DB = -15.0
LOUDNESS = -14.0
FONT = "Ray ExtraBlack"
CHIP_COLOUR = "#8A9298"         # glassy grey chips


def _esc(text: str) -> str:
    """ASS-safe Persian with visible Ray word spacing."""
    return _spaced(_base_esc(text))


@dataclass
class Shot:
    src_in: float
    src_out: float
    split: bool = False
    close: bool = False
    face: tuple[float, float] = (0.5, 0.35)
    out_start: float = 0.0
    picture: Optional[str] = None      # image path for the top card
    slot: Optional[int] = None         # sentence index of the B-roll slot
    picture_in: float = 0.0            # motion clip offset, continuous across cut pieces

    @property
    def length(self) -> float:
        return self.src_out - self.src_in


@dataclass
class ReelPlan:
    shots: list[Shot]
    captions: list[dict] = field(default_factory=list)   # {"start","end","lead","key"} output time
    chips: list[dict] = field(default_factory=list)      # {"start","end","items"}
    cards: list[dict] = field(default_factory=list)      # text cards: {"start","end","text"}
    hook: Optional[dict] = None                          # {"start","end","text"}
    duration: float = 0.0
    cold_open: float = 0.0
    theme: str = "editorial"
    continuous_split: bool = True


# --- planning -------------------------------------------------------------------

def _pieces(ranges: list[tuple[float, float]], words: list[dict]) -> list[tuple[float, float]]:
    """Kept ranges split at word ends into MIN_PIECE..MAX_PIECE pieces."""
    out = []
    for a, b in ranges:
        start = a
        while b - start > MAX_PIECE:
            ends = [float(w["end"]) for w in words if start + MIN_PIECE <= float(w["end"]) <= min(b - 1.0, start + MAX_PIECE)]
            if not ends:
                break
            cut = max(ends)
            out.append((start, cut))
            start = cut
        out.append((start, b))
    return out


def _sentence_at(sentences: list[dict], t: float) -> Optional[int]:
    for k, s in enumerate(sentences):
        if s["start"] - 0.3 <= t <= s["end"] + 0.3:
            return k
    return None


def _face(faces, a, b) -> tuple[float, float]:
    inside = [(cx, cy) for t, cx, cy in faces if a - 0.5 <= t <= b + 0.5]
    near = inside or [(cx, cy) for t, cx, cy in sorted(faces, key=lambda f: abs(f[0] - a))[:3]]
    return _median([c[0] for c in near], 0.5), _median([c[1] for c in near], 0.35)


def _chunks(text: str) -> list[tuple[str, str]]:
    """Readable 2-3 word caption chunks: (lead phrase, accented keyword)."""
    words = [w for w in re.sub(r"[.،,!?؟]+", " ", text).split() if w]
    groups = [words[k:k + 3] for k in range(0, len(words), 3)]
    if len(groups) > 1 and len(groups[-1]) == 1:
        groups[-2].extend(groups.pop())
    out = []
    for group in groups:
        out.append((" ".join(group[:-1]), group[-1]))
    return out


def plan_reel(transcript: dict, decisions: dict, faces: list[tuple[float, float, float]], duration: float,
              pictures: Optional[dict[int, str]] = None, *, continuous_split: bool = True) -> ReelPlan:
    """Shots, captions, chips and cards on the output timeline.

    ``pictures`` maps a B-roll sentence index to its image; slots without one
    become text cards with the slot's Persian label.
    """
    from brain.talking_reel import is_filler

    sentences, words = transcript["sentences"], transcript["words"]
    pictures = pictures or {}
    dropped = [sentences[k] for k in decisions.get("drop", [])]

    def drop(word: dict) -> bool:
        t = float(word["start"])
        return is_filler(word.get("w", "")) or any(s["start"] - 0.05 <= t <= s["end"] + 0.05 for s in dropped)

    ranges = speech_ranges(words, drop, duration)
    if not ranges:
        raise ValueError("nothing left to keep after cutting pauses")
    broll = {b["i"]: b for b in decisions.get("broll", [])}
    chip_lists = {c["i"]: c["items"] for c in decisions.get("chips", [])}
    shots: list[Shot] = []
    close = False
    for a, b in _pieces(ranges, words):
        k = _sentence_at(sentences, (a + b) / 2)
        split = continuous_split or (k is not None and (k in broll or k in chip_lists))
        close = not close if not split else close
        shots.append(Shot(a, b, split=split, close=close and not split, face=_face(faces, a, b),
                          slot=k if split else None,
                          picture=pictures.get(k) if split and k not in chip_lists else None))

    cold = cold_open_span(decisions.get("cold_open"), sentences, words)
    if cold:
        a, b, _ = cold
        shots.insert(0, Shot(a, b, split=continuous_split, close=not continuous_split, face=_face(faces, a, b)))
    t = 0.0
    for shot in shots:
        shot.out_start = t
        t += shot.length
    total = t
    main = shots[1:] if cold else shots
    for group in _groups(main):
        offset=0.0
        for shot in group:
            shot.picture_in=offset
            offset+=shot.length

    def out_time(src: float) -> float:
        for shot in main:
            if src < shot.src_in:
                return shot.out_start
            if src <= shot.src_out:
                return shot.out_start + src - shot.src_in
        return total

    captions = []
    if cold:
        captions += _timed_chunks(cold[2], shots[0].src_in, shots[0].src_out, words,
                                  lambda s: s - shots[0].src_in)
    for k, sentence in enumerate(sentences):
        text = decisions["captions"].get(k) or decisions["captions"].get(str(k))
        if text and k not in decisions.get("drop", []):
            captions += _timed_chunks(text, sentence["start"], sentence["end"], words, out_time)
    captions.sort(key=lambda c: c["start"])
    for c, nxt in zip(captions, captions[1:]):
        c["end"] = min(max(c["end"], nxt["start"]), nxt["start"]) if nxt["start"] - c["end"] < 0.5 else c["end"]

    chips, cards = [], []
    for shot_group in _groups(main):
        k = shot_group[0].slot
        start, end = shot_group[0].out_start, shot_group[-1].out_start + shot_group[-1].length
        if k in chip_lists:
            chips.append({"start": start, "end": min(end, start + 3.2),
                          "items": [persian_digits(i) for i in chip_lists[k]]})
        elif k in broll and not shot_group[0].picture:
            cards.append({"start": start, "end": end, "text": persian_digits(broll[k].get("label") or "")})
    hook = None
    if decisions.get("hook"):
        hook = {"start": 0.0, "end": min(3.0, total), "text": persian_digits(decisions["hook"])}
    return ReelPlan(shots=shots, captions=captions, chips=chips, cards=cards, hook=hook, duration=total,
                    cold_open=shots[0].length if cold else 0.0, continuous_split=continuous_split)


def _groups(shots: list[Shot]) -> list[list[Shot]]:
    """Consecutive split shots of the same slot."""
    groups: list[list[Shot]] = []
    for shot in shots:
        if not shot.split:
            continue
        if groups and groups[-1][-1].slot == shot.slot and abs(
                groups[-1][-1].out_start + groups[-1][-1].length - shot.out_start) < 0.01:
            groups[-1].append(shot)
        else:
            groups.append([shot])
    return groups


def _timed_chunks(text: str, s0: float, s1: float, words: list[dict], out_time) -> list[dict]:
    spoken = [w for w in words if s0 - 0.05 <= float(w["start"]) <= s1 + 0.05]
    if not spoken:
        return []
    chunks = _chunks(persian_digits(text))
    out = []
    for index, (lead, key) in enumerate(chunks):
        first = min(len(spoken) - 1, round(index * len(spoken) / len(chunks)))
        last = min(len(spoken) - 1, max(first, round((index + 1) * len(spoken) / len(chunks)) - 1))
        a = max(s0, float(spoken[first]["start"]) - 0.04)
        b = min(s1, float(spoken[last]["end"]) + 0.10)
        if b - a >= 0.20:
            out.append({"start": out_time(a), "end": out_time(b), "lead": lead, "key": key})
    return out


# --- pictures -----------------------------------------------------------------------

def card_size() -> tuple[int, int]:
    return W - 2 * CARD_MARGIN, SPLIT_Y - 2 * CARD_MARGIN


def picture_panel(picture: Path, out: Path) -> Path:
    """Top half: the picture in a rounded card with a soft shadow on the background colour.

    Rendered 12% larger than the frame area so the slow zoom never shows edges.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageOps

    scale = 1.12
    pw, ph = int(W * scale), int(SPLIT_Y * scale)
    cw, ch = int(card_size()[0] * scale), int(card_size()[1] * scale)
    bg = Image.new("RGB", (pw, ph), BG_COLOUR)
    image = ImageOps.fit(Image.open(picture).convert("RGB"), (cw, ch), Image.LANCZOS)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=int(CARD_RADIUS * scale), fill=255)
    x, y = (pw - cw) // 2, (ph - ch) // 2
    shadow = Image.new("L", (pw, ph), 0)
    shadow.paste(mask, (x, y + 18))
    shadow = shadow.filter(ImageFilter.GaussianBlur(26))
    bg = Image.composite(Image.new("RGB", (pw, ph), "#000000"), bg, shadow.point(lambda v: int(v * 0.45)))
    bg.paste(image, (x, y), mask)
    bg.save(out)
    return out


def plain_panel(out: Path) -> Path:
    from PIL import Image

    size = (int(W * 1.12), int(SPLIT_Y * 1.12))
    expected = Image.new('RGB', (1, 1), BG_COLOUR).getpixel((0, 0))
    if out.is_file():
        try:
            with Image.open(out) as existing:
                if existing.size == size and existing.convert('RGB').getextrema() == tuple((v, v) for v in expected):
                    # cached_shot includes source mtimes: rewriting this same
                    # PNG invalidates every split shot on every continuation.
                    return out
        except OSError:
            pass
    Image.new("RGB", size, BG_COLOUR).save(out)
    return out


# --- overlay (ASS) --------------------------------------------------------------------

def build_ass(plan: ReelPlan, fonts_dir: Optional[Path]) -> str:
    events: list[str] = []
    seam = SPLIT_Y
    if plan.continuous_split and plan.theme != 'minimal':
        # A separate, full-width caption rail; never part of a scaled speaker PiP.
        events.append(_rounded_rect(1, 0, plan.duration, 0, seam - 72, W, seam + 72, '#101010', 0))
    split_spans = [(s.out_start, s.out_start + s.length) for s in plan.shots if s.split]

    def on_split(t: float) -> bool:
        return any(a <= t < b for a, b in split_spans)

    minimal = plan.theme == "minimal"
    key_size, lead_size = ((int(H * 0.036), int(H * 0.036)) if minimal
                           else (int(H * 0.038), int(H * 0.029)))
    hook_end = plan.hook["end"] if plan.hook else 0.0
    for caption_index, c in enumerate(plan.captions):
        if c["end"] <= hook_end:
            continue
        start = max(c["start"], hook_end)
        y = seam if plan.continuous_split else (seam - H * 0.004 if on_split(start) else H * (0.76 if minimal else 0.68))
        pop = "\\fad(70,70)" if minimal else "\\fscx108\\fscy108\\t(0,120,\\fscx100\\fscy100)"
        if minimal:
            phrase = " ".join(part for part in (c["lead"], c["key"]) if part)
            if caption_index > 0 and caption_index % 5 == 0:
                events.append(f"Dialogue: 5,{_ass_time(start)},{_ass_time(c['end'])},emph,,0,0,0,,"
                              f"{{\\an5\\q2\\pos({W / 2:.0f},{H * 0.62:.0f})"
                              f"\\fscx112\\fscy112\\t(0,150,\\fscx100\\fscy100)\\fad(90,120)}}{_esc(c['key'])}")
                continue
            events.append(f"Dialogue: 4,{_ass_time(start)},{_ass_time(c['end'])},key,,0,0,0,,"
                          f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.0f}){pop}}}{_esc(phrase)}")
            continue
        phrase = " ".join(part for part in (c["lead"], c["key"]) if part)
        events.append(f"Dialogue: 4,{_ass_time(start)},{_ass_time(c['end'])},key,,0,0,0,,"
                      f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.0f}){pop}}}{_esc(phrase)}")
    if plan.hook and minimal:
        y = H * 0.69
        events.append(f"Dialogue: 5,{_ass_time(plan.hook['start'] + 0.1)},{_ass_time(plan.hook['end'])},hook,,0,0,0,,"
                      f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.0f})\\fad(180,180)}}{_esc(plan.hook['text'])}")
    elif plan.hook:
        # The hook builds word by word on one line at chest height.
        words = plan.hook["text"].split()
        y = seam if on_split(plan.hook["start"]) else H * 0.64
        for k in range(len(words)):
            t0 = plan.hook["start"] + 0.1 + k * 0.3
            t1 = plan.hook["start"] + 0.1 + (k + 1) * 0.3 if k + 1 < len(words) else plan.hook["end"]
            pop = "\\fscx125\\fscy125\\t(0,150,\\fscx100\\fscy100)" if k == 0 else ""
            events.append(f"Dialogue: 5,{_ass_time(t0)},{_ass_time(t1)},hook,,0,0,0,,"
                          f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.0f}){pop}}}{_esc(' '.join(words[:k + 1]))}")
    chip_size = int(H * 0.032)
    for chip in plan.chips:
        items = chip["items"]
        inks = measure_text_boxes([(_esc(i), chip_size) for i in items], W, H, FONT, fonts_dir)
        pitch = chip_size * 1.85
        step = min(0.45, (chip["end"] - chip["start"]) * 0.5 / max(1, len(items)))
        for k, (item, (iw, ia, ib)) in enumerate(zip(items, inks)):
            y = SPLIT_Y / 2 + (k - (len(items) - 1) / 2) * pitch
            t0 = chip["start"] + 0.15 + k * step
            half = iw / 2 + chip_size * 0.6
            top, bottom = y + ia - chip_size * 0.32, y + ib + chip_size * 0.32
            fade = "\\fad(120,0)"
            events.append(_rounded_rect(2, t0, chip["end"], W / 2 - half, top, W / 2 + half, bottom, CHIP_COLOUR,
                                        (bottom - top) / 2, extra=f"\\1a&H38&{fade}"))
            events.append(f"Dialogue: 3,{_ass_time(t0)},{_ass_time(chip['end'])},chip,,0,0,0,,"
                          f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.1f}){fade}\\fscx120\\fscy120\\t(0,150,\\fscx100\\fscy100)}}"
                          f"{_esc(item)}")
    for card in plan.cards:
        cw, chh = card_size()
        events.append(_rounded_rect(2, card["start"], card["end"], CARD_MARGIN, CARD_MARGIN, CARD_MARGIN + cw,
                                    CARD_MARGIN + chh, "#123A40", CARD_RADIUS))
        events.append(f"Dialogue: 3,{_ass_time(card['start'])},{_ass_time(card['end'])},card,,0,0,0,,"
                      f"{{\\an5\\q2\\pos({W / 2:.0f},{SPLIT_Y / 2:.0f})\\fad(150,0)}}{_esc(card['text'])}")

    white, black = "&H00FFFFFF", "&H00000000"
    soft = "&H64000000"
    styles = [
        f"Style: key,{FONT},{key_size},{white},&H000000FF,{soft},{soft},"
        "-1,0,0,0,100,100,0,0,1,0.8,1.4,5,0,0,0,-1",
        f"Style: lead,{FONT},{lead_size},{white},&H000000FF,{soft},{soft},-1,0,0,0,100,100,0,0,1,0.7,1.2,2,0,0,0,-1",
        f"Style: hook,{FONT},{int(H * (0.041 if minimal else 0.046))},{white if minimal else _colour(YELLOW).replace('&H', '&H00', 1)[:-1]},&H000000FF,{soft},"
        f"{soft},-1,0,0,0,100,100,0,0,1,0.8,1.5,5,0,0,0,-1",
        f"Style: emph,{FONT},{int(H * 0.052)},{_colour(YELLOW).replace('&H', '&H00', 1)[:-1]},&H000000FF,{soft},{soft},"
        "-1,0,0,0,100,100,0,0,1,0.6,1.8,5,0,0,0,-1",
        f"Style: chip,{FONT},{chip_size},{white},&H000000FF,{black},&H80000000,-1,0,0,0,100,100,0,0,1,0,1,5,0,0,0,-1",
        f"Style: card,{FONT},{int(H * 0.05)},{white},&H000000FF,{black},&H80000000,-1,0,0,0,100,100,0,0,1,0,2,5,0,0,0,-1",
        "Style: plain,Arial,10,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
    ]
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
        "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles, "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *events,
    ]) + "\n"


# --- render -------------------------------------------------------------------------

GRADE = ("eq=contrast=1.08:saturation=1.12:gamma=0.99,"
         "colorbalance=rs=0.03:bs=-0.03:rm=0.03:bm=-0.03,unsharp=5:5:0.6")
MINIMAL_GRADE = "eq=contrast=1.04:saturation=0.96:gamma=1.01,unsharp=5:5:0.35"


def speaker_crop(
    shot: Shot, sw: int, sh: int, base_zoom: float = 1.0,
    close_zoom: float = base.CLOSE_ZOOM,
) -> tuple[int, int, int, int]:
    """Source crop for the speaker: 9:16 full frame (wide/close) or W x SPLIT_Y for the bottom half."""
    if shot.split:
        aspect = W / (H - SPLIT_Y)
        ch = sh * 0.56
        cw = min(sw, ch * aspect)
        ch = cw / aspect
        fx, fy = shot.face[0] * sw, shot.face[1] * sh
        x = min(max(0, fx - cw / 2), sw - cw)
        # Face a little below the middle, leaving the seam captions clear of the head.
        y = min(max(0, fy - 0.5 * ch), sh - ch)
        return int(cw) & ~1, int(ch) & ~1, int(x) & ~1, int(y) & ~1
    return base.crop_for(
        base.Shot(shot.src_in, shot.src_out, close=shot.close, face=shot.face), sw, sh,
        base_zoom=max(1.0, base_zoom), close_zoom=max(1.0, close_zoom),
    )


def render(video: Path, plan: ReelPlan, out: Path, *, work_dir: Path, music: Optional[Path] = None,
           cta: str = "", render_settings: Optional[dict] = None,
           logo_path: Optional[Path] = None, overlay: Optional[Path] = None,
           on_progress: Optional[Callable[[int], None]] = None, on_stage=None, **_ignored) -> Path:
    """`overlay` is an optional transparent WebM (engine/tscaps_overlay.py) composited above the ASS layer."""
    ffmpeg = ass_burner_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("Talking reels need an ffmpeg with libass (brew install ffmpeg-full)")
    if on_stage: on_stage('rendering source preparation', 'در حال بررسی و تبدیل فرمت فایل ورودی')
    video = base.prepare_render_source(video, work_dir, (lambda pct: on_progress(round(pct * .1))) if on_progress else None,
                                       getattr(on_progress, 'metrics', None))
    if on_progress: on_progress(10)
    if on_stage: on_stage('rendering captions', 'در حال آماده‌سازی زیرنویس و قاب‌های گوینده و تصاویر')
    sw, sh, _ = probe_video(video)
    settings = render_settings or {}
    gs = settings.get("grade") or {}
    brightness = 1 + float(gs.get("brightness", 0)) / 100
    contrast = float(gs.get("contrast", 100)) / 100
    grade = (
        f"lutrgb=r='(val*{brightness:.3f}-128)*{contrast:.3f}+128':"
        f"g='(val*{brightness:.3f}-128)*{contrast:.3f}+128':"
        f"b='(val*{brightness:.3f}-128)*{contrast:.3f}+128',"
        f"hue=s={float(gs.get('saturation', 100)) / 100:.3f},"
        f"colorbalance=rs={float(gs.get('temperature', 0)) / 500:.3f}:"
        f"bs={-float(gs.get('temperature', 0)) / 500:.3f}")
    fps = base.RENDER_FPS
    fps_value = eval_fps(fps)
    work_dir.mkdir(parents=True, exist_ok=True)
    fonts = fonts_bundle(work_dir)
    ass = work_dir / "reel2.ass"
    ass_text = build_ass(plan, fonts)
    from engine.caption_preferences import caption_font
    ass_text = caption_font(ass_text, settings)
    from engine.caption_looks import apply as apply_caption_looks
    ass_text = apply_caption_looks(ass_text, plan.captions)
    title_color = str(settings.get("title_color") or YELLOW)
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", title_color):
        old, new = _colour(YELLOW), _colour(title_color)
        ass_text = ass_text.replace(old, new).replace(old.replace("&H", "&H00", 1)[:-1], new.replace("&H", "&H00", 1)[:-1])
    ass.write_text(ass_text, encoding="utf-8")
    logo = settings.get("outro_logo") or {}
    outro, outro_seconds = render_outro(work_dir, cta.strip(), fps, fonts,
                                        logo_enabled=logo.get("enabled", True), logo_motion=logo.get("motion", "pop"),
                                        logo_path=logo_path)
    total = plan.duration + outro_seconds

    panels: dict[str, Path] = {}
    plain = plain_panel(work_dir / "panel_plain.png")

    def panel_for(shot: Shot) -> Path:
        if not shot.picture:
            return plain
        if shot.picture not in panels:
            digest = hashlib.sha256(shot.picture.encode()).hexdigest()[:12]
            panels[shot.picture] = picture_panel(Path(shot.picture), work_dir / f"panel_{digest}.png")
        return panels[shot.picture]

    n = len(plan.shots)
    source_colour = base.source_colour_filter(video)
    inputs = []
    clips = []
    elapsed = 0.0
    vf = []
    next_input = n
    zoom = settings.get("zoom") or {}
    zoom_amount = float(zoom.get("amount", 100)) / 100 if zoom.get("enabled", True) else 0.0
    base_zoom = float(zoom.get("base_scale", 100)) / 100 if zoom.get("enabled", True) else 1.0
    close_zoom = float(zoom.get("close_scale", 140)) / 100 if zoom.get("enabled", True) else 1.0
    for k, shot in enumerate(plan.shots):
        inputs = ['-threads','1','-ss',f'{shot.src_in:.3f}','-t',f'{shot.length:.3f}','-i',str(video)]
        vf = []
        next_input = 1
        cw, ch, x, y = speaker_crop(shot, sw, sh, base_zoom, close_zoom)
        cut = f"[0:v]setpts=PTS-STARTPTS,crop={cw}:{ch}:{x}:{y}"
        if shot.split:
            frames = max(1, round(shot.length * fps_value))
            if shot.picture and Path(shot.picture).suffix.lower()=='.mp4':
                from ..probe import probe_duration
                seek=min(shot.picture_in,max(0,probe_duration(Path(shot.picture))-1/fps_value))
                inputs += ['-threads','1','-ss',f'{seek:.3f}','-i',shot.picture]
                vf.append(f'[{next_input}:v]setpts=PTS-STARTPTS,scale={W}:{SPLIT_Y}:force_original_aspect_ratio=decrease,'
                          f'pad={W}:{SPLIT_Y}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps},'
                          f'tpad=stop_mode=clone:stop_duration={shot.length:.3f},trim=duration={shot.length:.3f},setsar=1,format=yuv420p[t{k}]')
            else:
                inputs += ["-threads", "1", "-i", str(panel_for(shot))]
                vf.append(f"[{next_input}:v]zoompan=z='1.0+{PICTURE_ZOOM * zoom_amount:.4f}*on/{frames}':"
                          f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s={W}x{SPLIT_Y}:fps={fps},setsar=1,format=yuv420p[t{k}]")
            vf.append(f"{cut},{source_colour},scale={W}:{H - SPLIT_Y}:flags=lanczos,fps={fps},setsar=1,{grade},format=yuv420p[b{k}]")
            vf.append(f"[t{k}][b{k}]vstack=inputs=2[v{k}]")
            next_input += 1
        else:
            vf.append(f"{cut},{source_colour},scale={W}:{H}:flags=lanczos,fps={fps},setsar=1,{grade},format=yuv420p[v{k}]")
        fade = min(0.012, shot.length / 4)
        vf.append(f"[0:a]asetpts=PTS-STARTPTS,"
                  f"afade=t=in:d={fade:.3f},afade=t=out:st={shot.length - fade:.3f}:d={fade:.3f}[a{k}]")
        length = max(1, round((elapsed+shot.length)*fps_value)-round(elapsed*fps_value))/fps_value
        if on_stage: on_stage('rendering shot', f'در حال رندر بخش {k + 1} از {len(plan.shots)}؛ گوینده و قاب تصویری بالا')
        clips.append((base.cached_shot(inputs,vf,k,length,work_dir),length)); elapsed += shot.length
        if on_progress: on_progress(min(60,10+round(elapsed/max(plan.duration,.001)*50)))
    if on_stage: on_stage('rendering composition', 'در حال ترکیب بخش‌ها، زیرنویس و صدا و رمزگذاری خروجی')
    inputs = base.shot_concat(clips,work_dir)
    vf = ['[0:v]setpts=PTS-STARTPTS[cv]','[0:a]asetpts=PTS-STARTPTS[ca]']
    next_input = 1
    inputs += ["-threads", "1", "-loop", "1", "-framerate", "1", "-i", str(vignette_png(work_dir / "vignette.png"))]
    vignette_alpha = max(0.0, min(1.0, float(gs.get("vignette", 50)) / 100))
    vf.append(f"[{next_input}:v]format=rgba,colorchannelmixer=aa={vignette_alpha:.3f}[vig]")
    next_input += 1
    content = "vmain" if outro else "vout"
    if overlay:
        inputs += ["-c:v", "libvpx-vp9", "-i", str(overlay)]
        vf.append(f"[cv][vig]overlay=0:0:format=yuv420:shortest=1,{subtitles_filter(ass, fonts)},format=yuv420p[vbase]")
        vf.append(f"[{next_input}:v]format=yuva420p,setpts=PTS-STARTPTS[tso]")
        vf.append(f"[vbase][tso]overlay=0:0:format=yuv420:eof_action=pass,format=yuv420p[{content}]")
        next_input += 1
    else:
        vf.append(f"[cv][vig]overlay=0:0:format=yuv420:shortest=1,{subtitles_filter(ass, fonts)},format=yuv420p[{content}]")
    if outro:
        inputs += ["-i", str(outro)]
        vf.append(f"[{next_input}:v]setsar=1,format=yuv420p[vend]")
        vf.append("[vmain][vend]concat=n=2:v=1:a=0[vout]")
        next_input += 1
    vf.append(f"[ca]apad=pad_dur={outro_seconds + 0.1:.3f}[cpad]")
    loud = f"loudnorm=I={LOUDNESS}:TP=-1:LRA=8,aresample=48000[aout]"
    if music and music.is_file():
        inputs += ["-i", str(music_bed(music, total + 1.0, work_dir))]
        from engine import music_mix
        mix = music_mix.resolve("talking_2", render_settings)
        vf.append(mix.bed(next_input, total))
        vf.extend(mix.graph(loud))
    else:
        vf.append(f"[cpad]{loud}")
    # Container CPU quotas do not limit FFmpeg's auto-detected host thread count.
    # Many split/picture branches otherwise spawn hundreds of scaler workers.
    cmd = [ffmpeg, "-hide_banner", "-y", "-filter_complex_threads", "2", "-filter_threads", "2", *inputs, "-filter_complex", ";".join(vf),
           "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-threads", "2", "-crf", "17", "-preset", "ultrafast",
           "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart",
           "-progress", "pipe:1", "-nostats", str(out)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    log_tail = []
    try:
        for row in proc.stdout:
            log_tail = (log_tail + [row])[-80:]
            if row.startswith("out_time_us=") and on_progress and total > 0:
                try: on_progress(min(99, 60+int(int(row.split("=")[1]) / 1e6 / total * 39)))
                except ValueError: pass
    except BaseException:
        proc.terminate(); proc.wait(timeout=5); out.unlink(missing_ok=True); raise
    if proc.wait() != 0:
        detail = 'process killed (SIGKILL); check container memory/OOM limits' if proc.returncode == -9 else base.ffmpeg_error(''.join(log_tail))
        raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}): {detail}")
    return out


# --- Tscaps hook layer (additive: without it the output is exactly the built-in ASS rendering) -------------------

render_plain = render


def render(video: Path, plan: ReelPlan, out: Path, *, work_dir: Path, **kwargs) -> Path:  # noqa: F811
    """Talking 2 uses the native Persian ASS path, including its opening hook.

    Other styles retain their own Tscaps integration. Do not rasterize and
    shrink these captions together with the speaker window.
    """
    return render_plain(video, plan, out, work_dir=work_dir, **kwargs)
