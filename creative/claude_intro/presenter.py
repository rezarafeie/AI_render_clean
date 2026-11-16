"""Intro engine 3 — Presenter: the person's own footage with an edit that shows itself (1920x1080, 30 fps, narration + music). Template: kit/src/Talk.tsx.

Every narration line performs one editing technique on screen (its treatment); the words on screen arrive on the same words of the narration.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)
KIND, WIDTH, HEIGHT, FPS, MUSIC, MUSIC_GAIN, FADE = "presenter", 1920, 1080, 30, "talk", 0.32, 2.5
TEMPO, LEAD, GAP, TAIL = 1.12, 0.5, 0.35, 2.6
RATE, CUT_RATE = 0.7, 0.85            # new narration over older footage: the footage runs slow so the lips never read as out of sync
CUT_W = 812
TREATMENTS = ("title_split", "word_cards", "cutout_place", "broll_code", "no_nle", "prompt_card", "end_card", "plain")


class Card(BaseModel):
    model_config = ConfigDict(extra="ignore")
    w: str = ""
    tag: str = ""


class Line(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = ""
    treatment: Literal["title_split", "word_cards", "cutout_place", "broll_code", "no_nle", "prompt_card", "end_card", "plain"] = "plain"
    tag: str = ""
    a: str = ""                                          # title_split: the brand's first half (right of the head)
    b: str = ""                                          # title_split: its second half (left of the head)
    sub: list[str] = Field(default_factory=list)         # title_split: two small lines
    cards: list[Card] = Field(default_factory=list)      # word_cards: up to four words of the line, one hard cut each
    l1: str = ""                                         # cutout_place / plain: first line
    l2: str = ""                                         # cutout_place / plain: second (heavy) line
    l3: str = ""                                         # cutout_place: a small Latin word
    title: str = ""                                      # broll_code / no_nle
    tracks: list[str] = Field(default_factory=list)      # no_nle: five track names
    panel: str = ""                                      # no_nle: the panel's small title
    lead: str = ""                                       # prompt_card: the giant word
    label: str = ""                                      # prompt_card: the small line above the card
    who: str = ""                                        # prompt_card: who is typing
    words: list[str] = Field(default_factory=list)       # prompt_card: the words typed, in the narrator's order
    pre: str = ""                                        # end_card: the small line above the brand
    features: str = ""                                   # end_card: one line of features separated by « · »


class Content(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: list[str] = Field(default_factory=list)
    brand: str = ""
    url: str = ""
    lines: list[Line] = Field(default_factory=list)
    facts: list[dict] = Field(default_factory=list)
    mascot_shape: str = "circle"


EXAMPLE = {
    "brand": "ادیتور جی‌پی‌تی", "url": "editor.rafiei.co", "mascot_shape": "spark",
    "lines": [
        {"text": "ادیتور جی‌پی‌تی، ویدیوت رو خودش تدوین می‌کنه.", "treatment": "title_split", "tag": "تدوین با", "a": "ادیتور", "b": "جی‌پی‌تی", "sub": ["ویدیوت رو", "خودش تدوین می‌کنه"]},
        {"text": "برش، متن، رنگ، و صدا.", "treatment": "word_cards", "cards": [{"w": "برش"}, {"w": "متن", "tag": "تایپوگرافی"}, {"w": "رنگ", "tag": "قبل"}, {"w": "صدا", "tag": "تراز روی −۱۴ LUFS"}]},
        {"text": "تو رو از پس‌زمینه جدا می‌کنه، و هر جا بخوای می‌ذاره.", "treatment": "cutout_place", "tag": "جداسازی سوژه", "l1": "جدا می‌کنه", "l2": "هر جا بخوای.", "l3": "anywhere."},
        {"text": "بی‌رول‌ها رو هم، خودش از صفر می‌سازه.", "treatment": "broll_code", "tag": "بی‌رول · ۰ عکس استوک · ۰ مدل ویدیو", "title": "از صفر می‌سازه"},
        {"text": "لازم نیست پریمیر رو باز کنی.", "treatment": "no_nle", "title": "بدون پریمیر.", "panel": "تایم‌لاین · همین ویدیو", "tracks": ["برش", "کپشن", "موشن", "رنگ", "صدا"]},
        {"text": "فقط کافیه بگی: یه ویدیوی خفن بساز.", "treatment": "prompt_card", "lead": "فقط", "label": "کافیه بگی", "who": "کاربر", "words": ["یه", "ویدیوی", "خفن", "بساز"]},
        {"text": "تدوین، با ادیتور جی‌پی‌تی.", "treatment": "end_card", "pre": "تدوین، با", "features": "برش · کپشن · رنگ · موشن · صدا — همه در یک گفت‌وگو"},
    ],
    "facts": [{"claim": "سوژه را از پس‌زمینه جدا می‌کند", "source": "docs"}],
}

GUIDE = """THE PRESENTER INTRO (landscape 1920x1080, 20-28 s): the person's own footage of a presenter, a new short narration, and an edit that SHOWS what
each line says: every narration line has one `treatment` that performs an editing technique on screen while the line is heard.
Write 5 to 7 narration lines (colloquial spoken Persian, each 4-10 words, one idea per line, numbers in words) and give each a treatment, each treatment at
most once, the first title_split and the last end_card:
- title_split: the brand's name split in two halves around the presenter's head. a = first half, b = second half (both words of the line), sub = 2 short
  lines taken from the rest of the line, tag = 2-3 words.
