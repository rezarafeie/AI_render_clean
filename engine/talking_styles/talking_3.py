"""Talking-head style "صحبتی ۳" (talking_3): cinematic split screen.

* mostly split: a full-bleed cinematic picture on top (slow push), the
  speaker below, the seam a soft dark gradient rather than a line; every
  other picture is shown as a tilted, glowing card on a blurred dark copy
  of itself; a long picture moment opens full frame
* minimal captions: one to three white words on the seam, no box
* editorial chapter titles (calligraphic accent word + heavy line) slide in
  at the turns of the talk; the hook opens the same way over the cold open
* moody teal-orange grade, film grain, strong vignette, cinematic pulse
  music at -14 LUFS; the same CTA card and logo outro as "صحبتی ۱"

Planning comes from "صحبتی ۲" (talking_2), which is frozen like talking_1.
"""
from __future__ import annotations

import hashlib
import logging
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

from ..localize import _ass_time, measure_text_boxes, probe_fps, probe_video
from ..render_ass import ass_burner_ffmpeg, subtitles_filter
from . import talking_2 as split
from .talking_1 import (W, H, _esc, eval_fps, fonts_bundle, music_bed, persian_digits, render_outro,
                        track_faces, vignette_png)
from .talking_2 import SPLIT_Y, ReelPlan, Shot, speaker_crop

log = logging.getLogger(__name__)

__all__ = ["track_faces", "plan_reel", "render", "probe_video"]

FONT = "Ray ExtraBlack"
CAPTION_FONT = "Ray ExtraBold"
ACCENT_FONT = "IRAN Kharazmi"
ACCENT_COLOUR = "&H00A8D8F0"      # warm cream for the calligraphic accent (ASS BGR)
PICTURE_ZOOM = 0.08
MUSIC_DB = -14.0
LOUDNESS = -14.0
GRADE = ("eq=contrast=1.13:saturation=0.92:gamma=0.96,"
         "colorbalance=rs=-0.04:gs=0.0:bs=0.05:rm=-0.01:bm=0.02:rh=0.06:gh=0.01:bh=-0.05,"
         "curves=master='0/0.02 0.25/0.2 0.5/0.5 0.8/0.84 1/0.96',unsharp=5:5:0.5")


def plan_reel(transcript: dict, decisions: dict, faces, duration: float,
              pictures: Optional[dict[int, str]] = None) -> ReelPlan:
    """The split plan of "صحبتی ۲" plus chapter titles; long picture moments open full frame."""
    plan = split.plan_reel(transcript, decisions, faces, duration, pictures)
    plan.cards = []          # no text cards: a slot without a picture shows the speaker instead
    for shot in plan.shots:
        if shot.split and not shot.picture and not any(c["start"] <= shot.out_start < c["end"] for c in plan.chips):
            shot.split = False
    main = plan.shots[1:] if plan.cold_open else plan.shots

    def out_time(src: float) -> float:
        for shot in main:
            if src < shot.src_in:
                return shot.out_start
            if src <= shot.src_out:
                return shot.out_start + src - shot.src_in
        return plan.duration

    sentences = transcript["sentences"]
    titles = []
    for title in decisions.get("titles") or []:
        start = out_time(sentences[title["i"]]["start"])
        if start >= (plan.hook or {}).get("end", 0) + 0.5:
            titles.append({"start": start, "end": min(plan.duration, start + 2.4), "text": persian_digits(title["text"])})
    plan.titles = titles
    # Unlike style 2, every generated visual is a full-screen cinematic
    # cutaway. This keeps the two styles unmistakably different.
    plan.card_pictures, plan.full_pictures = set(), set()
    for group in split._groups(main):
        if not group[0].picture:
            continue
        plan.full_pictures.update(id(shot) for shot in group)
    plan.chips = []
    return plan


# --- pictures ---------------------------------------------------------------------

def bleed_panel(picture: Path, out: Path, size: tuple[int, int]) -> Path:
    """The picture filling the area (12% oversize for the push), its bottom edge fading to black."""
    import numpy as np
    from PIL import Image, ImageOps

    pw, ph = int(size[0] * 1.12), int(size[1] * 1.12)
    image = ImageOps.fit(Image.open(picture).convert("RGB"), (pw, ph), Image.LANCZOS)
    if size[1] < H:   # the top half: fade into the seam
        arr = np.asarray(image).astype(np.float32)
        ramp = np.clip((np.arange(ph) - ph * 0.8) / (ph * 0.2), 0, 1)[:, None, None]
        arr *= 1 - ramp * 0.85
        image = Image.fromarray(arr.astype(np.uint8))
    image.save(out)
    return out


