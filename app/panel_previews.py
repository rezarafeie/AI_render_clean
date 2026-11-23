"""Real previews for the panel wizard.

* Sample clips: short muted loops and posters cut from finished films (the owner chose to show his own projects as each engine's samples). They live in
  job_data/panel_wizard/samples with a manifest (samples.json) written by build_samples(); the wizard lists them per engine and per Vox look.
* Talking stills: for each talking edit style, one 9:16 still built from a frame of the person's OWN uploaded video with that style's real geometry, crop,
  grade, fonts and colours (engine/talking_styles: talking_1 full frame + hook box, talking_2 picture/speaker split at SPLIT_Y with the yellow seam word,
  talking_3 cinematic split with teal-orange grade and vignette, talking_5 cream panel over a rounded speaker card at CARD_Y). Only the words are
  placeholders. Stills sit under an unguessable token for a day.
"""
from __future__ import annotations

import json
import logging
import random
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from app.config import settings

log = logging.getLogger(__name__)

ROOT = Path(settings.JOBS_DIR) / "panel_wizard"
SAMPLES = ROOT / "samples"
STILLS = ROOT / "tstills"
W, H = 1080, 1920
FONT_DIR = Path(__file__).resolve().parent.parent / "presets" / "fonts"


def samples() -> list[dict]:
    try:
        rows = json.loads((SAMPLES / "samples.json").read_text())
    except (OSError, ValueError):
        return []
    return [r for r in rows if (SAMPLES / r.get("video", "")).is_file() and (SAMPLES / r.get("poster", "")).is_file()]


def _probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def cut_sample(video: Path, sample_id: str, start_frac: float = 0.22, seconds: float = 9.0) -> tuple[str, str]:
    """A 9 s muted 540-wide loop and a poster from a finished film."""
    SAMPLES.mkdir(parents=True, exist_ok=True)
    total = _probe_seconds(video)
    start = max(0.0, min(total - seconds - 0.5, total * start_frac)) if total > seconds + 1 else 0.0
    clip, poster = f"{sample_id}.mp4", f"{sample_id}.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", f"{seconds:.2f}", "-i", str(video), "-an",
                    "-vf", "scale='if(gt(iw,ih),960,540)':-2,fps=30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(SAMPLES / clip)], check=True, timeout=600)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start + seconds * 0.45:.2f}", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale='if(gt(iw,ih),960,540)':-2", "-q:v", "4", str(SAMPLES / poster)], check=True, timeout=120)
    return clip, poster


def build_samples(picks: list[dict]) -> list[dict]:
    """picks: [{id, engine, title, look?, path}] -> the manifest (written atomically)."""
    rows = []
    for pick in picks:
        try:
            clip, poster = cut_sample(Path(pick["path"]), pick["id"], pick.get("start", 0.22))
        except Exception:
            log.warning("sample %s failed", pick.get("id"), exc_info=True)
            continue
        rows.append({k: pick[k] for k in ("id", "engine", "title", "look", "format", "summary") if pick.get(k)} | {"video": clip, "poster": poster})
    tmp = SAMPLES / "samples.json.tmp"
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    tmp.replace(SAMPLES / "samples.json")
    return rows


# ---- talking stills -------------------------------------------------------------------------------------------------------------------------------

def _font(name: str, size: int):
    from PIL import ImageFont
    for candidate in (FONT_DIR / name, FONT_DIR / "RAY-EXTRABLACK.TTF", FONT_DIR / "Vazirmatn-Regular.ttf"):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size, layout_engine=ImageFont.Layout.RAQM)
    return ImageFont.load_default()


def _text(draw, xy, text, font, fill, anchor="mm", stroke=0, stroke_fill="#000"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=stroke_fill)


def _frames(video: Path, count: int = 2) -> list:
    from PIL import Image
    total = _probe_seconds(video) or 10.0
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, frac in enumerate([0.35, 0.62][:count]):
            target = Path(tmp) / f"f{i}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{total * frac:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(target)],
                           check=True, timeout=120)
            out.append(Image.open(target).convert("RGB"))
    return out