- word_cards: the line is a list of up to four one-word things the product does (from the FACTS); cards = those words exactly as in the line, each with an
  optional tiny tag (the second, third and fourth may have one).
- cutout_place: the line says the subject is cut out of the background and placed anywhere. l1 and l2 = two short phrases of the line (max 14 characters
  each), l3 = one small Latin word, tag = 2-3 words. Only when the FACTS say the product does this.
- broll_code: the line says what the product makes from nothing. title = a phrase of the line (max 16 characters), tag = a small factual line.
- no_nle: the line says no editing program is needed. title (max 14 characters), panel (small title of a timeline panel), tracks = exactly 5 track names.
- prompt_card: the line ends with what the person would say to the product. lead = the giant first word of the line, label = the next words (max 12
  characters), who = «کاربر», words = the words of that request in order, exactly as in the line.
- end_card: the closing line with the brand. pre = the words before the brand, features = up to five capabilities separated by « · » plus a short ending.
- plain: any other line: l1 and l2 = two phrases of the line.
RULES: every word shown on screen must be a word of its own line, spelled exactly the same (the engine finds the moment by matching the word). Only say what
the FACTS support. brand: as written. url: without https://. mascot_shape: the simple shape closest to the brand's own mark (spark | circle | square | drop |
hex | diamond | cloud). facts: every claim with its source."""


def _norm(s: str) -> str:
    s = re.sub(r"[ً-ْٰـ‌‍]", "", s or "")
    s = re.sub(r"[^\w؀-ۿ]+", "", s)
    return s.replace("ي", "ی").replace("ك", "ک").lower()


def cue(words: list[dict], phrase: str, start: float, default: float, after: float = -1.0) -> float:
    """The moment (film seconds) the first word of `phrase` is heard in a line whose words are [{t, s, e}] and that starts at `start`; `default` when it is not there."""
    target = _norm((phrase or "").split()[0]) if (phrase or "").split() else ""
    if not target:
        return round(default, 3)
    for exact in (True, False):
        for w in words:
            n = _norm(w.get("t", ""))
            if not n or start + float(w["s"]) <= after:
                continue
            if (n == target) if exact else (n.startswith(target) or target.startswith(n) and len(n) > 2):
                return round(start + float(w["s"]), 3)
    return round(default, 3)


def plan(content: Content, scenes: list[dict], footage_seconds: float, cutout: bool) -> tuple[dict, list[dict], float]:
    """scenes: the narration's lines [{start, dur, words}] (film seconds). Returns (timing, events, total)."""
    n = len(content.lines)
    V = [float(s["start"]) for s in scenes]
    total = round(V[-1] + float(scenes[-1]["dur"]) + TAIL, 3)
    starts = [0.0] + [round(v - 0.1, 3) for v in V[1:]]
    ends = starts[1:] + [total]
    span = max(4.0, footage_seconds - 14.0)
    ev: list[dict] = []
    cuts: list[float] = []
    lines = []

    def e(t: float, k: str, g: float = 0.6) -> None:
        ev.append({"t": round(max(0.0, t), 3), "k": k, "g": g})

    for i, (line, scene) in enumerate(zip(content.lines, scenes)):
        v, a, b, words = V[i], starts[i], ends[i], scene.get("words") or []
        src0 = round(1.0 + span * i / max(1, n), 2)
        src = [src0]
        cues: dict = {}
        if i:
            cuts.append(a)
        if line.treatment == "cutout_place" and not cutout:
            line.treatment = "plain"                           # no person matte on this machine: the line is shown as plain type over the footage
        kind = line.treatment
        if kind == "title_split":
            cues["a"] = cue(words, line.a, v, v)
            cues["b"] = cue(words, line.b, v, cues["a"] + 0.55, after=cues["a"])
            last = cues["b"]
            cues["sub"] = []
            for k, text in enumerate(line.sub[:2]):
                last = cue(words, text, v, last + 0.6, after=last)
                cues["sub"].append(last)
            e(v, "swell", 0.4)
        elif kind == "word_cards":
            times, last = [], a - 1
            for k, card in enumerate(line.cards[:4]):
                t = a if k == 0 else cue(words, card.w, v, v + k * 0.7, after=last)
                t = max(t, last + 0.45) if k else t           # a card under 0.45 s cannot be read
                times.append(round(t, 3)); last = t
            cues["words"] = times
            src = [round(src0 + k * 2.8, 2) for k in range(max(1, len(times)))]
            cuts.extend(times[1:])
            for t, k in zip(times, ("hit", "shutter", "whoosh", "pop")):
                e(t, k, 0.75 if k == "hit" else 0.65)
        elif kind == "cutout_place":
            cues["l1"] = cue(words, line.l1, v, v + 1.0)
            cues["cut"] = round(cues["l1"] - 0.1, 3)
            cues["l2"] = cue(words, line.l2, v, cues["l1"] + 1.1, after=cues["l1"])
            cues["move"] = round(cues["l2"] - 0.12, 3)
            e(a, "whoosh", 0.6); e(cues["cut"] + 0.1, "pop", 0.7); e(cues["move"], "whoosh", 0.5)
        elif kind == "broll_code":
            cues["title"] = cue(words, line.title, v, v + 1.2)
            e(a + 0.05, "hit", 0.7); e(cues["title"] + 0.15, "riser", 0.4)
        elif kind == "no_nle":
            cues["title"] = cue(words, line.title, v, v + 0.5)
            e(a, "whoosh", 0.6)
        elif kind == "prompt_card":
            cues["lead"] = cue(words, line.lead, v, v)
            cues["label"] = cue(words, line.label, v, cues["lead"] + 0.3, after=cues["lead"])
            cues["card"] = round(cues["label"] + 0.3, 3)
            times, last = [], cues["label"]
            for k, w in enumerate(line.words[:8]):
                last = cue(words, w, v, last + 0.3, after=last)
                times.append(last)
            cues["words"] = times
            e(a, "whoosh", 0.5)
            for t in times:
                e(t, "key", 0.6)
        elif kind == "end_card":
            cues["pre"] = cue(words, line.pre, v, v)
            cues["brand"] = cue(words, content.brand, v, v + 0.9, after=cues["pre"])
            e(v - 0.2, "swell", 0.6); e(cues["brand"] + 0.55, "ding", 0.5)
        else:
            cues["l1"] = cue(words, line.l1, v, v + 0.2)
            cues["l2"] = cue(words, line.l2, v, cues["l1"] + 0.8, after=cues["l1"])
            e(a, "whoosh", 0.5)
        lines.append({"a": a, "b": b, "v": v, "src": src, "cues": cues})
    return {"lines": lines, "cuts": [round(c, 3) for c in cuts], "total": total}, ev, total


