"""Caption, hook and key-moment overlays rendered with the MIT `@tscaps/engine` (tools/tscaps).

The engine lays out Persian text (bidi, word timing, animated templates) in headless Chrome and writes a transparent
WebM containing only the text. The talking renderers composite that layer with ffmpeg, so the video is encoded once
and every template can place text exactly where its style wants it.

Everything here is optional: `available()` is false without node, Chrome or the installed engine, and callers keep
their ASS captions when `render_overlay` raises `OverlayUnavailable`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)
TOOL = Path(__file__).resolve().parent.parent / "tools" / "tscaps"

# Role -> look. Fonts are our own Ray weights (Persian-capable); templates come from tools/tscaps/templates (MIT).
ROLES: dict[str, dict] = {
    # calm multi-word subtitles, a warm accent on the key phrase
    "caption": {"template": "loki", "font": "RayBold", "maxChars": 17, "maxLines": 2,
                "alignment": {"verticalAlign": "center", "verticalOffset": 0.76},
                "vars": {"--tscaps-font-size": "4.8cqh", "--tscaps-primary-color": "#ffffff", "--tscaps-tag-color": "#ffd23f"}},
    # the opening line: large, premium gold
    "hook": {"template": "noor", "font": "RayBlack", "maxChars": 14, "maxLines": 3,
             "alignment": {"verticalAlign": "center", "verticalOffset": 0.62},
             "vars": {"--tscaps-font-size": "6.0cqh", "--tscaps-primary-color": "#ffd23f"}},
    # a key moment: very large white statement
    "moment": {"template": "elio", "font": "RayBlack", "maxChars": 12, "maxLines": 3,
               "alignment": {"verticalAlign": "center", "verticalOffset": 0.5},
               "vars": {"--tscaps-font-size": "7.2cqh", "--tscaps-primary-color": "#ffffff", "--tscaps-tag-color": "#ffd23f"}},
}
FONTS = [{"family": "RayBold", "url": "/fonts/RAY-BOLD.TTF", "weight": 700},
         {"family": "RayBlack", "url": "/fonts/RAY-BLACK.TTF", "weight": 900},
         {"family": "Vazir", "url": "/fonts/Vazirmatn-Regular.ttf", "weight": 400}]


class OverlayUnavailable(RuntimeError):
    """The overlay could not be produced; the caller falls back to its built-in text rendering."""


@dataclass
class Word:
    t: str
    s: float
    e: float
    tag: str | None = None


@dataclass
class Cue:
    kind: str          # caption | hook | moment
    start: float
    end: float
    words: list[Word] = field(default_factory=list)
    y: float | None = None   # vertical centre as a fraction of the frame height; None = the role's default
    scale: float | None = None   # size multiplier; None = the role's size
    color: str | None = None     # "#RRGGBB" text colour; None = the role's colour


def enabled() -> bool:
    return os.environ.get("TSCAPS_OVERLAY", "1").lower() not in {"0", "false", "no", "off"}


def available() -> bool:
    return enabled() and bool(shutil.which("node") and shutil.which("ffmpeg")) and (TOOL / "node_modules" / "@tscaps").is_dir()


def ensure_installed() -> bool:
    """One-time `npm ci` for the tool, best effort (a fresh checkout has no node_modules)."""
    if (TOOL / "node_modules" / "@tscaps").is_dir():
        return True
    npm = shutil.which("npm")
    if not npm:
        return False
    try:
        subprocess.run([npm, "install", "--no-audit", "--no-fund", "--silent"], cwd=TOOL, check=True, capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("tscaps tool install failed: %s", str(exc)[:200])
        return False
    return (TOOL / "node_modules" / "@tscaps").is_dir()


def words_for(text: str, start: float, end: float, *, emphasize: str = "", reveal: float | None = None) -> list[Word]:
    """Spread `text` over [start, end] by character weight. Words inside `emphasize` get the `emphasis` tag.

    `reveal` limits how long the words take to arrive (a hook builds in ~1.4 s and then holds)."""
    tokens = text.split()
    if not tokens or end <= start:
        return []
    window = min(end - start, reveal) if reveal else (end - start) * 0.9
    weights = [max(1, len(token)) for token in tokens]
    total = float(sum(weights))
    marked = {token for token in emphasize.split()} if emphasize else set()
    out, cursor = [], start
    for token, weight in zip(tokens, weights):
        span = window * weight / total
        out.append(Word(token, round(cursor, 3), round(cursor + span, 3), "emphasis" if token in marked else None))
        cursor += span
    return out


def _blank(path: Path, width: int, height: int, fps: int, duration: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d={duration:.3f}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35", "-pix_fmt", "yuv420p", str(path)],
                   check=True, capture_output=True, timeout=120)


def build_spec(cues: list[Cue], width: int, height: int, kinds: dict[str, dict] | None = None) -> dict:
    roles = {**ROLES, **(kinds or {})}
    out_kinds: dict[str, dict] = {}

    def kind_of(cue: Cue) -> str:
        if cue.kind not in roles:
            return cue.kind
        if cue.y is None and cue.scale is None and cue.color is None:
            out_kinds.setdefault(cue.kind, roles[cue.kind])
            return cue.kind
        role = roles[cue.kind]
        # The same look with another height, size or colour; a plain identifier (engine selectors).
        name = cue.kind + "".join([
            f"_y{int(round(cue.y * 100))}" if cue.y is not None else "",
            f"_s{int(round(cue.scale * 100))}" if cue.scale is not None else "",
            f"_c{cue.color.lstrip('#').lower()}" if cue.color else ""])
        variant = {**role, "alignment": {**role["alignment"], **({"verticalOffset": cue.y} if cue.y is not None else {})},
                   "vars": dict(role.get("vars") or {})}
        if cue.scale is not None and "--tscaps-font-size" in variant["vars"]:
            number, unit = re.match(r"([\d.]+)(\D+)", variant["vars"]["--tscaps-font-size"]).groups()
            variant["vars"]["--tscaps-font-size"] = f"{float(number) * cue.scale:.2f}{unit}"
        if cue.color:
            variant["vars"]["--tscaps-primary-color"] = cue.color
        out_kinds.setdefault(name, variant)
        return name

    names = [kind_of(c) for c in cues if c.words]
    return {"width": width, "height": height, "fonts": FONTS, "kinds": out_kinds,
            "cues": [{"kind": name, "start": round(c.start, 3), "end": round(c.end, 3),
                      "words": [{"t": w.t, "s": w.s, "e": w.e, "tag": w.tag} for w in c.words]}
                     for name, c in zip(names, [c for c in cues if c.words])]}


def render_overlay(cues: list[Cue], out: Path, *, width: int, height: int, fps: int, duration: float,
                   work_dir: Path, timeout: int = 900, kinds: dict[str, dict] | None = None, on_progress=None) -> Path:
    """Render `cues` to a transparent VP9 WebM of exactly `duration` seconds; raises OverlayUnavailable on any failure."""
    cues = [c for c in cues if c.words]
    if not cues:
        raise OverlayUnavailable("no cues to render")
    if not available() and not (enabled() and ensure_installed() and shutil.which("node") and shutil.which("ffmpeg")):
        raise OverlayUnavailable("node, ffmpeg or the tscaps engine is not installed")
    work_dir = Path(work_dir).resolve()
    out = Path(out).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    blank, spec_path = work_dir / "tscaps_blank.mp4", work_dir / "tscaps_spec.json"
    try:
        _blank(blank, width, height, fps, duration)
        spec_path.write_text(json.dumps(build_spec(cues, width, height, kinds), ensure_ascii=False))
        out.unlink(missing_ok=True)
        # The engine says "progress N" (percent of its rendering) as it works: read that as it arrives, so the page shows a real percentage for this stage.
        proc = subprocess.Popen(["node", "run.mjs", str(spec_path), str(blank), str(out)], cwd=TOOL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines: list[str] = []

        def pump() -> None:
            for line in proc.stderr:
                lines.append(line)
                found = re.search(r"progress\s+(\d+(?:\.\d+)?)", line)
                if found and on_progress:
                    try:
                        on_progress(min(100.0, float(found.group(1))))
                    except Exception:
                        pass
        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            stdout, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        reader.join(timeout=5)
        stderr = "".join(lines)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OverlayUnavailable(f"overlay render did not run: {str(exc)[:200]}") from exc
    if proc.returncode != 0 or not out.is_file() or out.stat().st_size < 1000:
        raise OverlayUnavailable((stderr or stdout or "overlay render failed")[-400:])
    return out


# --- cues from a talking plan ----------------------------------------------------------------------------------------

def without(plan, **fields):
    """A shallow copy of `plan` with some fields replaced (plans carry extra attributes a dataclass copy would lose)."""
    import copy
    clone = copy.copy(plan)
    for name, value in fields.items():
        setattr(clone, name, value)
    return clone


def without_hook(plan, **fields):
    """`plan` minus the hook, with captions still held back until the hook window ends (the ASS renderer reads
    that window from the hook itself, so removing it alone would let captions show underneath the Tscaps hook)."""
    end = float(plan.hook["end"]) if getattr(plan, "hook", None) else 0.0
    captions = [{**c, "start": max(float(c["start"]), end)} for c in plan.captions if float(c["end"]) > end]
    return without(plan, hook=None, captions=captions, **fields)


def _tidy(cues: list[Cue]) -> list[Cue]:
    """Sorted, never overlapping (the engine shows one section at a time)."""
    cues = sorted((c for c in cues if c.words and c.end > c.start), key=lambda c: c.start)
    for cue, nxt in zip(cues, cues[1:]):
        if cue.end > nxt.start:
            cue.end = nxt.start
    return [c for c in cues if c.end - c.start > 0.15]


def reel_cues(plan, *, captions: bool = True, hook: bool = True, moments: bool = True, moment_every: int = 5,
              hook_reveal: float = 1.4) -> list[Cue]:
    """Cues for a talking ReelPlan (engine/talking_styles/talking_2 shape).

    Captions and moments replace the ASS captions: every `moment_every`-th phrase is shown as a large key moment.
    The hook window suppresses captions underneath it, as the ASS renderer does."""
    cues: list[Cue] = []
    hook_end = 0.0
    if hook and getattr(plan, "hook", None) and plan.hook.get("text"):
        h = plan.hook
        hook_end = float(h["end"])
        cues.append(Cue("hook", float(h["start"]) + 0.1, hook_end, words_for(h["text"], float(h["start"]) + 0.1, hook_end, reveal=hook_reveal)))
    elif getattr(plan, "hook", None):
        hook_end = float(plan.hook.get("end", 0.0))
    if captions or moments:
        since_moment = 0
        for index, c in enumerate(plan.captions):
            if c["end"] <= hook_end:
                continue
            start = max(float(c["start"]), hook_end)
            end = float(c["end"])
            since_moment += 1
            # a key moment needs something worth enlarging: not a connective like «که»
            is_moment = (moments and moment_every and index > 0 and since_moment >= moment_every
                         and len((c.get("key") or "").strip()) >= 5)
            if is_moment:
                since_moment = 0
            look = c.get("look") or {}
            shown = {"y": look["y"] / 1920 if "y" in look else None, "scale": look.get("scale"), "color": look.get("color")}
            if is_moment:
                cues.append(Cue("moment", start, end, words_for(c["key"], start, end, reveal=min(1.0, (end - start) * 0.6)), **shown))
            elif captions:
                phrase = " ".join(part for part in (c.get("lead"), c.get("key")) if part)
                cues.append(Cue("caption", start, end, words_for(phrase, start, end, emphasize=c.get("key") or ""), **shown))
    return _tidy(cues)


def title_cues(titles: list[dict], *, y_for=None) -> list[Cue]:
    """Key moments given as {"start","end","text"}; the first word is lifted as the accent when there are several."""
    cues = []
    for title in titles or []:
        text = (title.get("text") or "").strip()
        start, end = float(title["start"]), float(title["end"])
        if not text or end <= start:
            continue
        first = text.split()[0] if len(text.split()) >= 2 else ""
        cues.append(Cue("moment", start, end, words_for(text, start, end, emphasize=first, reveal=min(1.0, (end - start) * 0.6)),
                        y=y_for(start) if y_for else None))
    return cues


def hook_cue(hook: dict | None, *, y_for=None, accent_first: bool = False, reveal: float = 1.4) -> list[Cue]:
    if not hook or not (hook.get("text") or "").strip():
        return []
    start, end = float(hook["start"]) + 0.1, float(hook["end"])
    first = hook["text"].split()[0] if accent_first and len(hook["text"].split()) >= 2 else ""
    return [Cue("hook", start, end, words_for(hook["text"], start, end, emphasize=first, reveal=reveal), y=y_for(start) if y_for else None)]


def note_cues(notes: list[dict]) -> list[Cue]:
    """Emphasis phrases (talking_1 notes): the last word is the accent, as in the ASS version."""
    cues = []
    for note in notes or []:
        text = (note.get("text") or "").replace("،", "").strip()
        start, end = float(note["start"]), float(note["end"])
        parts = text.split()
        if not parts or end <= start:
            continue
        cues.append(Cue("moment", start + 0.12, end, words_for(text, start + 0.12, end, emphasize=parts[-1] if len(parts) > 1 else "",
                                                               reveal=min(1.2, (end - start) * 0.55))))
    return cues


def render_with_overlay(render, video, plan, out, *, work_dir: Path, cues: list[Cue], strip, fps: int, duration: float,
                        width: int = 1080, height: int = 1920, overlay_progress=None, **kwargs):
    """Render with the Tscaps layer when it can be made; otherwise (or if compositing fails) with the style's own text.

    `render` is the style's plain renderer (it accepts `overlay=`), `strip(plan)` returns the plan without what the layer draws."""
    cues = _tidy(cues)
    if (kwargs.get('render_settings') or {}).get('caption_font') == 'Vazirmatn':
        # The native path honors the selected installed Persian font. Do not
        # place a Ray Tscaps layer over a user-selected Vazirmatn caption.
        return render(video, plan, out, work_dir=work_dir, **kwargs)
    overlay = None
    if cues and enabled():
        try:
            overlay = render_overlay(cues, work_dir / "tscaps_overlay.webm", width=width, height=height, fps=fps,
                                     duration=duration + 0.1, work_dir=work_dir, on_progress=overlay_progress)
        except OverlayUnavailable as exc:
            log.warning("tscaps overlay unavailable, using built-in text: %s", str(exc)[:240])
        except Exception as exc:  # the layer may improve a reel; it must never fail one
            log.warning("tscaps overlay failed, using built-in text: %s", str(exc)[:240])
    if overlay:
        try:
            return render(video, strip(plan), out, work_dir=work_dir, overlay=overlay, **kwargs)
        except Exception as exc:
            log.warning("render with the tscaps overlay failed (%s); rendering with built-in text", str(exc)[:240])
    return render(video, plan, out, work_dir=work_dir, **kwargs)
