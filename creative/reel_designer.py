"""A storyboard video designed by the motion designer, scene by scene, instead of poured into one fixed page.

The approved storyboard (its words, its timing, its narration, its pictures) is the brief. Each scene is authored by the same designer the motion-graphic
engine uses (HTML + CSS + GSAP written for THIS content, with the product pictures available, validated before anything is rendered), the scenes are
assembled with their entrances, the narration and a ducked music bed, checked in the browser and rendered by HyperFrames.

It can only raise the ceiling: when anything fails the caller keeps the built-in reel page, so a video is still produced.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import re
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import motion_graphic as mg
from . import narration_take
from . import visual_gate
from .schemas import CreativeUnavailable

log = logging.getLogger(__name__)

MAX_PARALLEL = 3
PICTURE_PX = 1600


def enabled() -> bool:
    import os
    from . import director
    return director.enabled() and os.environ.get("REEL_DESIGNER", "1").strip().lower() not in {"0", "false", "off", "no"}


def _picture(source: Path, work: Path) -> tuple[str, int, int]:
    """The product picture as the designer may reference it: ./assets/ui-<16 hex>.png, fitted inside PICTURE_PX."""
    name = "ui-" + hashlib.sha256(str(source).encode()).hexdigest()[:16] + ".png"
    target = work / "assets" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vf",
                        f"scale='min({PICTURE_PX},iw)':'min({PICTURE_PX},ih)':force_original_aspect_ratio=decrease", "-frames:v", "1", str(target)],
                       check=True, capture_output=True, timeout=60)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(target)],
                           capture_output=True, text=True, timeout=30).stdout.strip().split(",")
    return f"./assets/{name}", int(probe[0]), int(probe[1])


def _subjects(job_dir: Path) -> dict[str, str]:
    """Picture file name -> what it shows (from the asset catalog the director used)."""
    try:
        catalog = json.loads((job_dir / "generated" / "asset_catalog.json").read_text())
        mapping = json.loads((job_dir / "generated" / "asset_map.json").read_text())
    except (OSError, ValueError):
        return {}
    by_index = {str(row.get("index")): str(row.get("subject") or "") for row in catalog if isinstance(row, dict)}
    return {Path(rel).name: by_index.get(index, "") for index, rel in mapping.items()}


def build_plan(config: dict, storyboard: dict, creative: dict, design, work: Path, job_dir: Path):
    """The MotionPlan the designers receive, made from the approved storyboard: words, timing and pictures are fixed; the design is theirs."""
    scenes_in, boards = config["scenes"], storyboard.get("scenes", [])
    subjects = _subjects(job_dir)
    pictures: dict[str, tuple[str, int, int]] = {}
    plans, cursor = [], 0.0
    for i, row in enumerate(scenes_in):
        board = boards[i] if i < len(boards) else {}
        source = Path(row["asset"])
        if source.name not in pictures:
            pictures[source.name] = _picture(source, work)
        src = pictures[source.name][0]
        length = row["frames"] / 30
        items = ", ".join(row.get("items") or [])
        idea = (f"{board.get('description') or row.get('role') or ''}. Camera/motion: {board.get('motion_style') or ''}. "
                f"This scene shows the product picture <img src=\"{src}\"> ({subjects.get(source.name) or 'a product picture'}); design how it appears, "
                f"moves and is framed (crop to the relevant part, callouts for: {items or 'the key point'}). Why this visual: {board.get('why_visual') or ''}.").strip()
        plans.append(mg.ScenePlan(headline=str(row.get("title") or board.get("text_overlay") or "")[:120] or "—", idea=idea[:900],
                                  start=round(cursor, 3), end=round(cursor + length, 3), narration=str(row.get("narration_text") or "")))
        cursor += length
    chosen = creative.get("chosen") or {}
    direction = "; ".join(x for x in (chosen.get("visual_language"), f"mood: {design.mood}", f"motion personality: {design.personality}", f"shape language: {design.shape}",
                                      f"pacing: {chosen.get('pacing')}" if chosen.get("pacing") else "") if x)[:2400]
    def six(color: str) -> str:
        color = str(color)
        return "#" + "".join(c * 2 for c in color[1:]) if len(color) == 4 else color
    design = design.model_copy(update={k: six(getattr(design, k)) for k in ("bg", "surface", "ink", "accent", "accent2")})
    palette = mg.Palette(bg=design.bg, surface=design.surface, ink=design.ink, accent=design.accent, accent2=design.accent2)
    plan = mg.MotionPlan(title=str(chosen.get("name") or storyboard.get("prompt", "")[:40] or "ویدیو")[:60], summary=str(chosen.get("angle") or "")[:300],
                         format="vertical", duration=round(cursor, 3), palette=palette, signature=str(chosen.get("name") or ""), design_direction=direction, scenes=plans)
    return plan, pictures, subjects


def _duration(path) -> float | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except Exception:
        return None


def scene_lengths(config: dict, target: float) -> list[float]:
    """Each scene lasts as long as its narration plus a breath (the voice is measured, not estimated), so a scene never sits silent for seconds or cuts the voice;
    when the whole film would fall well short of the planned length, the breaths grow a little."""
    rows = config["scenes"]
    spoken = [(_duration(row["narration"]) if row.get("narration") else None) for row in rows]
    lengths = [max(2.2, (d + 0.55) if d else row["frames"] / 30) for d, row in zip(spoken, rows)]
    total = sum(lengths)
    if target and total < target * 0.9 and rows:
        extra = min(1.2, (target * 0.9 - total) / len(rows))
        lengths = [round(x + extra, 3) for x in lengths]
    return [round(x, 3) for x in lengths]


def _clean(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("|", "/")).strip()


def handoff_brief(config: dict, storyboard: dict, creative: dict, pictures: dict, subjects: dict, lengths: list[float]) -> str:
    """The approved storyboard in the studio's own hand-over format, so the planner (which knows the whole component library) receives the scenes as final."""
    chosen = creative.get("chosen") or {}
    head = [f"ایده: {_clean(chosen.get('name'))} — {_clean(chosen.get('angle'))}", f"هوک (دو ثانیه‌ی اول): {_clean(chosen.get('hook'))}",
            f"سبک بصری: {_clean(chosen.get('visual_language'))}", f"حس و حال: {_clean(chosen.get('pacing') or chosen.get('feeling'))}"]
    boards = storyboard.get("scenes", [])
    lines = []
    for i, row in enumerate(config["scenes"]):
        board = boards[i] if i < len(boards) else {}
        src = pictures[Path(row["asset"]).name][0]
        what = subjects.get(Path(row["asset"]).name) or "a product picture"
        see = _clean(f"{board.get('description') or row.get('role') or ''}. Motion: {board.get('motion_style') or ''}. Picture to use: <img src=\"{src}\"> ({what}). "
                     f"Call-outs: {', '.join(row.get('items') or []) or 'none'}. Why: {board.get('why_visual') or ''}. "
                     "The picture is always shown whole in its frame: any crop mentioned above is done by a camera move (zoom and drift toward the part), never by cutting the picture.")
        lines.append(f"{i + 1}. ({lengths[i]:.1f}s) تصویر: {see} | متن روی صفحه: {_clean(row.get('title') or board.get('text_overlay'))} | روایت: {_clean(row.get('narration_text'))}")
    return "\n".join([*head, "", *lines])


