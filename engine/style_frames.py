"""Style preview frames: one frame of each talking style, built from that style's own parts.

Every preview uses the style module's real text layer (its ``build_ass``), real picture panels, seam,
vignette and colour treatment, composed on a still from the user's video — so typography, boxes,
positions and colours are the ones the renderer produces. What a single frame cannot show (cuts,
zooms, motion, per-sentence pictures) is not faked: the style 2 and 3 picture areas use a fixed sample
picture of the kind those styles generate. Callers still label the image "preview", not output.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from .render_ass import ass_burner_ffmpeg, subtitles_filter

ROOT = Path(__file__).resolve().parent.parent
STYLE_IDS = ("talking_1", "talking_2", "talking_3")
SAMPLE_PHOTO = ROOT / "assets" / "style_previews" / "cinematic_still.jpg"   # a style 3 still-life, generated once
SECONDS = 1.2   # entrance animations (pops, fades, slides) have settled by then
PREVIEW_VERSION = 4   # bump when previews change, so cached plan frames are rebuilt


class MockupUnavailable(RuntimeError):
    pass


def _ass_bgr(hex_colour: str) -> str:
    value = hex_colour.lstrip("#").upper()
    return f"&H00{value[4:6]}{value[2:4]}{value[0:2]}"


def _recolour(ass: str, old_hex: str, new_hex: str) -> str:
    """The renderers' own accent swap: both the inline ``&Hbbggrr&`` and the style ``&H00bbggrr`` forms."""
    from .talking_styles.talking_1 import _colour
    old, new = _colour(old_hex), _colour(new_hex)
    return ass.replace(old, new).replace(old.replace("&H", "&H00", 1)[:-1], new.replace("&H", "&H00", 1)[:-1])


def _crop(size: tuple[int, int], aspect: float, focus_y: float = 0.38) -> str:
    """Centre crop to ``aspect`` (w/h), keeping the upper body (where a speaker's face is) in frame."""
    w, h = size
    if w / h > aspect:
        cw, ch = int(h * aspect) // 2 * 2, h
    else:
        cw, ch = w, int(w / aspect) // 2 * 2
    x = (w - cw) // 2
    y = int(min(max(h * focus_y - ch / 2, 0), h - ch))
    return f"crop={cw}:{ch}:{x}:{y}"


def _grade_split(grade: dict) -> str:
    """talking_2/3 custom grade (same expression as their render)."""
    brightness = 1 + float(grade.get("brightness", 0)) / 100
    contrast = float(grade.get("contrast", 100)) / 100
    lut = f"(val*{brightness:.3f}-128)*{contrast:.3f}+128"
    return (f"lutrgb=r='{lut}':g='{lut}':b='{lut}',hue=s={float(grade.get('saturation', 100)) / 100:.3f},"
            f"colorbalance=rs={float(grade.get('temperature', 0)) / 500:.3f}:bs={-float(grade.get('temperature', 0)) / 500:.3f}")


def _grade_full(grade: dict) -> str:
    """talking_1 custom grade (same expression as its render)."""
    brightness = 1 + float(grade.get("brightness", 0)) / 100
    return (f"lutyuv=y='val*{brightness:.3f}',eq=contrast={float(grade.get('contrast', 100)) / 100:.3f}:"
            f"saturation={float(grade.get('saturation', 100)) / 100:.3f},"
            f"colorbalance=rs={float(grade.get('temperature', 0)) / 500:.3f}:bs={-float(grade.get('temperature', 0)) / 500:.3f}")


ICON_ACCENT = "#D9962B"   # the muted amber the style 2 picture prompt asks for (app/talking_reel._visual_prompt)


def motion_icon(out: Path) -> Path:
    """A flat editorial illustration like the style 2 pictures (off-white, charcoal line, one muted amber accent):
    a rising bar chart with an arrow and speed lines, to show that this style adds explanatory graphics.
    Like the real pictures it does not take the user's caption accent colour."""
    accent = ICON_ACCENT
    from PIL import Image, ImageDraw
    size = (1200, 1000)
    ink, paper = (43, 43, 43), (242, 239, 232)
    img = Image.new("RGB", size, paper)
    draw = ImageDraw.Draw(img)
    base_y, left = 800, 300
    for k, height in enumerate((200, 330, 470)):
        x = left + k * 190
        draw.rounded_rectangle((x, base_y - height, x + 130, base_y), radius=18, outline=ink, width=14,
                               fill=accent if k == 2 else paper)
    draw.line((230, base_y, 960, base_y), fill=ink, width=14)
    draw.line((300, 610, 520, 470, 690, 520, 930, 250), fill=accent, width=22, joint="curve")
    draw.polygon(((975, 205), (880, 225), (950, 295)), fill=accent)
    for k, y in enumerate((300, 360, 420)):
        draw.line((150 + k * 25, y, 250 + k * 25, y), fill=ink, width=12)
    img.save(out)
    return out


