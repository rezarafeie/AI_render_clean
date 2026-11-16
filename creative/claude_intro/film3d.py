"""Intro engine 4 — Film3D: a cinematic 3D film of one desk from day to night (1920x1080, 24 fps, music and room tone, four subtitles).
Template: kit/src/Film.tsx + kit/src/ProductUI.tsx; the plates are Cycles renders of kit/b3d/scene.py, cached per scene parameters.

The kit ships the plates of the default scene (the studio's own mark as the desk figurine). Any other scene (another brand's mark, wall or poster) is
rendered with Blender's Python module in a separate interpreter (INTRO_BPY_PYTHON); without it the engine stops with a clear message instead of showing
another brand's figurine.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent
KIT_PLATES = HERE / "kit" / "film"
SCENE = HERE / "kit" / "b3d" / "scene.py"
KIND, WIDTH, HEIGHT, FPS, MUSIC, MUSIC_GAIN, FADE = "film3d", 1920, 1080, 24, "film", 0.75, 3.5
TOTAL, END = 47.0, 43.0
RENDERS = [("wide", "day"), ("wide", "dusk"), ("wide", "night"), ("wide", "morning"), ("med", "day"), ("med", "night"), ("screen", "day"), ("screen", "night"),
           ("mascot", "dusk"), ("mascot", "night"), ("low", "night")]
DEFAULT_SCENE = {"mascot_shape": "spark", "mascot_color": None, "wall": None, "poster": None}

# the reference film's shot table: each shot shows a span (u0..u1) of the interface's narrative clock
SHOTS = [
    {"a": 0, "b": 4.6, "plate": "wide_day", "s0": 1.0, "s1": 1.07, "ox": 0.52, "oy": 0.62, "u0": 0, "u1": 0.5, "uiDim": 0.85},
    {"a": 4.6, "b": 10.0, "plate": "screen_day", "s0": 1.02, "s1": 1.07, "dx": -18, "ox": 0.5, "oy": 0.4, "u0": 0.4, "u1": 5.6, "uiDim": 0.92},
    {"a": 10.0, "b": 13.2, "plate": "mascot_dusk", "s0": 1.03, "s1": 1.09, "dx": 14, "ox": 0.4, "oy": 0.55, "u0": 6, "u1": 8, "blur": 15, "fg": "mascot_dusk_fg"},
    {"a": 13.2, "b": 18.2, "plate": "med_day", "s0": 1.02, "s1": 1.08, "ox": 0.6, "oy": 0.4, "u0": 7.4, "u1": 12.6, "uiDim": 0.92},
    {"a": 18.2, "b": 25.2, "plate": "wide_day", "plate2": [["wide_dusk", 19.2, 21.0], ["wide_night", 22.0, 23.8]], "s0": 1.07, "s1": 1.16, "ox": 0.52, "oy": 0.62, "u0": 12, "u1": 16},
    {"a": 25.2, "b": 30.2, "plate": "screen_night", "s0": 1.07, "s1": 1.02, "dx": 16, "ox": 0.5, "oy": 0.4, "u0": 15.5, "u1": 21},
    {"a": 30.2, "b": 34.4, "plate": "low_night", "s0": 1.02, "s1": 1.09, "dx": -12, "ox": 0.7, "oy": 0.4, "u0": 20.6, "u1": 24.9},
    {"a": 34.4, "b": 38.6, "plate": "med_night", "s0": 1.08, "s1": 1.02, "ox": 0.6, "oy": 0.4, "u0": 24.3, "u1": 28},
    {"a": 38.6, "b": 43.0, "plate": "wide_morning", "s0": 1.1, "s1": 1.02, "ox": 0.52, "oy": 0.62, "u0": 28, "u1": 30, "uiDim": 0.85},
]
SUB_SPANS = [(1.3, 4.3), (19.0, 22.6), (30.8, 33.8), (35.4, 38.2)]
EVENTS = [(0.2, "room", 0.35), (5.3, "keys", 0.5), (8.2, "keys", 0.4), (9.55, "key", 0.7), (10.0, "swell", 0.35), (13.2, "tick", 0.3), (18.2, "room", 0.4), (22.0, "key", 0.5),
          (25.2, "room", 0.35), (30.2, "swell", 0.3), (34.0, "ding", 0.5), (38.6, "swell", 0.5), (43.0, "pop", 0.4)]


class UI(BaseModel):
    model_config = ConfigDict(extra="ignore")
    app: str = ""
    nav: list[str] = Field(default_factory=list)            # four sidebar items (the second is the selected one)
    recent_label: str = ""
    recent: list[str] = Field(default_factory=list)         # four recent project names (samples)
    heading: str = ""
    placeholder: str = ""
    chips: list[str] = Field(default_factory=list)
    attachment: str = ""
    model: str = ""
    prompt: str = ""                                        # the one sentence the person types
    project: str = ""
    working: str = ""
    ready: str = ""
    reply: str = ""
    steps: list[str] = Field(default_factory=list)          # six steps that are ticked one after the other
    panel: list[str] = Field(default_factory=list)          # the side panel's three titles: plan, preview, result
    board: list[str] = Field(default_factory=list)          # six storyboard card labels
    preview: list[str] = Field(default_factory=list)        # the preview's title in two parts (the second in the accent colour)
    tracks: list[str] = Field(default_factory=list)         # four timeline tracks
    status: list[str] = Field(default_factory=list)         # three states of the status line: arranging, rendering, finished
    count: int = 1440
    done: list[str] = Field(default_factory=list)           # the big «آماده شد.» and one line of specs
    buttons: list[str] = Field(default_factory=list)
    tokens: dict = Field(default_factory=dict)              # the product's own interface colours: bg, sidebar, surface, elevated, border, text, accent


class End(BaseModel):
    model_config = ConfigDict(extra="ignore")
    line: str = ""
    moral: str = ""
    credit: str = ""


class Content(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: list[str] = Field(default_factory=list)
    brand: str = ""
    url: str = ""
    ui: UI = Field(default_factory=UI)
    subs: list[str] = Field(default_factory=list)           # four subtitles
    end: End = Field(default_factory=End)
    facts: list[dict] = Field(default_factory=list)
    mascot_shape: str = "circle"
    mascot_color: str = ""


EXAMPLE = {
    "brand": "ادیتور جی‌پی‌تی", "url": "editor.rafiei.co", "mascot_shape": "spark",
    "ui": {"app": "ادیتورجی‌پی‌تی", "nav": ["اینستاجی‌پی‌تی", "ویرایش جدید", "جست‌وجوی چت‌ها", "پروژه‌ها"], "recent_label": "اخیر",
           "recent": ["ریلز معرفی محصول", "دوبلهٔ انگلیسی وبینار", "اکسپلینر دراپ‌شیپینگ", "تدوین پریمیوم"], "heading": "چه چیزی می‌خواهید بسازید؟",
           "placeholder": "ویدیو یا ویرایش خود را توضیح دهید…", "chips": ["ریلز از ویدیوی بلند", "دوبله به انگلیسی", "موشن‌گرافیک از لینک محصول"],
           "attachment": "ویدیو.mp4 · ۳ دقیقه", "model": "ادیتورجی‌پی‌تی Lite", "prompt": "یه ریلز خفن از این ویدیو بساز", "project": "ریلز معرفی محصول",
           "working": "در حال کار", "ready": "✓ آماده", "reply": "ویدیو را دیدم. یک ریلز ۴۸ ثانیه‌ای با قلاب قوی می‌سازم.",
           "steps": ["رونویسی گفتار", "انتخاب قلاب", "استوری‌بورد", "برش و کپشن", "موشن و رنگ", "رندر نهایی"], "panel": ["استوری‌بورد", "پیش‌نمایش", "خروجی"],
           "board": ["قلاب", "مشکل", "راه‌حل", "اثبات", "پیشنهاد", "دعوت"], "preview": ["اولین فروش", "بدون انبار"], "tracks": ["برش", "کپشن", "موشن", "صدا"],
           "status": ["چیدن تایم‌لاین…", "رندر", "رندر تمام شد"], "count": 1440, "done": ["آماده شد.", "۴۸ ثانیه · ۱۰۸۰×۱۹۲۰ · −۱۴ LUFS"],
           "buttons": ["دانلود ویدیو", "خروجی پریمیر"],
           "tokens": {"bg": "#101010", "sidebar": "#171717", "surface": "#202020", "elevated": "#262626", "border": "#343434", "text": "#f5f5f5", "accent": "#f7a600"}},
    "subs": ["با یک جمله شروع شد.", "بعد، خودش کار کرد.", "تو خواب بودی.", "تا صبح، آماده بود."],
    "end": {"line": "از یک جمله، تا ویدیوی آماده.", "moral": "همه‌چیز با یک پیام شروع می‌شود.", "credit": "اتاق، نور، صفحه‌نمایش و تدوینِ این فیلم با کد ساخته شده است."},
    "facts": [{"claim": "از یک پیام ویدیوی آماده می‌سازد", "source": "README"}],
}

GUIDE = """THE FILM3D INTRO (landscape 1920x1080, 47 s, 24 fps, music only): one shot of a desk; a person types ONE sentence into the product on a laptop,
leaves, and the product finishes the work by morning: day -> dusk -> night -> morning. No narrator: four short subtitles and an end card. The product's
interface is shown live on the laptop screen as a chat-style studio: a home screen with a composer, then the person's message, six steps ticked one by
one, a plan of six cards, a preview with a four-track timeline and a progress bar, then a big «done».
Fill this JSON (Persian). The interface texts must be the product's REAL words when the FACTS show them (menu names, placeholder, button labels), else plain
generic words; sample project names and numbers are allowed in the interface but nothing the product cannot do:
- brand, url (without https://).
- ui: app (the name in the sidebar), nav (4 menu items), recent_label, recent (4 sample project names), heading (the home question), placeholder,
  chips (3 suggestions), attachment (a small file chip or ""), model (a small label or ""), prompt (the ONE sentence the person types, max 30 characters,
  colloquial), project (the project's title), working, ready (with ✓), reply (the product's first answer, max 60 characters),
  steps (exactly 6, max 16 characters each, in the order the product really works), panel (3 titles), board (6 labels, max 8 characters), preview (2 parts of
  a 3-4 word title), tracks (4 names), status (3 lines: arranging, working, finished), count (a whole number it counts to), done (2: a big word, one line
  of specs), buttons (1 or 2), tokens (the product's interface colours as #rrggbb: bg, sidebar, surface, elevated, border, text, accent; the FACTS' own when
  they give them, else a neutral dark theme).
- subs: exactly 4 subtitles of at most 22 characters: it began with one sentence / then it worked by itself / you were asleep / by morning it was ready.
- end: line (under the brand, max 30 characters), moral (one sentence, max 34 characters), credit (one honest line about how the film was made, max 60).
- mascot_shape: the simple shape closest to the brand's OWN mark (spark | circle | square | drop | hex | diamond | cloud); mascot_color #rrggbb or "".
- facts: every capability shown with its source."""


def plan(content: Content) -> tuple[dict, list[dict], float]:
    subs = [[a, b, text] for (a, b), text in zip(SUB_SPANS, content.subs)]
    events = [{"t": t, "k": k, "g": g} for t, k, g in EVENTS]
    return {"shots": SHOTS, "subs": subs, "end": END, "total": TOTAL}, events, TOTAL


def still_times(timing: dict) -> list[tuple[str, float]]:
    return [("desk", 2.6), ("typing", 8.6), ("mascot", 11.8), ("plan", 16.6), ("dusk", 20.6), ("night", 24.4), ("render", 28.6), ("low", 32.6), ("done", 37.0),
            ("morning", 41.2), ("end", 45.6)]


def texts(content: Content) -> list[str]:
    ui = content.ui
    return [t for t in [content.brand, ui.prompt, ui.heading, ui.reply, *ui.steps, *content.subs, content.end.line, content.end.moral] if t]


# ── plates ────────────────────────────────────────────────────────────────────

def _rgb(color: str) -> list[float] | None:
    color = (color or "").strip().lstrip("#")
    if len(color) != 6:
        return None
    try:
        return [round((int(color[i:i + 2], 16) / 255) ** 2.2, 4) for i in (0, 2, 4)]      # sRGB -> the scene's linear colours
    except ValueError:
        return None


def scene_of(content: Content) -> dict:
    """The Blender scene's parameters for this film. The studio's own mark (the spark) in its own colour is the kit's default scene."""
    shape = content.mascot_shape if content.mascot_shape in {"spark", "circle", "square", "drop", "hex", "diamond", "cloud"} else "circle"
    return {"mascot_shape": shape, "mascot_color": None if shape == "spark" and not content.mascot_color else _rgb(content.mascot_color), "wall": None, "poster": None}


def scene_key(scene: dict) -> str:
    return hashlib.sha256(json.dumps(scene, sort_keys=True).encode()).hexdigest()[:12]


def cache_root() -> Path:
    shared = HERE.parents[1] / "assets" / "models"
    base = shared if shared.is_dir() and os.access(shared, os.W_OK) else Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "editorgpt"
    return base / "intro_plates"


def bpy_python() -> str | None:
    """A Python interpreter that has Blender's `bpy` module (it needs its own Python version, so it is never this process's)."""
    exe = os.environ.get("INTRO_BPY_PYTHON", "").strip()
    return exe if exe and Path(exe).is_file() else None


class NeedsRenderer(RuntimeError):
    pass


def plates(content: Content, *, on_note=None, cancelled=None) -> Path:
    """The folder holding this film's plates (jpg + plates.json): the kit's for the default scene, else the cache, else rendered now with Blender."""
    scene = scene_of(content)
    if scene == DEFAULT_SCENE:
        return KIT_PLATES
    folder = cache_root() / scene_key(scene)
    if (folder / "plates.json").is_file():
        return folder
    exe = bpy_python()
    if not exe:
        raise NeedsRenderer("فیلم سه‌بعدی برای این برند به رندر تازهٔ صحنه نیاز دارد (مجسمهٔ روی میز باید نشان خود این برند باشد) و رندرر Blender روی این سرور نصب نیست. "
                            "سبک‌های قصه (story)، شوریل (reel) یا مجری (presenter) همین حالا برای این برند ساخته می‌شوند.")
    work = folder.with_name(folder.name + ".part")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    corners: dict = {}
    for n, (shot, light) in enumerate(RENDERS, 1):
        if cancelled and cancelled():
            raise InterruptedError("cancelled")
        if on_note:
            on_note(f"دارم نمای {n} از {len(RENDERS)} صحنهٔ سه‌بعدی را رندر می‌کنم ({shot}، نور {light})")
        out = work / f"{shot}_{light}.png"
        proc = subprocess.run([exe, str(SCENE), "--", shot, light, str(out), "40", "80"], env={**os.environ, "INTRO_SCENE": json.dumps(scene)},
                              capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0 or not out.is_file():
            raise RuntimeError("the 3D scene did not render: " + (proc.stderr or proc.stdout)[-300:])
        corners[f"{shot}_{light}"] = {"screen": json.loads(out.with_suffix(".json").read_text())["screen"]}
        _finish_plate(out, work / f"{shot}_{light}.jpg")
    for name in ("mascot_dusk", "mascot_night"):
        _foreground(work / f"{name}.jpg", work / f"{name}_fg.png", scene)
    (work / "plates.json").write_text(json.dumps(corners))
    for png in work.glob("*_*.png"):
        if not png.name.endswith("_fg.png"):
            png.unlink()
    work.replace(folder)
    return folder


def _finish_plate(png: Path, jpg: Path) -> None:
    from PIL import Image, ImageFilter
    image = Image.open(png).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.4, percent=60, threshold=2))
    image.save(jpg, quality=92)


def _foreground(plate: Path, out: Path, scene: dict) -> None:
    """The figurine standing in front of the laptop screen as an alpha layer, so the composited interface stays behind it: the pixels of the figurine's colour
    inside its part of the frame, holes closed, feathered."""
    import numpy as np
    from PIL import Image, ImageFilter
    image = np.asarray(Image.open(plate).convert("RGB")).astype(np.int16)
    r, g, b = image[..., 0], image[..., 1], image[..., 2]
    colour = scene.get("mascot_color")
    if colour:
        target = np.array([int(255 * c ** (1 / 2.2)) for c in colour], dtype=np.int16)
        mask = (np.abs(image - target[None, None, :]).sum(axis=2) < 150)
    else:
        mask = (r - b > 75) & (r > 110)
    box = np.zeros_like(mask)
    box[int(HEIGHT * 0.25):, int(WIDTH * 0.3):int(WIDTH * 0.85)] = True
    alpha = Image.fromarray(((mask & box) * 255).astype("uint8")).filter(ImageFilter.MaxFilter(31)).filter(ImageFilter.MinFilter(31)).filter(ImageFilter.GaussianBlur(1.6))
    layer = Image.open(plate).convert("RGBA")
    layer.putalpha(alpha)
    layer.save(out)