def library_plan(config, storyboard, creative, pictures, subjects, lengths, context, cache: Path, used: list[str]):
    """The planner designs the film from the approved script: palette, signature device, design bible, entrances and the ready-made components (Shotcraft recipes,
    executable library components) where they fit; then the library scout looks at pictures of the components next to the scenes. Cached beside the job."""
    brief = handoff_brief(config, storyboard, creative, pictures, subjects, lengths)
    chosen_look = read_design_choice(cache.parent if cache.name == "scenes" else cache)
    if chosen_look:
        brief = re.sub(r"^سبک بصری:.*$", "سبک بصری: " + _clean(chosen_look["direction"]), brief, count=1, flags=re.M)
    from .design_styles import reference_text
    style = reference_text(creative.get("reference"))
    key = hashlib.sha256((brief + context + style).encode()).hexdigest()[:20]
    path = cache / "plan.json"
    try:
        saved = json.loads(path.read_text())
        if saved.get("fp") == key:
            return mg.MotionPlan.model_validate(saved["plan"]), brief
    except (OSError, ValueError):
        pass
    plan = mg.plan(brief, context=context, style=style, used=used)
    if chosen_look:                                   # the look the person (or the studio, sure of itself) settled is the look: palette and design bible are fixed, the designers build on them
        plan = plan.model_copy(update={"palette": mg.Palette(**chosen_look["palette"]), "design_direction": chosen_look["direction"][:2400]})
    if plan.asks() or len(plan.scenes) != len(config["scenes"]):
        raise CreativeUnavailable("the planner did not keep the approved scenes")
    try:
        from . import library_scout
        plan, report = library_scout.scout(plan, brief, used=used)
        log.info("reel library scout: %s", [(p.get("scene"), p.get("resource_id"), p.get("used")) for p in report.get("picks", [])])
    except Exception as exc:
        log.warning("reel library scout failed: %s", str(exc)[:160])
    path.write_text(json.dumps({"fp": key, "plan": plan.model_dump()}, ensure_ascii=False))
    return plan, brief