def _talking_1(work: Path, fonts: Path, d: dict) -> tuple[list[str], str, str]:
    from .talking_styles import talking_1 as t1
    caption = (t1.phrases(d["caption"], 6) or [d["caption"]])[0]
    plan = t1.ReelPlan(shots=[], captions=[{"start": 0, "end": 5, "text": caption}], duration=5)
    ass = t1.build_ass(plan, d["hook"], d["highlight"], d["name"], d["tagline"], fonts, moments=False,
                       caption_font="Vazirmatn" if d["caption_font"] == "Vazirmatn" else None)
    ass = _recolour(ass, t1.YELLOW, d["accent"])
    graph = (f"[0:v]{_crop(d['size'], 9 / 16)},scale={t1.W}:{t1.H}:flags=lanczos,{_grade_full(d['grade'])}[base];"
             f"[1:v]format=rgba,colorchannelmixer=aa={d['vignette']:.3f}[vig];[base][vig]overlay=0:0")
    return [str(t1.vignette_png(work / "vignette.png"))], graph, ass


def _split_plan(d: dict, *, split: bool, theme: str):
    from .talking_styles import talking_2 as t2
    words = d["caption"].split() or ["…"]
    shot = t2.Shot(src_in=0, src_out=5, split=split)
    plan = t2.ReelPlan(shots=[shot], captions=[{"start": 0, "end": 5, "lead": " ".join(words[-3:-1]), "key": words[-1]}],
                       duration=5, theme=theme, continuous_split=split)
    return plan


def _talking_2(work: Path, fonts: Path, d: dict) -> tuple[list[str], str, str]:
    from .caption_preferences import caption_font
    from .talking_styles import talking_2 as t2
    panel = t2.picture_panel(motion_icon(work / "icon.png"), work / "panel.png")
    ass = _recolour(caption_font(t2.build_ass(_split_plan(d, split=True, theme="editorial"), fonts),
                                 {"caption_font": d["caption_font"]}), t2.YELLOW, d["accent"])
    graph = (f"[1:v]scale={t2.W}:{t2.SPLIT_Y}:flags=lanczos,setsar=1[top];"
             f"[0:v]{_crop(d['size'], t2.W / (t2.H - t2.SPLIT_Y))},scale={t2.W}:{t2.H - t2.SPLIT_Y}:flags=lanczos,"
             f"setsar=1,{_grade_split(d['grade'])}[bottom];[top][bottom]vstack=inputs=2[base];"
             f"[2:v]format=rgba,colorchannelmixer=aa={d['vignette']:.3f}[vig];[base][vig]overlay=0:0")
    from .talking_styles.talking_1 import vignette_png
    return [str(panel), str(vignette_png(work / "vignette.png"))], graph, ass


def _talking_3(work: Path, fonts: Path, d: dict) -> tuple[list[str], str, str]:
    from .caption_preferences import caption_font
    from .talking_styles import talking_3 as t3
    from .talking_styles.talking_1 import vignette_png
    if not SAMPLE_PHOTO.is_file():
        raise MockupUnavailable("style 3 sample picture is missing")
    panel = t3.bleed_panel(SAMPLE_PHOTO, work / "panel.png", (t3.W, t3.SPLIT_Y))
    plan = _split_plan(d, split=True, theme="editorial")
    plan.titles = [{"start": 0, "end": 5, "text": d["card"]}]
    plan.card_pictures, plan.full_pictures = set(), set()
    ass = caption_font(t3.build_ass(plan, fonts), {"caption_font": d["caption_font"]})
    ass = ass.replace(t3.ACCENT_COLOUR, _ass_bgr(d["accent"]))
    graph = (f"[1:v]scale={t3.W}:{t3.SPLIT_Y}:flags=lanczos,setsar=1[top];"
             f"[0:v]{_crop(d['size'], t3.W / (t3.H - t3.SPLIT_Y))},scale={t3.W}:{t3.H - t3.SPLIT_Y}:flags=lanczos,"
             f"setsar=1,{_grade_split(d['grade'])}[bottom];[top][bottom]vstack=inputs=2[stack];"
             f"[2:v]format=rgba[seam];[stack][seam]overlay=0:0[seamed];"
             f"[3:v]format=rgba,colorchannelmixer=aa={d['vignette']:.3f}[vig];[seamed][vig]overlay=0:0")
    return [str(panel), str(t3.seam_png(work / "seam.png")), str(vignette_png(work / "vignette.png"))], graph, ass