def still_times(timing: dict) -> list[tuple[str, float]]:
    out = []
    for i, line in enumerate(timing["lines"], 1):
        cues = line["cues"]
        if "words" in cues and len(cues["words"]) > 1 and "lead" not in cues:
            for k, t in enumerate(cues["words"]):
                nxt = cues["words"][k + 1] if k + 1 < len(cues["words"]) else line["b"]
                out.append((f"line{i}-{k + 1}", round(min(t + 0.4, nxt - 0.08), 2)))
        else:
            out.append((f"line{i}", round(line["b"] - (0.9 if i == len(timing["lines"]) else 0.25), 2)))
    return out


def texts(content: Content) -> list[str]:
    out = [content.brand]
    for line in content.lines:
        out += [line.text, line.a, line.b, *line.sub, *[c.w for c in line.cards], line.l1, line.l2, line.title, line.lead, line.label, *line.words, line.features]
    return [t for t in out if t]


# ── footage ───────────────────────────────────────────────────────────────────

def probe(video: Path) -> tuple[float, int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "csv=p=0:s=,",
                          str(video)], capture_output=True, text=True, check=True).stdout.replace("\n", ",").split(",")
    numbers = [float(x) for x in out if x.strip()]
    return float(numbers[2]) if len(numbers) > 2 else 0.0, int(numbers[0]), int(numbers[1])