def read_design_choice(work: Path) -> dict | None:
    """The look chosen before the scenes were designed (see the studio's design question): {name, direction, palette, text} or None."""
    try:
        data = json.loads((work.parent / "design_choice.json").read_text()) if work.name == "reel_design" else json.loads((work / "design_choice.json").read_text())
        return data if data.get("direction") and data.get("palette") else None
    except (OSError, ValueError):
        return None


def retime(plan, lengths: list[float]):
    cursor, scenes = 0.0, []
    for scene, length in zip(plan.scenes, lengths):
        scenes.append(scene.model_copy(update={"start": round(cursor, 3), "end": round(cursor + length, 3)}))
        cursor += length
    return plan.model_copy(update={"scenes": scenes, "duration": round(cursor, 3)})


def _context(facts: dict, pictures: dict, subjects: dict) -> str:
    lines = ["PRODUCT FACTS (verified; the only facts you may state): " + json.dumps(facts, ensure_ascii=False)[:2800],
             "ATTACHED PICTURES the person already gave (never ask them to upload one). You cannot see them; use the exact src and this description:"]
    for name, (src, width, height) in pictures.items():
        lines.append(f'- <img src="{src}"> ({width}x{height} px, aspect {width / height:.2f}): {subjects.get(name) or "a product picture"}')
    lines.append("SUBTITLES: after rendering the studio lays the narration's word-by-word subtitles (Tscaps) over the lower part of the frame, y = 1330 to 1580. Keep every "
                 "headline, picture and label of your scene out of that band (a background or glow may continue behind it); never draw your own subtitles.")
    lines.append(QUALITY_BAR)
    lines.append("USE OF PICTURES: the product is the hero. Show it large with width and height in px, object-fit: contain (or cover inside an overflow:hidden box), "
                 "never stretched; frame it with shapes drawn in the film's palette, give it depth (layers, shadow, parallax), crop to the part the scene talks about, "
                 "and never leave the same layout twice.")
    return "\n".join(lines)


_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def path_problem(d: str) -> str | None:
    """Why an SVG path's `d` would not parse in the browser (a missing or extra number, a stray character), or None. A bad path stops the whole page."""
    import re
    text = d.strip()
    if not text or text[0] not in "Mm":
        return "path must start with M"
    for command, body in re.findall(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)", text):
        leftover = re.sub(_NUM, " ", body)
        if command in "Aa":                                   # arc flags may be written together (0 1 → 01): not worth accepting, ask for spaces
            pass
        if re.sub(r"[\s,]", "", leftover):
            return f"path has an invalid number near «{body.strip()[:24]}»"
        count = len(re.findall(_NUM, body))
        need = _ARGS[command.upper()]
        if need == 0:
            if count:
                return "path has numbers after Z"
        elif count == 0 or count % need:
            return f"path command {command} needs groups of {need} numbers (got {count})"
    return None


def svg_problems(html: str) -> list[str]:
    import re
    found = []
    for d in re.findall(r'\bd\s*=\s*"([^"]*)"', html):
        problem = path_problem(d)
        if problem:
            found.append(f"inline SVG: {problem}. Every path d must be valid SVG (each command followed by the right number of numbers, numbers separated by spaces or commas).")
    return found[:3]


def sound_effects(work: Path, plan) -> list[dict]:
    """Synthesised sound design for the motion (the studio has no sound-effect library): a soft whoosh into every scene after the first and a low hit on the closing scene.
    Quiet by construction, so the voice stays clear."""
    work.mkdir(parents=True, exist_ok=True)
    whoosh, hit = work / "whoosh.wav", work / "hit.wav"
    try:
        if not whoosh.is_file():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=0.7:c=pink:r=48000:a=0.9", "-af",
                            "highpass=f=250,lowpass=f=5200,afade=t=in:d=0.3,afade=t=out:st=0.28:d=0.42,volume=0.30", str(whoosh)], check=True, capture_output=True, timeout=60)
        if not hit.is_file():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=62:d=0.6:r=48000", "-af", "afade=t=in:d=0.01,afade=t=out:st=0.05:d=0.55,volume=0.55", str(hit)],
                           check=True, capture_output=True, timeout=60)
    except Exception as exc:
        log.warning("reel sound effects were not made: %s", str(exc)[:200])
        return []
    clips = [{"path": str(whoosh), "start": round(max(0.0, scene.start - 0.35), 3), "duration": 0.7} for scene in plan.scenes[1:]]
    if len(plan.scenes) > 1:
        clips.append({"path": str(hit), "start": round(plan.scenes[-1].start + 0.05, 3), "duration": 0.6})
    return clips