def _face(video: Path) -> tuple[float, float]:
    """Normalised face centre from a 2 s slice (the same YuNet tracker the talking styles use); the frame centre if none."""
    try:
        from engine.talking_styles.talking_1 import track_faces
        total = _probe_seconds(video) or 10.0
        with tempfile.TemporaryDirectory() as tmp:
            piece = Path(tmp) / "p.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{total * 0.35:.2f}", "-t", "2", "-i", str(video), "-an", "-c:v", "libx264",
                            "-preset", "ultrafast", str(piece)], check=True, timeout=120)
            faces = track_faces(piece, fps=2.0)
        if faces:
            return sum(f[1] for f in faces) / len(faces), sum(f[2] for f in faces) / len(faces)
    except Exception:
        log.info("face track for the wizard preview failed", exc_info=True)
    return 0.5, 0.4


def _cover(img, w: int, h: int, face: tuple[float, float], zoom: float = 1.0, face_y: float = 0.42):
    """Crop img to w:h around the face (face at face_y of the height), zoomed in by zoom."""
    sw, sh = img.size
    aspect = w / h
    ch = min(sh, sw / aspect) / zoom
    cw = ch * aspect
    fx, fy = face[0] * sw, face[1] * sh
    x = min(max(0, fx - cw / 2), sw - cw)
    y = min(max(0, fy - ch * face_y), sh - ch)
    return img.crop((int(x), int(y), int(x + cw), int(y + ch))).resize((w, h))


def _grade(img, kind: str):
    from PIL import Image, ImageEnhance
    if kind == "warm":
        img = ImageEnhance.Color(img).enhance(1.08)
        return Image.blend(img, Image.new("RGB", img.size, (255, 196, 140)), 0.07)
    if kind == "cine":
        img = ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(0.9)).enhance(1.12)
        r, g, b = img.split()
        r = r.point(lambda v: min(255, int(v * 1.06 + 6)))
        b = b.point(lambda v: min(255, int(v * 0.92 + 18)))
        return Image.merge("RGB", (r, g, b))
    return img


def _vignette(size, strength: float = 0.75):
    from PIL import Image, ImageDraw, ImageFilter
    w, h = size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((-w * 0.25, -h * 0.12, w * 1.25, h * 1.12), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(w * 0.18))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, int(255 * strength)))
    dark.putalpha(Image.eval(mask, lambda v: int((255 - v) * strength)))
    return dark