def _talking_4(work: Path, fonts: Path, d: dict) -> tuple[list[str], str, str]:
    from .caption_preferences import caption_font
    from .talking_styles import talking_2 as t2
    from .talking_styles.talking_1 import vignette_png
    ass = caption_font(t2.build_ass(_split_plan(d, split=False, theme="minimal"), fonts), {"caption_font": d["caption_font"]})
    graph = (f"[0:v]{_crop(d['size'], 9 / 16)},scale={t2.W}:{t2.H}:flags=lanczos,setsar=1,{_grade_split(d['grade'])}[base];"
             f"[1:v]format=rgba,colorchannelmixer=aa={d['vignette']:.3f}[vig];[base][vig]overlay=0:0")
    return [str(vignette_png(work / "vignette.png"))], graph, ass


BUILDERS = {"talking_1": _talking_1, "talking_2": _talking_2, "talking_3": _talking_3, "talking_4": _talking_4}


def render_mockup(video: Path, out: Path, *, style_id: str, at: float, hook: str, highlight: list[str] | None = None,
                  caption: str = "", card: str = "", accent: str = "#F5B800", name: str = "", tagline: str = "",
                  grade: dict | None = None, caption_font: str = "default", width: int = 540, source_still: Path | None = None) -> Path:
    """Write a JPEG preview of ``style_id`` on the frame of ``video`` at ``at`` seconds."""
    if style_id not in BUILDERS:
        raise MockupUnavailable(f"unknown style {style_id!r}")
    ffmpeg = ass_burner_ffmpeg()
    if ffmpeg is None:
        raise MockupUnavailable("no ffmpeg with libass is available for style previews")
    accent = "#" + accent.lstrip("#").upper() if re.fullmatch(r"#?[0-9A-Fa-f]{6}", accent or "") else "#F5B800"
    grade = grade or {}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        still = source_still or work / "frame.png"
        if source_still is None:
            grab = subprocess.run([ffmpeg, "-v", "error", "-y", "-threads", "1", "-ss", f"{max(0.0, at):.2f}", "-i", str(video),
                                   "-vf", "scale=720:-2", "-frames:v", "1", "-threads", "1", str(still)], capture_output=True, text=True, timeout=20)
            if grab.returncode != 0 or not still.is_file():
                raise MockupUnavailable((grab.stderr or "could not read a frame").strip()[-300:])
        from PIL import Image
        with Image.open(still) as image:
            size = image.size
        from .talking_styles.talking_1 import fonts_bundle
        fonts = fonts_bundle(work)
        data = {"hook": hook or "", "highlight": [w for w in (highlight or []) if w and w in (hook or "")][:2],
                "caption": caption or hook or "", "card": card or hook or "", "accent": accent, "name": name,
                "tagline": tagline, "grade": grade, "vignette": max(0.0, min(1.0, float(grade.get("vignette", 50)) / 100)),
                "caption_font": caption_font, "size": size}
        extra, graph, ass_text = BUILDERS[style_id](work, fonts, data)
        ass = work / "preview.ass"
        ass.write_text(ass_text, encoding="utf-8")
        inputs = ["-threads", "1", "-itsoffset", str(SECONDS), "-loop", "1", "-framerate", "30", "-t", f"{SECONDS + 0.3:.2f}", "-i", str(still)]
        for path in extra:
            inputs += ["-threads", "1", "-itsoffset", str(SECONDS), "-loop", "1", "-framerate", "30", "-t", f"{SECONDS + 0.3:.2f}", "-i", path]
        graph += f",{subtitles_filter(ass, fonts)},scale={width}:-2[out]"
        command = [ffmpeg, "-v", "error", "-y", "-filter_threads", "1", "-filter_complex_threads", "1", *inputs, "-filter_complex", graph, "-map", "[out]",
                   "-ss", f"{SECONDS:.2f}", "-threads", "1", "-frames:v", "1", "-q:v", "3", str(out)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    if result.returncode != 0 or not out.is_file():
        raise MockupUnavailable((result.stderr or "ffmpeg failed").strip()[-300:])
    return out