def add_subtitles(video: Path, plan, config: dict, work: Path, take: dict | None = None) -> bool:
    """Word-by-word subtitles of the narration, drawn by Tscaps (the engine of the studio's talking styles) as a transparent layer and composited onto the finished
    reel. Best effort: the reel stays as it was when the layer cannot be made."""
    try:
        from engine import tscaps_overlay as tso
        cues = []
        if take:                                                   # the voice's own word times, not an even spread
            for line in take["lines"]:
                words = [tso.Word(w["word"], round(narration_take.PREROLL + w["start"], 3), round(narration_take.PREROLL + w["end"], 3), None) for w in line["words"]]
                if words:
                    cues.append(tso.Cue("caption", words[0].s, words[-1].e + 0.15, words))
        else:
            for scene, row in zip(plan.scenes, config["scenes"]):
                text = str(row.get("narration_text") or scene.narration or "").strip()
                words = tso.words_for(text, scene.start + 0.12, scene.end - 0.2) if text else []
                if words:
                    cues.append(tso.Cue("caption", words[0].s, words[-1].e + 0.15, words))
        if not cues or not tso.enabled():
            return False
        work.mkdir(parents=True, exist_ok=True)
        overlay = tso.render_overlay(tso._tidy(cues), work / "subtitles.webm", width=1080, height=1920, fps=30, duration=plan.duration + 0.1, work_dir=work, timeout=300)
        target = work / "with_subtitles.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(overlay), "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto[v]", "-map", "[v]", "-map", "0:a?",
                        "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", str(target)], check=True, capture_output=True, timeout=900)
        if target.is_file() and target.stat().st_size > 10_000:
            target.replace(video)
            return True
    except Exception as exc:
        log.warning("reel subtitles were not added: %s", str(exc)[:240])
    return False


def richness_problems(draft) -> list[str]:
    """A scene too plain to be worth rendering: few moving parts, no layers, the product picture missing or never moved."""
    moves = len(re.findall(r"\b(?:tl|HM)\s*\.", draft.build_js)) + len(re.findall(r"\bHM\.", draft.update_js))
    tags = len(re.findall(r"<(?:div|p|span|svg|path|rect|circle|line|g|img|polygon|ellipse)\b", draft.html))
    problems = []
    if moves < 9:
        problems.append(f"only {moves} animation calls: write at least 9 (entrance of every layer, a camera move on the picture, callouts one after another, a breathing ambient motion)")
    if tags < 8:
        problems.append(f"only {tags} elements: build at least three layers (a background treatment, the product picture with its frame, the headline and foreground details such as rules, labels and marks)")
    if "<img" not in draft.html:
        problems.append("the product picture is missing: this scene must show it (its exact src from the facts)")
    elif not re.search(r"scale|clipPath|\bx\s*:|\by\s*:", draft.build_js):
        problems.append("the product picture never moves: give it a camera move (scale and x/y over the whole scene)")
    return problems


QUALITY_BAR = ("QUALITY BAR (a scene below it is rejected and sent back): at least three layers; at least nine animation calls; the product picture is shown WHOLE in its frame "
               "(object-fit: contain; never guess a crop of a picture you cannot see) and gets a camera move (slow scale and drift) for the whole scene; callouts or labels appear one "
               "after another; something keeps breathing until the end; a different composition and entrance from the neighbouring scenes.")


def _scene_request(scene) -> str:
    return (f"عنوان: {scene.headline}\nنریشن: {scene.narration}\nمدت: {scene.end - scene.start:.1f} ثانیه\nایدهٔ تصویری و حرکتی:\n{scene.idea}"
            + (f"\nکامپوننت آمادهٔ کتابخانه: {scene.shotcraft_id}" if scene.shotcraft_id else ""))