def card_panel(picture: Path, out: Path) -> Path:
    """The picture as a tilted, glowing card on a blurred, darkened copy of itself (top half)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageOps

    pw, ph = int(W * 1.12), int(SPLIT_Y * 1.12)
    src = Image.open(picture).convert("RGB")
    bg = ImageOps.fit(src, (pw, ph), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
    bg = Image.fromarray((np.asarray(bg).astype(np.float32) * 0.35).astype(np.uint8))
    cw, ch = int(pw * 0.66), int(ph * 0.62)
    card = ImageOps.fit(src, (cw, ch), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=28, fill=255)
    card.putalpha(mask)
    # Perspective: the right edge recedes (a card turned slightly away).
    dx, dy = int(cw * 0.08), int(ch * 0.07)
    canvas = Image.new("RGBA", (cw + 2 * dx, ch + 2 * dy), (0, 0, 0, 0))
    canvas.alpha_composite(card, (dx, dy))
    w2, h2 = canvas.size
    quad = (0, 0, -dx * 0.2, h2, w2 + dx * 0.0, h2 - dy * 1.6, w2, dy * 1.6)
    tilted = canvas.transform(canvas.size, Image.QUAD, quad, Image.BICUBIC)
    glow = Image.new("RGBA", tilted.size, (255, 214, 160, 0))
    glow.putalpha(tilted.getchannel("A").filter(ImageFilter.GaussianBlur(30)).point(lambda v: int(v * 0.55)))
    shadow = Image.new("RGBA", tilted.size, (0, 0, 0, 0))
    shadow.putalpha(tilted.getchannel("A").filter(ImageFilter.GaussianBlur(24)).point(lambda v: int(v * 0.8)))
    frame = bg.convert("RGBA")
    x, y = (pw - w2) // 2, (ph - h2) // 2
    frame.alpha_composite(shadow, (x + 14, y + 26))
    frame.alpha_composite(glow, (x, y))
    frame.alpha_composite(tilted, (x, y))
    arr = np.asarray(frame.convert("RGB")).astype(np.float32)
    ramp = np.clip((np.arange(ph) - ph * 0.82) / (ph * 0.18), 0, 1)[:, None, None]
    Image.fromarray((arr * (1 - ramp * 0.85)).astype(np.uint8)).save(out)
    return out


def seam_png(out: Path) -> Path:
    """A soft dark band across the seam: the two halves blend, the captions read."""
    import numpy as np
    from PIL import Image

    y = np.arange(H, dtype=np.float32)
    band = np.exp(-((y - SPLIT_Y) / 70.0) ** 2) * 0.7
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[..., 3] = (band[:, None] * 255).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(out)
    return out


# --- overlay (ASS) -----------------------------------------------------------------

def build_ass(plan: ReelPlan, fonts_dir: Optional[Path]) -> str:
    events: list[str] = []
    split_spans = [(s.out_start, s.out_start + s.length) for s in plan.shots if s.split and id(s) not in plan.full_pictures]

    def on_split(t: float) -> bool:
        return any(a <= t < b for a, b in split_spans)

    hook_end = plan.hook["end"] if plan.hook else 0.0
    quiet = [(t["start"], t["end"]) for t in plan.titles]
    for c in plan.captions:
        if c["end"] <= hook_end:
            continue
        start = max(c["start"], hook_end)
        text = f"{c['lead']} {c['key']}".strip()
        y = SPLIT_Y if on_split(start) else H * 0.79
        events.append(f"Dialogue: 4,{_ass_time(start)},{_ass_time(c['end'])},cap,,0,0,0,,"
                      f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.0f})\\fad(90,90)}}{_esc(text)}")

    def editorial(t0: float, t1: float, text: str, y: float) -> None:
        words = text.split()
        accent, main = (words[0], " ".join(words[1:])) if len(words) >= 2 else ("", text)
        size = int(H * 0.085)
        width = measure_text_boxes([(_esc(main), size)], W, H, FONT, fonts_dir)[0][0]
        size = min(size, int(size * W * 0.86 / max(1, width)))
        slide = f"\\fad(260,300)\\move({W / 2:.0f},{y + 40:.0f},{W / 2:.0f},{y:.0f},0,420)"
        if accent:
            events.append(f"Dialogue: 6,{_ass_time(t0)},{_ass_time(t1)},accent,,0,0,0,,"
                          f"{{\\an2\\q2\\fad(260,300)\\move({W / 2:.0f},{y - size * 0.95 + 30:.0f},{W / 2:.0f},"
                          f"{y - size * 0.95:.0f},80,500)}}{_esc(accent)}")
        events.append(f"Dialogue: 6,{_ass_time(t0 + 0.12)},{_ass_time(t1)},title,,0,0,0,,"
                      f"{{\\an8\\q2{slide}\\fs{size}\\fscx88}}{_esc(main)}")

    if plan.hook:
        editorial(plan.hook["start"] + 0.1, plan.hook["end"], plan.hook["text"],
                  H * 0.24 if on_split(plan.hook["start"]) else H * 0.6)
    for title in plan.titles:
        editorial(title["start"], title["end"], title["text"], H * 0.22 if on_split(title["start"]) else H * 0.3)

    chip_size = int(H * 0.04)
    for chip in plan.chips:
        items = chip["items"]
        inks = measure_text_boxes([(_esc(i), chip_size) for i in items], W, H, FONT, fonts_dir)
        step = min(0.45, (chip["end"] - chip["start"]) * 0.5 / max(1, len(items)))
        for k, (item, (iw, ia, ib)) in enumerate(zip(items, inks)):
            y = SPLIT_Y / 2 + (k - (len(items) - 1) / 2) * chip_size * 1.9
            t0 = chip["start"] + 0.15 + k * step
            half = iw / 2 + chip_size * 0.7
            top, bottom = y + ia - chip_size * 0.36, y + ib + chip_size * 0.36
            from ..localize import _rounded_rect
            events.append(_rounded_rect(2, t0, chip["end"], W / 2 - half, top, W / 2 + half, bottom, "#FFFFFF",
                                        (bottom - top) / 2, extra="\\1a&HD8&\\fad(150,0)"))
            events.append(f"Dialogue: 3,{_ass_time(t0)},{_ass_time(chip['end'])},chip,,0,0,0,,"
                          f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.1f})\\fad(150,0)}}{_esc(item)}")

    white = "&H00FFFFFF"
    soft = "&H70000000"
    styles = [
        f"Style: cap,{CAPTION_FONT},{int(H * 0.035)},{white},&H000000FF,{soft},{soft},"
        "-1,0,0,0,100,100,0,0,1,0.7,1.5,5,0,0,0,-1",
        f"Style: title,{FONT},{int(H * 0.07)},{white},&H000000FF,{soft},&H80000000,"
        "-1,0,0,0,100,100,0,0,1,0,3,8,0,0,0,-1",
        f"Style: accent,{ACCENT_FONT},{int(H * 0.058)},{ACCENT_COLOUR},&H000000FF,{soft},&H80000000,"
        "0,0,0,0,100,100,0,0,1,0,2,2,0,0,0,-1",
        f"Style: chip,{FONT},{chip_size},{white},&H000000FF,{soft},&H80000000,-1,0,0,0,100,100,0,0,1,0,1,5,0,0,0,-1",
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

def render(video: Path, plan: ReelPlan, out: Path, *, work_dir: Path, music: Optional[Path] = None,
           cta: str = "", render_settings: Optional[dict] = None,
           logo_path: Optional[Path] = None, overlay: Optional[Path] = None,
           on_progress: Optional[Callable[[int], None]] = None, on_stage=None, **_ignored) -> Path:
    """`overlay`: optional transparent WebM from engine/tscaps_overlay.py, composited above the ASS layer."""
    if on_stage: on_stage('rendering composition', 'در حال ترکیب قاب سینمایی، گوینده، زیرنویس و صدا')
    ffmpeg = ass_burner_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("Talking reels need an ffmpeg with libass (brew install ffmpeg-full)")
    settings = render_settings or {}
    gs = settings.get("grade") or {}
    brightness = 1 + float(gs.get("brightness", 0)) / 100
    contrast = float(gs.get("contrast", 100)) / 100
    custom_grade = (f"lutrgb=r='(val*{brightness:.3f}-128)*{contrast:.3f}+128':"
                    f"g='(val*{brightness:.3f}-128)*{contrast:.3f}+128':"
                    f"b='(val*{brightness:.3f}-128)*{contrast:.3f}+128',"
                    f"hue=s={float(gs.get('saturation', 100)) / 100:.3f},"
                    f"colorbalance=rs={float(gs.get('temperature', 0)) / 500:.3f}:"
                    f"bs={-float(gs.get('temperature', 0)) / 500:.3f}")
    sw, sh, _ = probe_video(video)
    fps = probe_fps(video)
    fps_value = eval_fps(fps)
    work_dir.mkdir(parents=True, exist_ok=True)
    fonts = fonts_bundle(work_dir)
    ass = work_dir / "reel3.ass"
    ass_text = build_ass(plan, fonts)
    from engine.caption_preferences import caption_font
    ass_text = caption_font(ass_text, settings)
    from engine.caption_looks import apply as apply_caption_looks
    ass_text = apply_caption_looks(ass_text, plan.captions)
    title_color = str(settings.get("title_color") or "")
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", title_color):
        ass_text = ass_text.replace(ACCENT_COLOUR, "&H00" + title_color[5:7] + title_color[3:5] + title_color[1:3])
    ass.write_text(ass_text, encoding="utf-8")
    logo = settings.get("outro_logo") or {}
    outro, outro_seconds = render_outro(work_dir, cta.strip(), fps, fonts,
                                        logo_enabled=logo.get("enabled", True), logo_motion=logo.get("motion", "pop"),
                                        logo_path=logo_path)
    total = plan.duration + outro_seconds

    panels: dict[tuple, Path] = {}

    def panel(picture: str, kind: str) -> Path:
        key = (picture, kind)
        if key not in panels:
            digest = hashlib.sha256(f"{picture}|{kind}".encode()).hexdigest()[:12]
            dst = work_dir / f"p3_{kind}_{digest}.png"
            if kind == "card":
                panels[key] = card_panel(Path(picture), dst)
            elif kind == "full":
                panels[key] = bleed_panel(Path(picture), dst, (W, H))
            else:
                panels[key] = bleed_panel(Path(picture), dst, (W, SPLIT_Y))
        return panels[key]

    from PIL import Image
    plain = work_dir / "p3_plain.png"
    Image.new("RGB", (int(W * 1.12), int(SPLIT_Y * 1.12)), "#0B0C0E").save(plain)

    n = len(plan.shots)
    source_colour = split.base.source_colour_filter(video)
    inputs = ["-i", str(video)]
    vf = [f"[0:v]split={n}" + "".join(f"[s{k}]" for k in range(n)),
          f"[0:a]asplit={n}" + "".join(f"[r{k}]" for k in range(n))]
    nxt = 1
    zoom = settings.get("zoom") or {}
    zoom_amount = float(zoom.get("amount", 100)) / 100 if zoom.get("enabled", True) else 0.0
    base_zoom = float(zoom.get("base_scale", 100)) / 100 if zoom.get("enabled", True) else 1.0
    close_zoom = float(zoom.get("close_scale", 140)) / 100 if zoom.get("enabled", True) else 1.0
    for k, shot in enumerate(plan.shots):
        frames = max(1, round(shot.length * fps_value))
        cw, ch, x, y = speaker_crop(shot, sw, sh, base_zoom, close_zoom)
        cut = f"[s{k}]trim={shot.src_in:.3f}:{shot.src_out:.3f},setpts=PTS-STARTPTS,crop={cw}:{ch}:{x}:{y}"
        push = f"zoompan=z='1.0+{PICTURE_ZOOM * zoom_amount:.4f}*on/{frames}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1"
        if shot.split and id(shot) in plan.full_pictures:
            inputs += ["-loop", "1", "-framerate", fps, "-t", f"{shot.length:.3f}", "-i", str(panel(shot.picture, "full"))]
            vf.append(f"[{nxt}:v]{push}:s={W}x{H}:fps={fps},setsar=1[v{k}]")
            vf.append(f"[s{k}]trim=0:0.04,nullsink")
            nxt += 1
        elif shot.split:
            kind = "card" if shot.picture in plan.card_pictures else "bleed"
            top = panel(shot.picture, kind) if shot.picture else plain
            inputs += ["-loop", "1", "-framerate", fps, "-t", f"{shot.length:.3f}", "-i", str(top)]
            vf.append(f"[{nxt}:v]{push}:s={W}x{SPLIT_Y}:fps={fps},setsar=1[t{k}]")
            vf.append(f"{cut},{source_colour},scale={W}:{H - SPLIT_Y}:flags=lanczos,fps={fps},setsar=1,{custom_grade}[b{k}]")
            vf.append(f"[t{k}][b{k}]vstack=inputs=2[v{k}]")
            nxt += 1
        else:
            # Full-frame speaker: a slow push-in, close on alternate shots.
            vf.append(f"{cut},scale={W * 3 // 2}:{H * 3 // 2}:flags=lanczos,"
                      f"zoompan=z='1.0+{0.05 * zoom_amount:.4f}*on/{frames}':x='iw/2-iw/zoom/2':y='ih*0.4-ih/zoom*0.4':d=1:s={W}x{H}:fps={fps},"
                      f"{source_colour},setsar=1,{custom_grade}[v{k}]")
        fade = min(0.012, shot.length / 4)
        vf.append(f"[r{k}]atrim={shot.src_in:.3f}:{shot.src_out:.3f},asetpts=PTS-STARTPTS,"
                  f"afade=t=in:d={fade:.3f},afade=t=out:st={shot.length - fade:.3f}:d={fade:.3f}[a{k}]")
    vf.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca]")
    inputs += ["-loop", "1", "-framerate", fps, "-i", str(seam_png(work_dir / "p3_seam.png"))]
    vf.append(f"[{nxt}:v]format=rgba[seam]")
    nxt += 1
    inputs += ["-loop", "1", "-framerate", fps, "-i", str(vignette_png(work_dir / "vignette.png"))]
    vignette_alpha = max(0.0, min(1.0, float(gs.get("vignette", 50)) / 100))
    vf.append(f"[{nxt}:v]format=rgba,colorchannelmixer=aa={vignette_alpha:.3f}[vig]")
    nxt += 1
    split_times = "+".join(f"between(t,{s.out_start:.3f},{s.out_start + s.length:.3f})" for s in plan.shots
                           if s.split and id(s) not in plan.full_pictures) or "0"
    content = "vmain" if outro else "vout"
    vf.append(f"[cv][seam]overlay=0:0:format=auto:shortest=1:enable='{split_times}'[cs]")
    if overlay:
        inputs += ["-c:v", "libvpx-vp9", "-i", str(overlay)]
        vf.append(f"[cs][vig]overlay=0:0:format=auto:shortest=1,noise=alls=7:allf=t,"
                  f"{subtitles_filter(ass, fonts)},format=yuv420p[vbase]")
        vf.append(f"[{nxt}:v]format=yuva420p,setpts=PTS-STARTPTS[tso]")
        vf.append(f"[vbase][tso]overlay=0:0:format=auto:eof_action=pass,format=yuv420p[{content}]")
        nxt += 1
    else:
        vf.append(f"[cs][vig]overlay=0:0:format=auto:shortest=1,noise=alls=7:allf=t,"
                  f"{subtitles_filter(ass, fonts)},format=yuv420p[{content}]")
    if outro:
        inputs += ["-i", str(outro)]
        vf.append(f"[{nxt}:v]setsar=1,format=yuv420p[vend]")
        vf.append("[vmain][vend]concat=n=2:v=1:a=0[vout]")
        nxt += 1
    vf.append(f"[ca]apad=pad_dur={outro_seconds + 0.1:.3f}[cpad]")
    loud = f"loudnorm=I={LOUDNESS}:TP=-1:LRA=8,aresample=48000[aout]"
    if music and music.is_file():
        inputs += ["-i", str(music_bed(music, total + 1.0, work_dir))]
        from engine import music_mix
        mix = music_mix.resolve("talking_3", render_settings)
        vf.append(mix.bed(nxt, total))
        vf.extend(mix.graph(loud))
    else:
        vf.append(f"[cpad]{loud}")
    cmd = [ffmpeg, "-hide_banner", "-y", *inputs, "-filter_complex", ";".join(vf),
           "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-crf", "17", "-preset", "medium",
           "-profile:v", "high", "-level:v", "4.2", "-pix_fmt", "yuv420p",
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
                try: on_progress(min(99, int(int(row.split("=")[1]) / 1e6 / total * 100)))
                except ValueError: pass
    except BaseException:
        proc.terminate(); proc.wait(timeout=5); out.unlink(missing_ok=True); raise
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {split.base.ffmpeg_error(''.join(log_tail))}")
    return out


# --- Tscaps layer for the hook and key moments (additive: without it the output is the built-in ASS rendering) -----

render_plain = render


def render(video: Path, plan: ReelPlan, out: Path, *, work_dir: Path, **kwargs) -> Path:  # noqa: F811
    """The hook and the key-moment titles are drawn by the Tscaps engine; captions and chips stay built-in."""
    if kwargs.get("overlay") is not None:
        return render_plain(video, plan, out, work_dir=work_dir, **kwargs)
    from engine import tscaps_overlay as tso
    spans = [(s.out_start, s.out_start + s.length) for s in plan.shots if s.split and id(s) not in plan.full_pictures]

    def over_split(t: float) -> bool:
        return any(a <= t < b for a, b in spans)

    cues = (tso.hook_cue(plan.hook, accent_first=True, y_for=lambda t: 0.27 if over_split(t) else None)
            + tso.title_cues(plan.titles, y_for=lambda t: 0.26 if over_split(t) else 0.34))
    fps = int(round(eval_fps(probe_fps(video)) or 30))
    return tso.render_with_overlay(render_plain, video, plan, out, work_dir=work_dir, cues=cues,
                                   strip=lambda p: tso.without_hook(p, titles=[]), fps=fps, duration=plan.duration, **kwargs)