def normalise(video: Path, out: Path, limit: float = 90.0) -> float:
    """The footage as 1920x1080, 30 fps, silent H.264 (scaled to cover, centre crop); returns its length in seconds."""
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-t", f"{limit:.2f}", "-an",
                    "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p",
                    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-g", "15", "-movflags", "+faststart", str(out)], check=True)
    return probe(out)[0]


def face_centre(video: Path, seconds: float) -> tuple[float, float]:
    """Where the presenter's face is, as fractions of the frame (median of a few frames); the frame's upper middle when no face is found."""
    try:
        import cv2
        import numpy as np
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        capture = cv2.VideoCapture(str(video))
        found = []
        for k in range(8):
            capture.set(cv2.CAP_PROP_POS_MSEC, (0.08 + 0.84 * k / 7) * seconds * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.15, 6, minSize=(gray.shape[1] // 14, gray.shape[1] // 14))
            if len(faces):
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                found.append(((x + w / 2) / gray.shape[1], (y + h / 2) / gray.shape[0]))
        capture.release()
        if found:
            return float(np.median([f[0] for f in found])), float(np.median([f[1] for f in found]))
    except Exception:
        log.warning("face search failed; the frame's upper middle is used", exc_info=True)
    return 0.5, 0.4


def cutout(footage: Path, out: Path, *, start: float, seconds: float, x: int) -> bool:
    """A VP9 alpha clip (812x1080) of the person in the crop x..x+812 of the footage from `start` for `seconds`; False when no matte engine works here."""
    try:
        from engine import person_matte
        if not person_matte.available():
            return False
        matte = out.with_name("matte.mp4")
        person_matte.matte([{"src": str(footage), "start": float(start), "end": float(start + seconds), "crop": [int(x), 0, CUT_W, HEIGHT], "size": [CUT_W, HEIGHT],
                             "fps": FPS, "out": str(matte)}], timeout=1500)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(footage), "-i", str(matte),
                        "-filter_complex", f"[0:v]crop={CUT_W}:{HEIGHT}:{int(x)}:0,fps={FPS}[c];[1:v]format=gray,scale={CUT_W}:{HEIGHT}[m];[c][m]alphamerge[o]",
                        "-map", "[o]", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "2500k", "-auto-alt-ref", "0", "-an", str(out)], check=True, timeout=900)
        matte.unlink(missing_ok=True)
        return out.is_file() and out.stat().st_size > 2000
    except Exception:
        log.warning("the cut-out could not be made", exc_info=True)
        return False