def _author(plan, n: int, brief: str, context: str, cache: Path, used: list[str], job_dir: Path | None = None):
    scene = plan.scenes[n - 1]
    stage = f"designing scene {n}"
    say = (lambda text, **kw: _progress(job_dir, text, stage=stage, **kw)) if job_dir else (lambda text, **kw: None)
    key = hashlib.sha256(json.dumps([scene.headline, scene.idea, scene.narration, round(scene.end - scene.start, 2), plan.design_direction, plan.palette.model_dump()],
                                    ensure_ascii=False).encode()).hexdigest()[:20]
    path = cache / f"s{n}.json"
    request = _scene_request(scene)
    try:
        saved = json.loads(path.read_text())
        if saved.get("fp") == key:
            draft = mg.SceneDraft.model_validate(saved["draft"])
            say(f"صحنهٔ {n} («{scene.headline}»): از قبل طراحی و تأیید شده بود", request=request, detail=f"وضعیت: تأییدشده (استفاده از طراحی ذخیره‌شده)\n\n{draft.html[:1200]}", done=True)
            return draft, "reused"
    except (OSError, ValueError):
        pass
    say(f"صحنهٔ {n} («{scene.headline}»): طراحی شروع شد", request=request, detail="وضعیت: در حال طراحی")
    try:
        draft = mg.author_scene(plan, n, brief, context=context, used=used)
        problems = svg_problems(draft.html)
        said = ""
        if not problems:
            problems = richness_problems(draft)
            said = "طراحی ساده بود"
        if problems:                                         # one correction with the exact reasons; a scene that is still wrong is replaced, never rendered broken
            say(f"صحنهٔ {n}: بازبینی — {said or 'مشکل در طراحی'}؛ دوباره طراحی می‌شود", detail="وضعیت: بازبینی\n" + "\n".join(problems))
            draft = mg.author_scene(plan, n, brief, context=context, used=used, feedback=problems)
            if svg_problems(draft.html):
                raise CreativeUnavailable("the scene's SVG paths are still invalid")
        path.write_text(json.dumps({"fp": key, "draft": draft.model_dump()}, ensure_ascii=False))
        left = richness_problems(draft)
        say(f"صحنهٔ {n} («{scene.headline}»): طراحی تأیید شد", request=request,
            detail=f"وضعیت: تأییدشده{' (با نکتهٔ باقی‌مانده: ' + '؛ '.join(left) + ')' if left else ''}\n\nHTML:\n{draft.html[:1500]}\n\nانیمیشن:\n{draft.build_js[:1200]}", done=True)
        return draft, "designed"
    except Exception as exc:
        if scene.native_component or scene.shotcraft_component:
            # a ready-made component that does not fit this length or text: the scene is designed by hand instead
            plan.scenes[n - 1] = scene.model_copy(update={"native_component": None, "shotcraft_component": None})
            try:
                draft = mg.author_scene(plan, n, brief, context=context, used=used)
                if not svg_problems(draft.html):
                    path.write_text(json.dumps({"fp": key, "draft": draft.model_dump()}, ensure_ascii=False))
                    say(f"صحنهٔ {n}: کامپوننت آماده جا نیفتاد؛ با طراحی دستی تأیید شد", request=request, detail=f"وضعیت: تأییدشده\n\n{draft.html[:1200]}", done=True)
                    return draft, "designed"
            except Exception:
                pass
        log.warning("reel scene %d could not be designed (%s); a plain scene is used", n, str(exc)[:200])
        say(f"صحنهٔ {n} («{scene.headline}»): طراحی اختصاصی تأیید نشد؛ با صحنهٔ ساده جایگزین شد", request=request, detail=f"وضعیت: ردشده\nعلت: {str(exc)[:600]}", done=True)
        return mg.fallback_scene(plan, n), "plain"


def read_timeline(job_dir: Path) -> dict | None:
    """The timeline the designed reel was built on: {duration, scenes:[{start, end}]} (None when this job has no designed reel)."""
    try:
        data = json.loads((job_dir / "reel_design" / "timeline.json").read_text())
        return data if data.get("duration") and data.get("scenes") else None
    except (OSError, ValueError):
        return None


_NOTES = threading.Lock()


def _progress(job_dir: Path, note: str, *, stage: str = "designing motion scenes", detail: str = "", request: str = "", done: bool = False) -> None:
    """Notes the chat shows as this stage's log (the status sync of the web process reads them; this runs in the render worker). Each scene is its own stage
    (`designing scene N`), so it is its own row with its status, request and response; `done` closes the row."""
    path = job_dir / "reel_design" / "progress.json"
    with _NOTES:
        try:
            data = json.loads(path.read_text()) if path.is_file() else {"notes": []}
        except (OSError, ValueError):
            data = {"notes": []}
        data["stage"] = stage
        data["notes"].append({"text": note, "detail": detail[:3000], "request": request[:3000], "stage": stage, "done": done})
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False))
        except OSError:
            pass