def _rounded(img, radius: int):
    from PIL import Image, ImageDraw
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def _still(style: str, frames: list, face: tuple[float, float], title: str):
    from PIL import Image, ImageDraw, ImageFilter
    main, other = frames[0], frames[-1]
    heavy = "RAY-EXTRABLACK.TTF"
    hook = title or "عنوان ویدیوی تو اینجاست"
    if style == "talking_2":
        from engine.talking_styles.talking_2 import SPLIT_Y, YELLOW
        canvas = Image.new("RGB", (W, H), "#2a59d6")
        card = _rounded(_cover(other, 900, 680, (0.5, 0.45), 1.15), 46)
        canvas.paste(card, ((W - 900) // 2, (SPLIT_Y - 680) // 2 + 20), card)
        canvas.paste(_cover(main, W, H - SPLIT_Y, face, 1.25, 0.38), (0, SPLIT_Y))
        d = ImageDraw.Draw(canvas)
        _text(d, (W / 2, SPLIT_Y - 40), "نکتهٔ", _font(heavy, 58), "#ffffff", stroke=3)
        _text(d, (W / 2, SPLIT_Y + 60), "کلیدی", _font(heavy, 132), YELLOW, stroke=5)
        return canvas
    if style == "talking_3":
        from engine.talking_styles.talking_2 import SPLIT_Y
        top = _grade(_cover(other, W, SPLIT_Y + 160, (0.5, 0.45), 1.3), "cine")
        canvas = Image.new("RGB", (W, H), "#071012")
        canvas.paste(top, (0, 0))
        canvas.paste(_grade(_cover(main, W, H - SPLIT_Y, face, 1.2, 0.38), "cine"), (0, SPLIT_Y))
        fade = Image.new("RGBA", (W, 360), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fade)
        for y in range(360):
            fd.line([(0, y), (W, y)], fill=(5, 10, 12, int(230 * (1 - abs(y - 180) / 180))))
        canvas.paste(fade, (0, SPLIT_Y - 180), fade)
        rgba = canvas.convert("RGBA")
        rgba.alpha_composite(_vignette(rgba.size, 0.8))
        noise = Image.effect_noise((W // 2, H // 2), 40).resize((W, H)).convert("RGBA")
        noise.putalpha(22)
        rgba.alpha_composite(noise)
        d = ImageDraw.Draw(rgba)
        _text(d, (W - 90, 250), "فصل اول", _font("IRAN_Kharazmi/IRAN Kharazmi.ttf", 80), "#ffb36b", anchor="rm")
        _text(d, (W - 90, 360), hook[:22], _font(heavy, 92), "#ffffff", anchor="rm", stroke=2)
        _text(d, (W / 2, SPLIT_Y + 10), "هیچ‌وقت دیر نیست", _font(heavy, 70), "#ffffff", stroke=3)
        return rgba.convert("RGB")
    if style == "talking_5":
        from engine.talking_styles.talking_5 import CARD_RADIUS, CARD_Y
        canvas = Image.new("RGB", (W, H), "#EFE7DA")
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle((60, 120, W - 60, CARD_Y - 50), radius=48, fill="#FFFFFF", outline="#E2D6C3", width=3)
        _text(d, (W - 120, 230), "خبر تازه", _font("RAY-BOLD.TTF", 44), "#C2410C", anchor="rm")
        _text(d, (W / 2, 420), hook[:20], _font(heavy, 86), "#1D1B17")
        thumb = _rounded(_cover(other, 760, 300, (0.5, 0.45), 1.1), 30)
        canvas.paste(thumb, ((W - 760) // 2, 520), thumb)
        speaker = _rounded(_cover(main, W - 80, H - CARD_Y - 40, face, 1.15, 0.36), CARD_RADIUS)
        canvas.paste(speaker, (40, CARD_Y), speaker)
        _text(ImageDraw.Draw(canvas), (W / 2, H - 230), "این ابزار همه‌چیز را", _font(heavy, 84), "#FFFFFF", stroke=5)
        return canvas
    if style == "premium":
        img = _grade(_cover(main, W, H, face, 1.0, 0.36), "warm").convert("RGBA")
        img.alpha_composite(_vignette(img.size, 0.55))
        d = ImageDraw.Draw(img)
        _text(d, (W / 2, H * 0.72), "این یک", _font(heavy, 96), "#ffffff", stroke=4)
        _text(d, (W / 2, H * 0.72 + 130), "تغییر بزرگ است", _font(heavy, 120), "#FFD23F", stroke=5)
        return img.convert("RGB")
    # talking_1: full frame, warm grade, the hook pinned in a translucent dark rounded box with yellow highlight, short captions above it
    from engine.talking_styles.talking_1 import YELLOW
    img = _grade(_cover(main, W, H, face, 1.0, 0.36), "warm").convert("RGBA")
    box = Image.new("RGBA", (W - 140, 300), (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle((0, 0, W - 140, 300), radius=40, fill=(12, 12, 14, 165))
    img.alpha_composite(box, (70, int(H * 0.70)))
    d = ImageDraw.Draw(img)
    words = hook.split()
    _text(d, (W / 2, H * 0.70 + 105), " ".join(words[:3]) or hook, _font(heavy, 78), "#ffffff")
    _text(d, (W / 2, H * 0.70 + 205), " ".join(words[3:7]) or "را ببین", _font(heavy, 78), YELLOW)
    _text(d, (W / 2, H * 0.70 - 70), "هر روز فقط ده دقیقه", _font(heavy, 60), "#ffffff", stroke=4)
    return img.convert("RGB")


def talking_stills(video: Path, styles: list[str], title: str = "") -> tuple[str, dict[str, str]]:
    """One 540x960 JPEG per style from the person's own video; returns (token, {style: file})."""
    STILLS.mkdir(parents=True, exist_ok=True)
    for old in STILLS.iterdir():                      # a day is enough for a wizard session
        try:
            if time.time() - old.stat().st_mtime > 86400:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            pass
    frames = _frames(video)
    face = _face(video)
    token = secrets.token_urlsafe(18)
    folder = STILLS / token
    folder.mkdir()
    out = {}
    for style in styles:
        try:
            _still(style, frames, face, title).resize((540, 960)).save(folder / f"{style}.jpg", quality=82)
            out[style] = f"{style}.jpg"
        except Exception:
            log.warning("talking still %s failed", style, exc_info=True)
    random.seed()
    return token, out