def _stage(job, message: str) -> None:
    """The job's own stage name (the chat turns it into a step of the timeline; only 'rendering' is a render card)."""
    try:
        from app.jobs import _write_status
        job.render.message = message
        _write_status(job)
    except Exception:
        pass


def _skipped(job, reason: str) -> bool:
    """The caller falls back to the built-in page; the reason is kept so the review can tell the person the designer was not used."""
    try:
        job.designer_note = "اجرا نشد و قالب پایه استفاده شد — " + reason
    except Exception:
        pass
    try:                                           # the failure is a visible line of the log, not only a note kept in the review
        _progress(job.dir, "طراحی موشن ناموفق بود؛ قالب پایه استفاده می‌شود", detail=reason, done=True)
    except Exception:
        pass
    return False


def render(job, data: dict, config: dict, out_path: Path, *, on_progress=None, should_cancel=None, timeout: int = 5400) -> bool:
    """Design, check and render the reel. True when out_path was written; False (nothing raised) when the caller should use the built-in page."""
    from engine.hyperframes import product_reel, standalone
    meta = data.get("generation_meta") or {}
    creative = meta.get("creative_plan")
    if not enabled() or not creative or not config.get("scenes"):
        return _skipped(job, "برنامهٔ خلاقانه یا طراح موشن در دسترس نبود")
    work = job.dir / "reel_design"
    cache = work / "scenes"
    try:
        from . import motion as motion_designer
        shutil.rmtree(work / "project", ignore_errors=True)
        project = work / "project"
        cache.mkdir(parents=True, exist_ok=True)
        project.mkdir(parents=True, exist_ok=True)
        storyboard = json.loads((job.dir / "storyboard.json").read_text())
        used: list[str] = []
        (work / "progress.json").unlink(missing_ok=True)
        _progress(job.dir, "دارم صحنه‌های تأییدشده را به طراح موشن می‌دهم: متن‌ها، زمان‌بندی، نریشن و تصویرهای محصول ثابت‌اند؛ طراحی ظاهر و حرکت با طراح است")
        texts = [str(row.get("narration_text") or "").strip() for row in config["scenes"]]
        take = fitted = None
        if texts and all(texts):
            # One continuous reading of the whole script; the scenes are fitted to its real word times (never a clip per scene joined with pauses).
            _progress(job.dir, "دارم نریشن را یک‌جا و پیوسته می‌سازم تا صحنه‌ها با زمان واقعی کلمات تنظیم شوند", detail="وضعیت: در حال ساخت")
            take = narration_take.voice(storyboard, texts, work / "voice", getattr(job, "user_id", None))
            fitted = narration_take.fit(take)
            lengths = [round(end - begin, 3) for begin, end in zip(fitted["starts"], fitted["ends"])]
            _progress(job.dir, f"نریشن آماده شد: یک اجرای پیوسته، {take['total']:.0f} ثانیه صدا، ویدیو {fitted['duration']:.0f} ثانیه", done=True,
                      detail="\n".join(f"{n}. [{begin:.1f}–{end:.1f}s] {text}" for n, (begin, end, text) in enumerate(zip(fitted["starts"], fitted["ends"], texts), 1)))
        else:
            if texts and any(texts):
                _progress(job.dir, "بعضی صحنه‌ها نریشن ندارند؛ برای این فیلم نریشن هر صحنه جدا زمان‌بندی می‌شود", done=True)
            lengths = scene_lengths(config, float(storyboard.get("total_duration_s") or 0))
        subjects = _subjects(job.dir)
        pictures = {}
        for row in config["scenes"]:
            name = Path(row["asset"]).name
            if name not in pictures:
                pictures[name] = _picture(Path(row["asset"]), project)
        facts = {k: v for k, v in (creative.get("facts") or {}).items()} if isinstance(creative.get("facts"), dict) else (creative.get("brief") or {})
        context = _context(facts, pictures, subjects)
        try:
            plan, brief = library_plan(config, storyboard, creative, pictures, subjects, lengths, context, work, used)
        except Exception as exc:
            # The planner could not take the approved scenes: the designer's own identity step plans them instead (still designed per scene, without library picks).
            log.warning("reel planner unavailable (%s); the scenes are planned from the creative direction", str(exc)[:200])
            public = motion_designer.plan_from_public(creative)
            design_file = work / "design.json"
            try:
                design = motion_designer.DesignSystem(**json.loads(design_file.read_text()))
            except (OSError, ValueError, TypeError):
                bf = public.brief
                design = motion_designer.design_system(f"topic: {bf.topic}; message: {bf.core_message}; audience: {bf.audience}; tone: {bf.tone}",
                                                       f"{public.chosen.name}: {public.chosen.angle}. Visual language: {public.chosen.visual_language}. Pacing: {public.chosen.pacing}", used)
                design_file.write_text(json.dumps(design.model_dump(), ensure_ascii=False))
            plan, _, _ = build_plan(config, storyboard, creative, design, project, job.dir)
            brief = str(storyboard.get("prompt") or "")[:1500]
        plan = retime(plan, lengths)
        if fitted:
            plan = narration_take.apply(plan, fitted)             # every scene knows when each of its words is spoken
        (work / "timeline.json").write_text(json.dumps({"duration": plan.duration, "scenes": [{"start": sc.start, "end": sc.end} for sc in plan.scenes]}))
        picks = [f"صحنهٔ {n}: {(sc.shotcraft_id or (sc.native_component.resource_id if sc.native_component else '') or '').split(':')[-1]}" for n, sc in enumerate(plan.scenes, 1)
                 if sc.shotcraft_id or sc.native_component or sc.shotcraft_component]
        _progress(job.dir, f"طرح کلی طراحی آماده شد: {len(plan.scenes)} صحنه، {plan.duration:g} ثانیه" + (f"، از کتابخانه: {'، '.join(picks[:4])}" if picks else "، همهٔ صحنه‌ها اختصاصی طراحی می‌شوند"),
                  detail=f"امضای بصری: {plan.signature}\n{plan.design_direction}\n\n" + "\n".join(f"صحنهٔ {n} · {sc.headline}\n{sc.idea}" for n, sc in enumerate(plan.scenes, 1)))
        if on_progress:
            on_progress(2)
        count = len(plan.scenes)
        contexts = [contextvars.copy_context() for _ in range(count)]
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            results = list(pool.map(lambda n: contexts[n - 1].run(_author, plan, n, brief, context, cache, used, job.dir), range(1, count + 1)))
        drafts = [draft for draft, _ in results]
        how = [kind for _, kind in results]
        log.info("reel designer: %s", how)
        if how.count("plain") * 2 > count:
            log.warning("reel designer: most scenes fell back to plain scenes; the built-in reel page is used instead")
            return _skipped(job, "طراحی بیشتر صحنه‌ها پس از چند بار تلاش از اعتبارسنجی رد شد")
        if on_progress:
            on_progress(8)
        total = plan.duration
        audio = []
        if fitted:
            audio = list(fitted["audio"])                         # the one unbroken take
        else:
            for scene, row in zip(plan.scenes, config["scenes"]):
                if row.get("narration"):
                    audio.append({"path": str(Path(row["narration"])), "start": scene.start, "duration": round(scene.end - scene.start, 3)})
        sfx = sound_effects(work / "sfx", plan)
        music = (data.get("music") or {}).get("file")
        if music:
            try:
                from .music_bed import make_bed
                bed = make_bed(Path(music), work / "bed.m4a", total, audio)
                audio.append({"path": str(bed), "start": 0, "duration": round(total, 3), "role": "music"})
            except Exception as exc:
                log.warning("reel music bed failed (%s); the reel is made without music", str(exc)[:200])
        page = mg.assemble_scenes(plan, drafts, audio + sfx)
        problems = [p for p in mg.validate_page(page, min_scenes=1) if not p.startswith("use 2-6 scenes")]      # a storyboard may have up to ten scenes
        if problems:
            log.warning("reel page invalid: %s", problems[:3])
            return _skipped(job, "صفحهٔ طراحی‌شده معتبر نبود: " + mg.explain_problem(problems[0]))
        mg.write_project(project, page)
        _progress(job.dir, "دارم صفحهٔ طراحی‌شده را در مرورگر بررسی می‌کنم: چیدمان، خوانایی متن و خطاهای اجرا")
        gate = {"overlap": True, "stills": 0}

        def gated(page_now):
            result = standalone.check(project, should_cancel=should_cancel)
            if result.ran and not result.blocking and gate["stills"] < 2:
                gate["stills"] += 1
                _progress(job.dir, "دارم از هر صحنه عکس بررسی می‌گیرم: خالی‌بودن یا روی‌هم‌افتادن متن‌ها", detail="وضعیت: در حال بررسی")
                found = visual_gate.problems(project, page_now_plan, work, list(getattr(result, "quality", []) or []), gate["overlap"])
                gate["overlap"] = False                               # overlaps are sent back once; blank scenes are checked after every repair
                if found:
                    result.blocking = list(found)
                else:
                    _progress(job.dir, "عکس‌های بررسی همهٔ صحنه‌ها سالم بودند", done=True)
            return result

        page_now_plan = plan
        check = gated(page)
        rounds = 0
        while check.blocking and rounds < 3:
            # A scene that breaks the page is repaired once from the browser's own message, then replaced by a plain scene: one bad scene never costs the whole design.
            rounds += 1
            hit = sorted({int(m) for text in check.blocking for m in re.findall(r"#?\bs(\d{1,2})-", text) if 1 <= int(m) <= count})
            if not hit:
                hit = sorted({int(m) for text in check.blocking for m in re.findall(r"\bs(\d{1,2})\b", text) if 1 <= int(m) <= count})
            if not hit:
                hit = [n for n, kind in enumerate(how, 1) if kind != "plain"][:1]      # the page names no scene: the first designed scene is swapped out and the page is checked again
            log.warning("reel check round %d blocked on scenes %s: %s", rounds, hit, check.blocking[:2])
            _progress(job.dir, f"بررسی مرورگر مشکل پیدا کرد (صحنهٔ {'، '.join(map(str, hit))}): " + mg.explain_problem(check.blocking[0]) + (" — دوباره طراحی می‌شود" if rounds == 1 else " — با صحنهٔ ساده جایگزین می‌شود"), detail="\n".join(check.blocking[:4]))
            for n in hit:
                reason = [t for t in check.blocking if re.search(rf"\bs{n}\b|\bs{n}-", t)] or check.blocking
                try:
                    if rounds == 1:
                        draft = mg.author_scene(plan, n, brief, context=context, used=used, feedback=[mg.explain_problem(t) + " — " + t[:300] for t in reason[:3]])
                        if svg_problems(draft.html):
                            raise CreativeUnavailable("invalid svg")
                    else:
                        raise CreativeUnavailable("replaced after a second failure")
                except Exception:
                    draft = mg.fallback_scene(plan, n)
                    how[n - 1] = "plain"
                drafts[n - 1] = draft
            if how.count("plain") * 2 > count:
                return _skipped(job, "بررسی مرورگر چند بار صحنه‌ها را رد کرد: " + mg.explain_problem(check.blocking[0]))
            page = mg.assemble_scenes(plan, drafts, audio + sfx)
            mg.write_project(project, page)
            check = gated(page)
        if check.blocking:
            log.warning("reel page failed the browser check: %s", check.blocking[:2])
            return _skipped(job, "بررسی مرورگر صفحهٔ طراحی‌شده را رد کرد: " + mg.explain_problem(check.blocking[0]))
        if "plain" in how:
            job.designer_note = f"{how.count('plain')} صحنه پس از ردشدن در بررسی با صحنهٔ ساده جایگزین شد"
        _progress(job.dir, "طراحی تمام شد و بررسی مرورگر پاک بود؛ رندر ویدیو شروع می‌شود")
        if on_progress:
            on_progress(12)
        _stage(job, "rendering")
        product_reel._run_cli(project, out_path, timeout=timeout,
                              on_progress=(lambda pct: on_progress(12 + int(pct * 0.83))) if on_progress else None, should_cancel=should_cancel)
        if not out_path.is_file():
            return False
        _stage(job, "adding subtitles")
        _progress(job.dir, "رندر تمام شد؛ دارم زیرنویس کلمه‌به‌کلمهٔ نریشن را اضافه می‌کنم", stage="adding subtitles")
        if not take and not add_subtitles(out_path, plan, config, work / "overlay", take):         # with a voice take the captions are already typography inside every scene
            job.designer_note = ((getattr(job, "designer_note", "") or "") + " زیرنویس کلمه‌به‌کلمه اضافه نشد.").strip()
        return True
    except narration_take.NarrationFailed:
        raise
    except CreativeUnavailable as exc:
        log.warning("reel designer unavailable: %s", exc)
        return _skipped(job, "طراح موشن در دسترس نبود: " + str(exc)[:160])
    except Exception as exc:
        from app.render_cloud.service import CloudRenderError
        if isinstance(exc, CloudRenderError):
            raise
        log.warning("reel designer failed (%s); the built-in reel page is used", str(exc)[:300])
        return _skipped(job, "طراحی موشن با خطا متوقف شد: " + str(exc)[:160])
    finally:
        shutil.rmtree(work / "project", ignore_errors=True)
