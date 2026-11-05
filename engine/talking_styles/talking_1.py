"""Talking-head style "صحبتی ۱" (talking_1): a podcast clip cut into a styled vertical reel.

FROZEN: this is a saved style the user relies on. Do not change its look;
new looks go in a new module under ``engine/talking_styles`` (see
``tests/test_talking_reel.py::test_talking_1_is_frozen``).

Style (matches the reference reels the user works from):

* jump cuts on pauses and hesitation sounds, alternating wide and close
  framing on the speaker's face every few seconds (face found with the
  macOS Vision framework, see ``tools/face_track``)
* a soft warm grade; a few emotional sentences in black and white, entered
  and left with a warm light flash
* a pinned hook title (heavy Persian font, highlighted words in yellow) in
  a translucent dark rounded box, short phrase captions right above it, a
  name/title lower third; up to two emphasis moments (black and white,
  blurred, every overlay off, the key phrase punching in word by word)
* a low music bed ducked under the voice, loudness normalised

Rendering is one ffmpeg pass (trim/crop per shot, concat, ASS overlay,
audio mix); it needs an ffmpeg with libass (see ``render_ass``).
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..localize import _ass_colour, _ass_time, _rounded_rect, measure_text_boxes, probe_video
from ..render_ass import ass_burner_ffmpeg, subtitles_filter

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FACE_TRACK = PROJECT_ROOT / "tools" / "face_track"

W, H = 1080, 1920
RENDER_FPS = "30"          # delivery cadence; phone sources are commonly 60fps
GAP_CUT = 0.35            # pauses longer than this are cut out
CUT_PAD = 0.08            # speech kept around each cut
MIN_SHOT = 6.0            # framing changes at most this often (seconds of output)
MAX_SHOT = 10.0           # a longer stretch gets a punch-in at a word boundary
CLOSE_ZOOM = 1.25         # close framing, relative to the full-height wide crop
YELLOW = "#F5B800"
FLASH_COLOUR = "#FFD9A0"
MUSIC_DB = -19.0           # music bed under the voice (ducked further while speaking)
PUSH_ZOOM = 0.08           # slow push-in over a shot (Ken Burns)
BOX_ALPHA = "&H33&"        # title/caption boxes: ~80% opaque near-black
BOX_PAD_X, BOX_PAD_Y = 0.28, 0.13   # box padding around the text ink, x font size
LOGO = PROJECT_ROOT / "assets" / "brand" / "logo.png"
LOGO_SECONDS = 2.4
CTA_SECONDS = 3.6
FONT = "Ray ExtraBlack"
CAPTION_FONT = "Ray Black"
LATIN_FONT = "Avenir Next"
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


@dataclass
class Shot:
    src_in: float
    src_out: float
    close: bool = False
    bw: bool = False
    face: tuple[float, float] = (0.5, 0.35)   # normalised face centre in the source
    out_start: float = 0.0
    push: bool = False      # slow smooth zoom-in over the shot

    @property
    def length(self) -> float:
        return self.src_out - self.src_in


@dataclass
class ReelPlan:
    shots: list[Shot]
    captions: list[dict] = field(default_factory=list)   # {"start","end","text"} output time
    notes: list[dict] = field(default_factory=list)      # {"start","end","text"} output time
    flashes: list[float] = field(default_factory=list)   # output times
    duration: float = 0.0
    cold_open: float = 0.0   # length of the teaser played before the start


# --- face tracking ------------------------------------------------------------

def face_track_binary() -> Optional[Path]:
    """Compile the Vision face tracker once (macOS only); None when unavailable."""
    binary = FACE_TRACK / "face_track"
    source = FACE_TRACK / "face_track.swift"
    if binary.is_file() and (not source.is_file() or binary.stat().st_mtime >= source.stat().st_mtime):
        return binary
    swiftc = shutil.which("swiftc")
    if not swiftc or not source.is_file():
        return None
    proc = subprocess.run([swiftc, "-O", str(source), "-o", str(binary)], capture_output=True, text=True)
    if proc.returncode != 0:
        log.warning("face tracker build failed: %s", proc.stderr[-400:])
        return None
    return binary


def track_faces(video: Path, fps: float = 2.0) -> list[tuple[float, float, float]]:
    """(time, cx, cy) of the largest face, sampled at ``fps``; empty if unavailable."""
    binary = face_track_binary()
    if binary is None:
        return _track_faces_yunet(video, fps)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale=640:-2",
                        f"{tmp}/f_%05d.png"], check=True, capture_output=True)
        frames = sorted(Path(tmp).glob("f_*.png"))
        out = subprocess.run([str(binary), *map(str, frames)], capture_output=True, text=True).stdout
    faces = []
    for line in out.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("face"):
            k = int(Path(item["file"]).stem.split("_")[1]) - 1
            cx, cy = item["face"][:2]
            faces.append(((k + 0.5) / fps, float(cx), float(cy)))
    return faces


YUNET = PROJECT_ROOT / "assets" / "effects" / "models" / "yunet.onnx"


def _track_faces_yunet(video: Path, fps: float) -> list[tuple[float, float, float]]:
    """The same samples as the macOS tracker, from OpenCV's YuNet detector (any platform; the server runs Linux). Largest face per frame."""
    try:
        import cv2
        if not YUNET.is_file():
            raise FileNotFoundError(YUNET)
    except Exception as exc:
        log.warning("face tracking is not available: %s", exc)
        return []
    faces: list[tuple[float, float, float]] = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale=640:-2", "-q:v", "3", f"{tmp}/f_%05d.jpg"],
                       check=True, capture_output=True, timeout=1800)
        detector = None
        for k, frame in enumerate(sorted(Path(tmp).glob("f_*.jpg"))):
            image = cv2.imread(str(frame))
            if image is None:
                continue
            h, w = image.shape[:2]
            if detector is None:
                detector = cv2.FaceDetectorYN.create(str(YUNET), "", (w, h), 0.6, 0.3, 20)
            _, found = detector.detect(image)
            if found is None or not len(found):
                continue
            x, y, fw, fh = max(found, key=lambda f: f[2] * f[3])[:4]
            faces.append(((k + 0.5) / fps, float(min(max((x + fw / 2) / w, 0.0), 1.0)), float(min(max((y + fh / 2) / h, 0.0), 1.0))))
    return faces


def _median(values: list[float], default: float) -> float:
    values = sorted(values)
    return values[len(values) // 2] if values else default


# --- cuts and shots -----------------------------------------------------------

def speech_ranges(words: list[dict], drop: Callable[[dict], bool], duration: float) -> list[tuple[float, float]]:
    """Source ranges to keep: speech with pauses and dropped words cut out."""
    kept = [w for w in words if not drop(w)]
    ranges: list[list[float]] = []
    for w in kept:
        start, end = float(w["start"]), float(w["end"])
        if ranges and start - ranges[-1][1] <= GAP_CUT:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])
    out = []
    for k, (a, b) in enumerate(ranges):
        a = max(0.0, a - CUT_PAD, out[-1][1] if out else 0.0)
        b = min(duration, b + CUT_PAD)
        if b - a > 0.15:
            out.append((round(a, 3), round(b, 3)))
    return out


def build_shots(ranges: list[tuple[float, float]], words: list[dict]) -> list[Shot]:
    """Shots from kept ranges: framing alternates every MIN_SHOT..MAX_SHOT seconds.

    Cuts are where the framing changes; a long stretch without a cut gets a
    punch-in at the word boundary closest to its middle.
    """
    pieces: list[tuple[float, float, bool]] = []   # (in, out, starts_after_a_cut)
    for a, b in ranges:
        start = a
        while b - start > MAX_SHOT:
            target = start + (b - start) / 2 if b - start < 2 * MAX_SHOT else start + MAX_SHOT * 0.75
            bounds = [float(w["end"]) for w in words if start + MIN_SHOT * 0.6 < float(w["end"]) < b - 1.5]
            if not bounds:
                break
            split = min(bounds, key=lambda t: abs(t - target))
            pieces.append((start, split, start == a))
            start = split
        pieces.append((start, b, start == a))
    shots: list[Shot] = []
    close = False
    since_change = MIN_SHOT
    for a, b, after_cut in pieces:
        if shots and since_change >= MIN_SHOT:
            close = not close
            since_change = 0.0
        elif shots and not after_cut:
            close = not close   # a forced punch-in inside one stretch
            since_change = 0.0
        shots.append(Shot(a, b, close=close))
        since_change += b - a
    t = 0.0
    for shot in shots:
        shot.out_start = t
        t += shot.length
    return shots


def to_output(shots: list[Shot], t: float) -> float:
    """Source time to output time (times in a cut gap map to the next shot)."""
    for shot in shots:
        if t < shot.src_in:
            return shot.out_start
        if t <= shot.src_out:
            return shot.out_start + t - shot.src_in
    return shots[-1].out_start + shots[-1].length if shots else 0.0


# --- captions -----------------------------------------------------------------

def persian_digits(text: str) -> str:
    return text.translate(_FA_DIGITS) if not re.search(r"[A-Za-z]\d|\d[A-Za-z]", text) else text


def phrases(text: str, max_words: int = 6) -> list[str]:
    """Caption phrases of 2..max_words words, broken at punctuation first."""
    out: list[str] = []
    for clause in re.split(r"(?<=[،,.!?؟])\s+", text.strip()):
        words = clause.split()
        while len(words) > max_words:
            take = max_words if len(words) - max_words >= 2 else len(words) - 2
            out.append(" ".join(words[:take]))
            words = words[take:]
        if words:
            if out and len(words) == 1 and len(out[-1].split()) < max_words:
                out[-1] += " " + words[0]
            else:
                out.append(" ".join(words))
    return [p.rstrip(".") for p in out if p.strip(" .")]


def caption_events(sentences: list[dict], words: list[dict], decisions: dict, shots: list[Shot]) -> list[dict]:
    """Phrase captions on the output timeline.

    The corrected sentence is split into phrases; each phrase is timed by
    the share of characters it covers within the sentence's spoken words.
    """
    events = []
    for k, sentence in enumerate(sentences):
        text = decisions["captions"].get(k) if isinstance(decisions.get("captions"), dict) else None
        if text is None:
            text = decisions.get("captions", {}).get(str(k))
        if not text or k in decisions.get("drop", []):
            continue
        spoken = [w for w in words if sentence["start"] - 0.05 <= float(w["start"]) <= sentence["end"] + 0.05]
        if not spoken:
            continue
        parts = phrases(persian_digits(text))
        total = sum(len(p) for p in parts) or 1
        t0, t1 = float(spoken[0]["start"]), float(spoken[-1]["end"])
        # Character share -> word index -> time, so pauses inside the sentence stay aligned.
        chars = [len(w["w"]) + 1 for w in spoken]
        csum = [0]
        for c in chars:
            csum.append(csum[-1] + c)

        def time_at(share: float) -> float:
            target = share * csum[-1]
            for j, w in enumerate(spoken):
                if csum[j + 1] >= target:
                    frac = (target - csum[j]) / max(1, chars[j])
                    return float(w["start"]) + frac * (float(w["end"]) - float(w["start"]))
            return t1

        done = 0
        for part in parts:
            a = time_at(done / total)
            done += len(part)
            b = time_at(done / total)
            events.append({"start": to_output(shots, a), "end": to_output(shots, b), "text": part})
    # Each caption stays until the next one (no flicker between phrases).
    events.sort(key=lambda e: e["start"])
    for e, nxt in zip(events, events[1:]):
        if nxt["start"] - e["end"] < 0.6:
            e["end"] = nxt["start"]
    return [e for e in events if e["end"] - e["start"] > 0.05]


def plan_reel(transcript: dict, decisions: dict, faces: list[tuple[float, float, float]],
              duration: float) -> ReelPlan:
    from brain.talking_reel import is_filler

    sentences = transcript["sentences"]
    words = transcript["words"]
    dropped = [sentences[k] for k in decisions.get("drop", []) if type(k) is int and 0 <= k < len(sentences)]

    def drop(word: dict) -> bool:
        t = float(word["start"])
        return is_filler(word.get("w", "")) or any(s["start"] - 0.05 <= t <= s["end"] + 0.05 for s in dropped)

    ranges = speech_ranges(words, drop, duration)
    from engine.revision_timing import subtract_ranges
    ranges = subtract_ranges(ranges, decisions.get('source_cuts') or [])
    if not ranges:
        raise ValueError("nothing left to keep after cutting pauses")
    shots = build_shots(ranges, words)
    for shot in shots:
        inside = [(cx, cy) for t, cx, cy in faces if shot.src_in - 0.5 <= t <= shot.src_out + 0.5]
        near = inside or [(cx, cy) for t, cx, cy in sorted(faces, key=lambda f: abs(f[0] - shot.src_in))[:3]]
        shot.face = (_median([c[0] for c in near], 0.5), _median([c[1] for c in near], 0.35))
    bw_spans = [(sentences[k]["start"], sentences[k]["end"]) for k in decisions.get("bw", [])]
    for k, shot in enumerate(shots):
        mid = (shot.src_in + shot.src_out) / 2
        shot.bw = any(a - 0.2 <= mid <= b + 0.2 for a, b in bw_spans)
        # A slow push-in on emotional lines and every third longer shot.
        shot.push = shot.bw or (k % 3 == 2 and shot.length >= 3.5)

    # Cold open: the most provocative line first, then the talk from the start.
    cold = cold_open_span(decisions.get("cold_open"), sentences, words)
    cold_captions: list[dict] = []
    if cold:
        a, b, text = cold
        teaser = Shot(a, b, close=True, push=True, face=_face_at(faces, a, b))
        for shot in shots:
            shot.out_start += teaser.length
        parts = phrases(persian_digits(text))
        total_chars = sum(len(p) for p in parts) or 1
        t = 0.0
        for part in parts:
            span = teaser.length * len(part) / total_chars
            cold_captions.append({"start": t, "end": t + span, "text": part})
            t += span
        shots = [teaser] + shots
    main = shots[1:] if cold else shots
    total = shots[-1].out_start + shots[-1].length
    flashes = [main[0].out_start] if cold else []
    for prev, shot in zip(main, main[1:]):
        if prev.bw != shot.bw:
            flashes.append(shot.out_start)
    notes = []
    for note in decisions.get("notes", []):
        s = sentences[note["i"]]
        start = to_output(main, s["start"])
        stop = min(total, max(start + 2.4, min(to_output(main, s["end"]), start + 3.6)))
        notes.append({"start": start, "end": stop, "text": persian_digits(note["text"])})
    for note in notes:
        flashes += [note["start"], note["end"]]
    flashes = sorted({round(t, 2) for t in flashes})
    return ReelPlan(shots=shots, captions=cold_captions + caption_events(sentences, words, decisions, main),
                    notes=notes, flashes=flashes, duration=total, cold_open=shots[0].length if cold else 0.0)


def _face_at(faces: list[tuple[float, float, float]], a: float, b: float) -> tuple[float, float]:
    inside = [(cx, cy) for t, cx, cy in faces if a - 0.5 <= t <= b + 0.5]
    near = inside or [(cx, cy) for t, cx, cy in sorted(faces, key=lambda f: abs(f[0] - a))[:3]]
    return _median([c[0] for c in near], 0.5), _median([c[1] for c in near], 0.35)


def _plain(word: str) -> str:
    return re.sub(r"[^\w]", "", word.replace("\u200c", "")).replace("ي", "ی").replace("ك", "ک")


def cold_open_span(cold: Optional[dict], sentences: list[dict], words: list[dict]
                   ) -> Optional[tuple[float, float, str]]:
    """Source (start, end, text) of the teaser line, found in the sentence's words."""
    if not cold or cold.get("i") is None:
        return None
    sentence = sentences[int(cold["i"])]
    spoken = [w for w in words if sentence["start"] - 0.05 <= float(w["start"]) <= sentence["end"] + 0.05]
    if not spoken:
        return None
    wanted = [_plain(w) for w in str(cold.get("text") or "").split() if _plain(w)]
    best = None
    if wanted:
        plain = [_plain(w["w"]) for w in spoken]
        for start in range(len(plain)):
            hits = sum(1 for k, token in enumerate(wanted) if start + k < len(plain) and plain[start + k] == token)
            if hits and (best is None or hits > best[0]):
                best = (hits, start)
    if best and best[0] >= max(2, len(wanted) // 2):
        first = spoken[best[1]]
        last = spoken[min(len(spoken), best[1] + len(wanted)) - 1]
        text = str(cold.get("text"))
    else:
        first, last, text = spoken[0], spoken[-1], sentence["text"]
    a, b = float(first["start"]) - CUT_PAD, float(last["end"]) + 0.25
    return (max(0.0, a), b, text) if 1.0 <= b - a <= 7.0 else None


# --- overlay (ASS) --------------------------------------------------------------

def _colour(hex_colour: str) -> str:
    return f"&H{_ass_colour(hex_colour)[4:]}&"


def _esc(text: str) -> str:
    from engine.persian_text import join_lam_alef
    text = join_lam_alef(text)
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _spaced(text: str) -> str:
    # The Ray font's space glyph is nearly zero wide.
    return re.sub(r" +", "  ", text.strip())


def hook_line(hook: str, highlight: list[str]) -> str:
    """Hook text with highlighted phrases wrapped in yellow colour overrides."""
    text = _esc(hook)
    for phrase in sorted(highlight, key=len, reverse=True):
        phrase = _esc(phrase)
        if phrase and phrase in text:
            text = text.replace(phrase, "\x00" + phrase + "\x01", 1)
    text = _spaced(text)
    return text.replace("\x00", f"{{\\1c{_colour(YELLOW)}}}").replace("\x01", "{\\1c&HFFFFFF&}")


def build_ass(plan: ReelPlan, hook: str, highlight: list[str], name: str, title: str,
              fonts_dir: Optional[Path], *, moments: bool = True, caption_font: str | None = None) -> str:
    CAPTION_FONT = caption_font or globals()['CAPTION_FONT']
    end = max(0.05, plan.duration - 0.02)
    hook_size = int(H * 0.041)
    # Wrap a long hook to two lines at the space nearest the middle.
    plain_width = measure_text_boxes([(_spaced(_esc(hook)), hook_size)], W, H, FONT, fonts_dir)[0][0]
    lines = [hook]
    if plain_width > W * 0.84 and " " in hook:
        spaces = [k for k, c in enumerate(hook) if c == " "]
        cut = min(spaces, key=lambda k: abs(k - len(hook) / 2))
        lines = [hook[:cut], hook[cut + 1:]]
    inks = measure_text_boxes([(_spaced(_esc(l)), hook_size) for l in lines], W, H, FONT, fonts_dir)
    widest = max(w for w, _, _ in inks)
    if widest > W * 0.86:
        hook_size = int(hook_size * W * 0.86 / widest)
        inks = [(int(w * W * 0.86 / widest), a, b) for w, a, b in inks]
        widest = max(w for w, _, _ in inks)
    hook_y = H * 0.74
    pitch = 1.15 * hook_size
    anchors = [hook_y + (k - (len(lines) - 1) / 2) * pitch for k in range(len(lines))]
    top = anchors[0] + inks[0][1] - BOX_PAD_Y * hook_size
    bottom = anchors[-1] + inks[-1][2] + BOX_PAD_Y * hook_size
    half = widest / 2 + BOX_PAD_X * hook_size

    # The hook pops in (scale bounce) at the start and then stays.
    events = [_rounded_rect(1, 0, end, W / 2 - half, top, W / 2 + half, bottom, "#000000", 18,
                            extra=f"\\1a{BOX_ALPHA}\\fad(200,0)")]
    pop = "\\fscx140\\fscy140\\t(0,260,\\fscx92\\fscy92)\\t(260,420,\\fscx100\\fscy100)\\fad(120,0)"
    for line, y in zip(lines, anchors):
        events.append(f"Dialogue: 2,{_ass_time(0)},{_ass_time(end)},hook,,0,0,0,,"
                      f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.1f}){pop}}}{hook_line(line, highlight)}")

    # Phrase captions in their own dark box right above the hook box.
    cap_size = int(H * 0.0325)
    texts = [_spaced(_esc(c["text"])) for c in plan.captions]
    cap_inks = measure_text_boxes([(t, cap_size) for t in texts], W, H, CAPTION_FONT, fonts_dir) if texts else []
    gap = 12
    caption_top = top
    for c, text, (cw, ca, cb) in zip(plan.captions, texts, cap_inks):
        size = cap_size if cw <= W * 0.88 else int(cap_size * W * 0.88 / cw)
        f = size / cap_size
        cw, ca, cb = cw * f, ca * f, cb * f
        box_bottom = top - gap
        box_top = box_bottom - (cb - ca) - 2 * BOX_PAD_Y * size
        y = box_top + BOX_PAD_Y * size - ca
        caption_top = min(caption_top, box_top)
        chalf = cw / 2 + BOX_PAD_X * size
        events.append(_rounded_rect(3, c["start"], c["end"], W / 2 - chalf, box_top, W / 2 + chalf, box_bottom,
                                    "#000000", 14, extra=f"\\1a{BOX_ALPHA}"))
        events.append(f"Dialogue: 4,{_ass_time(c['start'])},{_ass_time(c['end'])},caption,,0,0,0,,"
                      f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.1f})\\fs{size}}}{text}")
    if name or title:
        y = bottom + H * 0.062
        if name:
            # The name style's letter spacing suits Latin names; in Persian it breaks the joined letters.
            spacing = "\\fsp0" if re.search(r"[؀-ۿ]", name) else ""
            events.append(f"Dialogue: 2,{_ass_time(0)},{_ass_time(end)},name,,0,0,0,,"
                          f"{{\\an2\\pos({W / 2:.0f},{y:.1f}){spacing}}}{_esc(name)}")
        if title:
            events.append(f"Dialogue: 2,{_ass_time(0)},{_ass_time(end)},title,,0,0,0,,"
                          f"{{\\an8\\pos({W / 2:.0f},{y + 6:.1f})}}{_esc(title)}")
    # Emphasis moments belong to the phrase alone: every other overlay is off.
    events = _cut_windows(events, [(n["start"], n["end"]) for n in plan.notes])
    if moments:   # False when the Tscaps layer draws the emphasis phrases
        events += emphasis_events(plan.notes, fonts_dir)
    for t in plan.flashes:
        # A short warm glow across the cut, not a solid wash.
        events.append(_rounded_rect(6, max(0.0, t - 0.1), t + 0.28, 0, 0, W, H, FLASH_COLOUR, 0,
                                    extra="\\1a&H90&\\fad(100,180)"))

    white, black = "&H00FFFFFF", "&H00000000"
    styles = [
        # A tiny hard shadow (no outline, no blur) lifts the text off its box.
        f"Style: hook,{FONT},{hook_size},{white},&H000000FF,{black},&H4D000000,-1,0,0,0,100,100,0,0,1,0,2,5,0,0,0,-1",
        f"Style: caption,{CAPTION_FONT},{cap_size},{white},&H000000FF,{black},&H4D000000,"
        f"-1,0,0,0,100,100,0,0,1,0,2,5,0,0,0,-1",
        f"Style: emph,{FONT},{int(H * 0.09)},{white},&H000000FF,{black},&H4D000000,"
        f"-1,0,0,0,100,100,0,0,1,0,3,5,0,0,0,-1",
        f"Style: name,{LATIN_FONT} Medium,{int(H * 0.019)},{white},&H000000FF,&H90000000,&H90000000,"
        f"0,0,0,0,100,100,1,0,1,0,1,2,0,0,0,1",
        f"Style: title,{LATIN_FONT} Demi Bold,{int(H * 0.0215)},{white},&H000000FF,&H90000000,&H90000000,"
        f"-1,0,0,0,100,100,0,0,1,0,1,8,0,0,0,1",
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


def _cut_windows(events: list[str], windows: list[tuple[float, float]]) -> list[str]:
    """Remove the given time windows from every event (an event may split in two)."""
    def parse(t: str) -> float:
        h, m, sec = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(sec)

    out = []
    for event in events:
        head, rest = event.split(": ", 1)
        fields = rest.split(",", 3)
        spans = [(parse(fields[1]), parse(fields[2]))]
        for w0, w1 in windows:
            spans = [piece for a, b in spans for piece in ((a, min(b, w0)), (max(a, w1), b)) if piece[1] - piece[0] > 0.04]
        for a, b in spans:
            body = fields[3]
            if body.startswith('hook,') and a > parse(fields[1]) + .01:
                # The same pinned title resumes after a full-screen emphasis.
                # Its intro animation must not restart as a new hook each time.
                body = re.sub(r'\\t\([^)]*\)|\\fad\([^)]*\)', '', body)
                body = re.sub(r'\\fsc[xy][\d.]+', '', body)
                body = body.replace(r'\an5', r'\an5\fscx100\fscy100', 1)
            out.append(f"{head}: {fields[0]},{_ass_time(a)},{_ass_time(b)},{body}")
    return out


def emphasis_events(notes: list[dict], fonts_dir: Optional[Path]) -> list[str]:
    """The emphasis phrase word by word: big, centred, each word punching in, all in white (colour is kept for the pinned hook)."""
    events = []
    base = int(H * 0.125)
    for note in notes:
        words = note["text"].replace("،", "").split()
        if not words:
            continue
        inks = measure_text_boxes([(_esc(w), base) for w in words], W, H, FONT, fonts_dir)
        size = min(base, int(base * W * 0.86 / max(w for w, _, _ in inks)))
        pitch = 1.02 * size
        t0, t1 = note["start"], note["end"]
        step = min(0.42, (t1 - t0) * 0.55 / max(1, len(words)))
        for k, word in enumerate(words):
            y = H * 0.45 + (k - (len(words) - 1) / 2) * pitch
            colour = ""
            start = t0 + 0.12 + k * step
            punch = "\\fscx135\\fscy135\\t(0,170,\\fscx96\\fscy96)\\t(170,260,\\fscx100\\fscy100)\\fad(60,180)"
            events.append(f"Dialogue: 7,{_ass_time(start)},{_ass_time(t1)},emph,,0,0,0,,"
                          f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.1f})\\fs{size}{colour}{punch}}}{_esc(word)}")
    return events


# --- render -------------------------------------------------------------------

# Warm, contrasty and rich: S-curve with deeper blacks, warm shadows to highlights.
GRADE = ("eq=contrast=1.10:saturation=1.16:gamma=0.98,"
         "curves=master='0/0 0.12/0.08 0.5/0.5 0.85/0.9 1/1',"
         "colorbalance=rs=0.04:bs=-0.05:rm=0.05:gm=0.008:bm=-0.05:rh=0.035:bh=-0.04,unsharp=5:5:0.6")
BW = "hue=s=0,eq=contrast=1.12:brightness=-0.01"


def crop_for(
    shot: Shot, sw: int, sh: int, *, base_zoom: float = 1.0,
    close_zoom: float = CLOSE_ZOOM, framing: Optional[dict] = None,
) -> tuple[int, int, int, int]:
    """(w, h, x, y) of the 9:16 source crop for a shot's framing.

    Auto framing (on unless switched off): a wide shot is zoomed in just enough (never past 1.25x) to bring a speaker who stands off to one
    side back to the middle, and keeps headroom above the face; ``shift_x`` / ``shift_y`` (-100..100, percent of the free room) move the
    window by hand.
    """
    framing = framing or {}
    auto = framing.get("auto", True)
    shift_x = max(-100.0, min(100.0, float(framing.get("shift_x", 0) or 0))) / 100
    shift_y = max(-100.0, min(100.0, float(framing.get("shift_y", 0) or 0))) / 100
    fx, fy = shot.face[0] * sw, shot.face[1] * sh
    framing_zoom = close_zoom if shot.close else base_zoom
    if auto and not shot.close:
        off = min(abs(shot.face[0] - 0.5), 0.35)
        framing_zoom = max(framing_zoom, min(1.25, 1 / (1 - 2 * off)))
    if shift_x or shift_y:
        framing_zoom = max(framing_zoom, 1.12)      # there is no room to move a window that is already the whole picture
    ch = sh / max(1.0, framing_zoom)
    cw = ch * 9 / 16
    if cw > sw:   # a portrait or square source: use the full width instead
        cw, ch = sw, sw * 16 / 9
        if ch > sh:
            ch = sh
        if framing_zoom > 1:
            cw = sw / framing_zoom
            ch = cw * 16 / 9
            if ch > sh:
                ch, cw = sh, sh * 9 / 16
    cw, ch = int(cw) & ~1, int(ch) & ~1
    x = min(max(0, fx - cw / 2), sw - cw)
    # Close framing keeps the face in the upper third; a zoomed wide framing keeps a little more headroom than the centre would.
    if shot.close:
        y = min(max(0, fy - 0.36 * ch), sh - ch)
    elif ch < sh:
        y = min(max(0, fy - 0.40 * ch), sh - ch) if auto else (sh - ch) / 2
    else:
        y = 0
    x += shift_x * (sw - cw) / 2
    y += shift_y * (sh - ch) / 2
    x, y = min(max(0, x), sw - cw), min(max(0, y), sh - ch)
    return cw, ch, int(x) & ~1, int(y) & ~1


def source_colour_filter(video: Path) -> str:
    """Normalize HDR phone footage to SDR before applying editable grading.

    Browsers tone-map HLG/PQ previews automatically. Without this explicit
    conversion FFmpeg applies SDR controls to HDR-coded values, so export and
    preview cannot match.
    """
    try:
        raw = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=color_transfer", "-of", "default=nw=1:nk=1", str(video)],
            check=True, capture_output=True, text=True,
        ).stdout.strip().lower()
    except (OSError, subprocess.CalledProcessError):
        raw = ""
    if raw not in {"arib-std-b67", "smpte2084"}:
        return "null"
    return (
        "zscale=transfer=linear:npl=100,format=gbrpf32le,"
        # This shoulder closely matches the browser's SDR presentation of
        # iPhone HLG. Mobius left faces and pale clothes visibly overexposed.
        "zscale=primaries=bt709,tonemap=hable:desat=0,"
        # Keep ten-bit precision through crop, zoom and the editable grade.
        # Quantising HLG to 8-bit here caused banding/posterised skin, most
        # visible in close crops.  The final encoder conversion still emits
        # broadly compatible yuv420p.
        "zscale=transfer=bt709:matrix=bt709:range=tv:dither=error_diffusion,"
        "format=yuv420p10le"
    )


def measure_look(video: Path, source_colour: str = "null", samples: int = 12) -> dict:
    """Average colour and tonal spread of the footage, from a few small frames spread over it: {"r","g","b" (0..255 means), "low","high" (luma
    10th/90th percentile), "mean"}. Empty when the frames cannot be read."""
    try:
        duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video)],
                                        check=True, capture_output=True, text=True, timeout=60).stdout.strip() or 0)
        chain = f"fps={samples / max(duration, 1.0):.5f},{source_colour},scale=16:16:flags=area,format=rgb24"
        raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-vf", chain, "-frames:v", str(samples), "-f", "rawvideo", "-"],
                             check=True, capture_output=True, timeout=300).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    pixels = [raw[i:i + 3] for i in range(0, len(raw) - 2, 3)]
    if len(pixels) < 64:
        return {}
    lumas = sorted(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in pixels)
    n = len(pixels)
    return {"r": sum(p[0] for p in pixels) / n, "g": sum(p[1] for p in pixels) / n, "b": sum(p[2] for p in pixels) / n,
            "low": lumas[n // 10], "high": lumas[n * 9 // 10], "mean": sum(lumas) / n}


def auto_look(stats: dict) -> dict:
    """Corrections that bring the footage to a normal exposure and a neutral-ish white balance, kept mild: a room can be warm on purpose.

    {"exposure": multiplier on luma (0.88..1.25), "contrast": 0.95..1.15, "red"/"blue": channel gains (0.92..1.08)}. All 1.0 when unknown."""
    if not stats:
        return {"exposure": 1.0, "contrast": 1.0, "red": 1.0, "blue": 1.0}
    clamp = lambda v, a, b: max(a, min(b, v))
    exposure = clamp(118.0 / max(stats["mean"], 1.0), 0.88, 1.25)
    spread = max(stats["high"] - stats["low"], 1.0)
    contrast = clamp(105.0 / spread, 0.95, 1.15)
    gain = lambda channel: clamp(1 + 0.6 * (stats["g"] / max(stats[channel], 1.0) - 1), 0.92, 1.08)
    return {"exposure": round(exposure, 3), "contrast": round(contrast, 3), "red": round(gain("r"), 3), "blue": round(gain("b"), 3)}


def auto_grade_filter(look: dict) -> str:
    """The ffmpeg filters of an ``auto_look`` ("null" when there is nothing to correct)."""
    parts = []
    if abs(look["red"] - 1) > 0.004 or abs(look["blue"] - 1) > 0.004:
        parts.append(f"colorchannelmixer=rr={look['red']}:bb={look['blue']}")
    if abs(look["exposure"] - 1) > 0.01:
        parts.append(f"lutyuv=y='clip(val*{look['exposure']},16,235)'")
    if abs(look["contrast"] - 1) > 0.01:
        parts.append(f"eq=contrast={look['contrast']}")
    return ",".join(parts) or "null"


def ffmpeg_error(stderr: str, limit: int = 1200) -> str:
    """Keep the actionable FFmpeg failure instead of trailing encoder stats."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    needles = ("error", "failed", "invalid", "cannot", "no space", "broken pipe", "conversion")
    useful = [line for line in lines if any(word in line.lower() for word in needles)]
    chosen = useful[-12:] if useful else lines[-20:]
    return "\n".join(chosen)[-limit:]


def display_video_size(video: Path) -> tuple[int, int, float]:
    """Dimensions after FFmpeg's default autorotation, not coded sensor dimensions."""
    raw = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=width,height:stream_tags=rotate:stream_side_data=rotation:format=duration',
        '-of', 'json', str(video),
    ], capture_output=True, text=True, check=True)
    data = json.loads(raw.stdout)
    stream = data['streams'][0]
    width, height = int(stream['width']), int(stream['height'])
    rotation = float(stream.get('tags', {}).get('rotate', 0))
    for side in stream.get('side_data_list', []):
        if 'rotation' in side:
            rotation = float(side['rotation'])
            break
    if round(rotation) % 180 == 90:
        width, height = height, width
    return width, height, float(data['format']['duration'])


def prepare_render_source(video: Path, work_dir: Path, on_progress=None, on_metrics=None) -> Path:
    """Cache one SDR delivery-resolution decode before opening per-shot inputs.

    High resolution HDR decoded once per shot exhausts container memory and
    repeats floating point tone mapping. Normalized face coordinates remain valid.
    """
    sw, sh, duration = display_video_size(video)
    colour = source_colour_filter(video)
    if max(sw, sh) <= 1920 and colour == "null":
        return video
    import hashlib
    stamp = f"{video.resolve()}:{video.stat().st_size}:{video.stat().st_mtime_ns}:sdr-display-v3"
    key = hashlib.sha256(stamp.encode()).hexdigest()[:16]
    target = work_dir / f"render_source_{key}.mp4"
    if target.is_file(): return target
    work_dir.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.partial.mp4')
    ratio = min(1.0, 1920 / max(sw, sh))
    width, height = max(2, int(sw * ratio) // 2 * 2), max(2, int(sh * ratio) // 2 * 2)
    pixel_format = 'yuv420p' if colour == 'null' else 'yuv420p10le'
    from engine.source_progress import convert
    command = [ass_burner_ffmpeg(), '-hide_banner', '-v', 'error', '-y',
        '-threads', '1', '-i', str(video), '-filter_threads', '1',
        '-vf', f'fps={RENDER_FPS},{colour},scale={width}:{height}:flags=lanczos,setsar=1,format={pixel_format}',
        '-map', '0:v:0', '-map', '0:a:0?', '-metadata:s:v:0', 'rotate=0', '-c:v', 'libx264', '-threads', '2',
        '-preset', 'veryfast', '-crf', '16', '-c:a', 'copy',
        '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
        '-progress', 'pipe:1', '-nostats', str(temporary)]
    import fcntl
    with target.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.is_file(): return target
        try:
            convert(command, duration, on_progress, on_metrics=on_metrics)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        temporary.replace(target)
    return target


def cached_shot(inputs: list[str], filters: list[str], index: int, duration: float, work_dir: Path) -> Path:
    """Bound memory to one shot; high-quality intermediate is safe to reuse."""
    import hashlib
    stamps = []
    for i, token in enumerate(inputs[:-1]):
        if token == '-i':
            p = Path(inputs[i+1]); stamps.append((str(p), p.stat().st_size, p.stat().st_mtime_ns))
    key = hashlib.sha256(json.dumps([inputs, filters, duration, stamps, 'shot-v1']).encode()).hexdigest()[:20]
    root = work_dir / 'shot_cache'; root.mkdir(parents=True, exist_ok=True)
    out = root / f'{key}.mkv'
    if out.is_file(): return out
    temporary = root / f'{key}.partial.mkv'
    graph = filters[:-1] + [filters[-1] + f';[a{index}]aresample=48000,apad,atrim=duration={duration:.9f}[audio]']
    subprocess.run([ass_burner_ffmpeg(), '-hide_banner','-v','error','-y',
        '-filter_complex_threads','2','-filter_threads','2',*inputs,'-filter_complex',';'.join(graph),
        '-map',f'[v{index}]','-map','[audio]','-c:v','libx264','-threads','2',
        '-preset','ultrafast','-crf','12','-pix_fmt','yuv420p','-c:a','pcm_s16le',
        '-t',f'{duration:.9f}',str(temporary)],check=True,capture_output=True)
    temporary.replace(out)
    return out


def shot_concat(clips: list[tuple[Path,float]], work_dir: Path) -> list[str]:
    manifest = work_dir / 'shot_cache' / 'concat.txt'
    manifest.write_text('ffconcat version 1.0\n' + ''.join(
        "file '" + str(p.resolve()).replace("'", "'\\''") + f"'\nduration {duration:.9f}\n" for p,duration in clips))
    return ['-threads','1','-f','concat','-safe','0','-i',str(manifest)]


def eval_fps(fps: str) -> float:
    num, _, den = fps.partition("/")
    return float(num) / float(den or 1)


def vignette_png(out: Path, bottom_shade: float = 0, strength: float = 1) -> Path:
    """Soft edge vignette, darker towards the bottom (text area), as an RGBA overlay."""
    import numpy as np
    from PIL import Image

    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    nx, ny = (x - W / 2) / (W / 2), (y - H / 2) / (H / 2)
    edge = np.clip((np.sqrt(nx ** 2 * 0.9 + ny ** 2 * 0.55) - 0.55) / 0.6, 0, 1) ** 1.6 * 0.45
    bottom = np.clip((y / H - 0.55) / 0.45, 0, 1) ** 1.4 * 0.55
    alpha = np.clip(1 - (1 - edge) * (1 - bottom), 0, 0.8)
    alpha *= max(0, min(1, strength))
    shade = np.clip((y / H - 0.72) / 0.28, 0, 1) * max(0, min(.6, bottom_shade))
    alpha = 1 - (1 - alpha) * (1 - shade)
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(out)
    return out


def music_bed(music: Path, duration: float, work_dir: Path) -> Path:
    """Loop a short track to ``duration`` with crossfaded seams (no hard loop jump)."""
    length = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                   str(music)], capture_output=True, text=True).stdout.strip() or 0)
    if length <= 0 or length >= duration:
        return music
    fade = min(2.0, length / 4)
    copies = int((duration - fade) // (length - fade)) + 1
    out = work_dir / f"music_bed_{music.stem}_{copies}.wav"
    if out.is_file():
        return out
    chain = [f"[0:a][1:a]acrossfade=d={fade}[x1]"] + [
        f"[x{k - 1}][{k}:a]acrossfade=d={fade}[x{k}]" for k in range(2, copies)]
    last = f"x{copies - 1}" if copies > 1 else "0:a"
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for _ in range(copies):
        cmd += ["-i", str(music)]
    if copies > 1:
        cmd += ["-filter_complex", ";".join(chain), "-map", f"[{last}]"]
    subprocess.run(cmd + [str(out)], check=True, capture_output=True)
    return out


def fonts_bundle(work_dir: Path) -> Path:
    """libass loads fonts from one flat directory; collect the reel's fonts there."""
    out = work_dir / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    for path in (PROJECT_ROOT / "presets" / "fonts").rglob("*"):
        if path.suffix.lower() in {".ttf", ".otf"} and not (out / path.name).exists():
            shutil.copy2(path, out / path.name)
    return out


# --- outro: CTA card and logo motion -------------------------------------------

CTA_FONT = "Ray ExtraBlack"
CTA_HIGHLIGHT = re.compile(r"عدد\s*\S+\s*(?:رو|را)?\s*(?:برام\s*)?کامنت\s*کن")


CTA_LINE_CHARS = 24


def _wrap_words(line: str, limit: int) -> list[str]:
    """``line`` split at spaces into pieces of at most ``limit`` characters (a longer single word stays whole)."""
    pieces, current = [], ""
    for word in line.split(" "):
        if current and len(current) + 1 + len(word) > limit:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    return pieces + [current] if current else pieces


def cta_events(cta: str, t0: float, t1: float, fonts_dir: Optional[Path]) -> list[str]:
    """Two-line CTA set straight on the end-card background; "عدد N رو کامنت کن" in gold."""
    from ..localize import END_CARD_HIGHLIGHT

    text = persian_digits(" ".join(cta.split()))
    words = text.split(" ")
    size = int(H * 0.05)
    lines = [text]
    match = CTA_HIGHLIGHT.search(text)
    if match and match.start() > 0 and text[:match.start()].strip():
        # The ask gets its own line: "... / عدد ۲۰ رو کامنت کن ..."
        lines = [text[:match.start()].strip(), text[match.start():].strip()]
    elif len(words) > 3:
        cut = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(text) / 2))
        lines = [" ".join(words[:cut]), " ".join(words[cut:])]
    lines = [piece for line in lines for piece in _wrap_words(line, CTA_LINE_CHARS)]
    spans, pos = [], 0
    for line in lines:
        pos = text.index(line, pos)
        spans.append((pos, pos + len(line)))
        pos += len(line)
    inks = measure_text_boxes([(_spaced(_esc(l)), size) for l in lines], W, H, CTA_FONT, fonts_dir)
    # The measured width is trusted only when it is not smaller than a plain estimate: with a missing font it comes out far too small
    # and the card ran edge to edge (no margin at all on the left and right).
    widest = max(max(w for w, _, _ in inks), max(len(l) for l in lines) * size * 0.5)
    if widest > W * 0.78:
        size = int(size * W * 0.78 / widest)
    pitch = 1.12 * size
    anchors = [H * 0.47 + (k - (len(lines) - 1) / 2) * pitch for k in range(len(lines))]
    pop = "\\fad(250,0)\\fscx85\\fscy85\\t(0,300,\\fscx100\\fscy100)"
    gold, white = _colour(END_CARD_HIGHLIGHT), "&HFFFFFF&"
    events = []
    for line, (a, b), y in zip(lines, spans, anchors):
        if match and match.start() < b and match.end() > a:
            h0, h1 = max(match.start(), a) - a, min(match.end(), b) - a
            parts = [_spaced(_esc(line[:h0])), f"{{\\1c{gold}}}" + _spaced(_esc(line[h0:h1])),
                     f"{{\\1c{white}}}" + _spaced(_esc(line[h1:]))]
            body = "\u00a0\u00a0".join(p for p in parts if p.strip("{}\\1c&HFFFFFF&") or p == parts[1])
        else:
            body = _spaced(_esc(line))
        events.append(f"Dialogue: 2,{_ass_time(t0)},{_ass_time(t1)},cta,,0,0,0,,"
                      f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.1f}){pop}}}{body}")
    return events


def logo_frames(out_dir: Path, fps: float, seconds: float = LOGO_SECONDS, motion: str = "pop",
                logo_path: Optional[Path] = None) -> Path:
    """Logo reveal frames: scale up with a soft overshoot, glow, a light sweep, fade out."""
    import math

    import numpy as np
    from PIL import Image, ImageFilter

    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "logo_%04d.png"
    count = max(1, round(seconds * fps))
    if (out_dir / f"logo_{count:04d}.png").is_file():
        return pattern
    mark = Image.open(logo_path or LOGO).convert("RGBA")
    base_h = int(H * 0.11)
    mark = mark.resize((int(mark.width * base_h / mark.height), base_h), Image.LANCZOS)
    padded = Image.new("RGBA", (mark.width + 160, mark.height + 160), (255, 255, 255, 0))
    padded.alpha_composite(mark, (80, 80))
    glow = padded.filter(ImageFilter.GaussianBlur(28))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    radial = np.clip(1 - np.sqrt(((xx - W / 2) / (W * 0.7)) ** 2 + ((yy - H * 0.47) / (H * 0.4)) ** 2), 0, 1)
    bg = np.stack([11 + 16 * radial, 11 + 12 * radial, 12 + 8 * radial], -1).astype(np.uint8)

    def ease_back(t: float) -> float:   # overshoots slightly, then settles
        c = 1.70158
        return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

    for k in range(count):
        t = k / fps
        p = min(1.0, t / 0.75)
        if motion == "fade" or motion == "none":
            scale = 1.0
        elif motion == "slide":
            scale = 1.0
        else:
            scale = 0.55 + 0.45 * ease_back(p)
        alpha = min(1.0, t / 0.3) * (1 - max(0.0, (t - (seconds - 0.45)) / 0.45))
        frame = Image.fromarray(bg.copy()).convert("RGBA")
        size = (max(1, int(mark.width * scale)), max(1, int(mark.height * scale)))
        m = mark.resize(size, Image.LANCZOS)
        g = glow.resize((int(glow.width * scale), int(glow.height * scale)), Image.LANCZOS)
        cx, cy = W // 2, int(H * 0.47)
        if motion == "slide":
            cx = int(-m.width / 2 + (W / 2 + m.width / 2) * (1 - (1 - p) ** 3))
        # Light sweep: a bright diagonal band crossing the mark between 0.8 s and 1.5 s.
        sweep = (t - 0.8) / 0.7
        if 0 <= sweep <= 1:
            arr = np.array(m).astype(np.float32)
            h, w = arr.shape[:2]
            band = (np.arange(w)[None, :] + np.arange(h)[:, None] * 0.6) / (w + h * 0.6)
            boost = np.clip(1 - np.abs(band - sweep) / 0.12, 0, 1)[..., None] * 0.9
            arr[..., :3] = np.minimum(255, arr[..., :3] + boost * 255)
            m = Image.fromarray(arr.astype(np.uint8), "RGBA")
        for layer, strength in ((g, 0.55 + 0.25 * math.sin(min(1.0, t / 1.2) * math.pi)), (m, 1.0)):
            layer = layer.copy()
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha * strength)))
            frame.alpha_composite(layer, (cx - layer.width // 2, cy - layer.height // 2))
        frame.convert("RGB").save(out_dir / f"logo_{k + 1:04d}.png")
    return pattern


def render_outro(work_dir: Path, cta: str, fps: str, fonts: Path, *, logo_enabled: bool = True,
                 logo_motion: str = "pop", logo_path: Optional[Path] = None) -> tuple[Optional[Path], float]:
    """Silent outro clip: optional CTA card, then the logo motion. Returns (path, seconds)."""
    from ..localize import render_end_card

    ffmpeg = ass_burner_ffmpeg()
    fps_value = eval_fps(fps)
    active_logo = logo_path if logo_path and logo_path.is_file() else LOGO
    if (not active_logo.is_file() or not logo_enabled) and not cta:
        return None, 0.0
    parts, inputs, chains = [], [], []
    cta_seconds = CTA_SECONDS if cta else 0.0
    if cta:
        # The single "end logo" toggle owns every logo appearance in the
        # outro, including the small static mark on the CTA card.  Previously
        # it only disabled the standalone logo-motion clip.
        cta_logo = active_logo if logo_enabled and active_logo.is_file() else None
        bg = render_end_card(work_dir / "cta_bg.png", W, H, cta_logo)
        ass = work_dir / "cta.ass"
        ass.write_text("\n".join([
            "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: cta,{CTA_FONT},{int(H * 0.05)},&H00FFFFFF,&H000000FF,&H00000000,&H66000000,"
            "-1,0,0,0,100,100,0,0,1,0,2,5,0,0,0,-1",
            "Style: plain,Arial,10,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *cta_events(cta, 0, cta_seconds, fonts),
        ]) + "\n", encoding="utf-8")
        inputs += ["-loop", "1", "-framerate", fps, "-t", f"{cta_seconds:.3f}", "-i", str(bg)]
        chains.append(f"[{len(parts)}:v]scale={W}:{H},setsar=1,format=yuv420p,{subtitles_filter(ass, fonts)}[p{len(parts)}]")
        parts.append(f"[p{len(parts)}]")
    logo_seconds = 0.0
    if active_logo.is_file() and logo_enabled:
        logo_seconds = LOGO_SECONDS
        logo_key = f"{active_logo.stat().st_mtime_ns:x}"
        pattern = logo_frames(work_dir / f"logo_frames_{logo_motion}_{logo_key}", fps_value,
                              motion=logo_motion, logo_path=active_logo)
        inputs += ["-framerate", fps, "-i", str(pattern)]
        chains.append(f"[{len(parts)}:v]setsar=1,format=yuv420p[p{len(parts)}]")
        parts.append(f"[p{len(parts)}]")
    out = work_dir / "outro.mp4"
    graph = ";".join(chains + ["".join(parts) + f"concat=n={len(parts)}:v=1:a=0,fps={fps}[o]"])
    subprocess.run([ffmpeg, "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[o]",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True,
                   capture_output=True)
    return out, cta_seconds + logo_seconds


def render(video: Path, plan: ReelPlan, out: Path, *, hook: str, highlight: list[str], name: str, title: str,
           work_dir: Path, music: Optional[Path] = None, cta: str = "",
           render_settings: Optional[dict] = None,
           logo_path: Optional[Path] = None, overlay: Optional[Path] = None,
           on_progress: Optional[Callable[[int], None]] = None, on_stage=None) -> Path:
    """`overlay`: optional transparent WebM (engine/tscaps_overlay.py) that draws the key moments above the ASS layer."""
    ffmpeg = ass_burner_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("Talking reels need an ffmpeg with libass (brew install ffmpeg-full)")
    if on_stage: on_stage('rendering source preparation', 'در حال بررسی و تبدیل فرمت فایل ورودی به نسخهٔ مناسب تدوین')
    video = prepare_render_source(video, work_dir, (lambda pct: on_progress(round(pct * .1))) if on_progress else None,
                                  getattr(on_progress, 'metrics', None))
    if on_progress: on_progress(10)
    sw, sh, _ = display_video_size(video)
    # Always render social delivery at a fixed 30fps.  In particular, feeding
    # a 60fps phone source straight into zoompan(d=1,fps=30) changes the video
    # clock relative to its audio and produces the visible lag/judder.
    fps = RENDER_FPS
    work_dir.mkdir(parents=True, exist_ok=True)
    if on_stage: on_stage('rendering captions', 'در حال آماده‌سازی فونت، زیرنویس و تیترهای ویدیو')
    fonts = fonts_bundle(work_dir)
    ass = work_dir / "reel.ass"
    settings = render_settings or {}
    ass_text = build_ass(plan, hook, highlight, name, title, fonts, moments=overlay is None,
                         caption_font='Vazirmatn' if settings.get('caption_font') == 'Vazirmatn' else None)
    from engine.caption_looks import apply as apply_caption_looks
    ass_text = apply_caption_looks(ass_text, plan.captions)
    title_color = str(settings.get("title_color") or YELLOW)
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", title_color):
        old, new = _colour(YELLOW), _colour(title_color)
        ass_text = ass_text.replace(old, new).replace(old.replace("&H", "&H00", 1)[:-1], new.replace("&H", "&H00", 1)[:-1])
    ass.write_text(ass_text, encoding="utf-8")

    fps_value = eval_fps(fps)
    vignette = vignette_png(work_dir / "vignette.png", float(settings.get('bottom_shade', 0)) / 100,
                            float((settings.get('grade') or {}).get('vignette', 50)) / 100)
    logo = settings.get("outro_logo") or {}
    if on_stage: on_stage('rendering outro', 'در حال آماده‌سازی صفحهٔ پایانی و لوگو')
    outro, outro_seconds = render_outro(work_dir, cta.strip(), fps, fonts,
                                        logo_enabled=logo.get("enabled", True),
                                        logo_motion=logo.get("motion", "pop"), logo_path=logo_path)
    total = plan.duration + outro_seconds
    n = len(plan.shots)
    source_colour = source_colour_filter(video)
    # Open each edit as an independently seeked input. A single decoded input
    # followed by split+trim must scan and buffer everything before a hook
    # taken from late in the source; that produced no output/progress for many
    # minutes. Seeked inputs let concat emit the first shot immediately.
    inputs: list[str] = []
    clips = []
    elapsed = 0.0
    vf: list[str] = []
    grade_settings = settings.get("grade") or {}
    brightness = 1 + float(grade_settings.get("brightness", 0)) / 100
    contrast = float(grade_settings.get("contrast", 100)) / 100
    custom_grade = (f"lutyuv=y='val*{brightness:.3f}',"
                    f"eq=contrast={contrast:.3f}:"
                    f"saturation={float(grade_settings.get('saturation', 100)) / 100:.3f},"
                    f"colorbalance=rs={float(grade_settings.get('temperature', 0)) / 500:.3f}:"
                    f"bs={-float(grade_settings.get('temperature', 0)) / 500:.3f}")
    if grade_settings.get("auto", True):
        look_path = work_dir / "auto_look.json"
        try:
            auto_stats = json.loads(look_path.read_text())
        except (OSError, ValueError):
            auto_stats = measure_look(video, source_colour)
            if auto_stats:
                look_path.write_text(json.dumps(auto_stats))
        auto_filter = auto_grade_filter(auto_look(auto_stats))
        if auto_filter != "null":
            custom_grade = auto_filter + "," + custom_grade
    zoom_settings = settings.get("zoom") or {}
    zoom_amount = float(zoom_settings.get("amount", 100)) / 100 if zoom_settings.get("enabled", True) else 0.0
    base_zoom = float(zoom_settings.get("base_scale", 100)) / 100 if zoom_settings.get("enabled", True) else 1.0
    close_zoom = float(zoom_settings.get("close_scale", 125)) / 100 if zoom_settings.get("enabled", True) else 1.0
    for k, shot in enumerate(plan.shots):
        inputs = ['-threads','1','-ss',f'{shot.src_in:.3f}','-t',f'{shot.length:.3f}','-i',str(video)]
        vf = []
        cw, ch, x, y = crop_for(
            shot, sw, sh, base_zoom=max(1.0, base_zoom), close_zoom=max(1.0, close_zoom), framing=settings.get("framing")
        )
        look = custom_grade + (f",{BW}" if shot.bw else "")
        if shot.push and zoom_amount > 0:
            # Slow eased push-in anchored on the face (Ken Burns), as a perspective warp with cubic interpolation: the window moves by
            # fractions of a pixel, so the picture glides.  (zoompan cuts its window at whole pixels: the picture stalled and jumped
            # every few frames, which read as shaking on every zoom; measured, frame-to-frame change was 5x more uneven.)
            frames = max(1, round(shot.length * fps_value))
            ax = min(max((shot.face[0] * sw - x) / cw, 0.2), 0.8)
            ay = min(max((shot.face[1] * sh - y) / ch, 0.2), 0.8)
            z = f"(1+{PUSH_ZOOM * zoom_amount:.4f}*(1-cos(PI*min(in/{frames},1)))/2)"
            left, top = f"({ax:.4f}*W*(1-1/{z}))", f"({ay:.4f}*H*(1-1/{z}))"
            zoom = (f"scale={W}:{H}:flags=lanczos,"
                    f"perspective=x0='{left}':y0='{top}':x1='{left}+W/{z}':y1='{top}':x2='{left}':y2='{top}+H/{z}':x3='{left}+W/{z}':y3='{top}+H/{z}'"
                    f":sense=source:eval=frame:interpolation=cubic")
            # Decimate the phone source to the delivery cadence before the warp: it counts input frames, and a 60fps input would run it twice as fast.
            frame = f"fps={fps},{zoom}"
        else:
            frame = f"scale={W}:{H}:flags=lanczos,fps={fps}"
        vf.append(f"[0:v]setpts=PTS-STARTPTS,"
                  f"crop={cw}:{ch}:{x}:{y},{source_colour},{frame},setsar=1,{look}[v{k}]")
        fade = min(0.012, shot.length / 4)
        vf.append(f"[0:a]asetpts=PTS-STARTPTS,"
                  f"afade=t=in:d={fade:.3f},afade=t=out:st={shot.length - fade:.3f}:d={fade:.3f}[a{k}]")
        length = max(1, round((elapsed+shot.length)*fps_value)-round(elapsed*fps_value))/fps_value
        if on_stage: on_stage('rendering shot', f'در حال رندر بخش {k + 1} از {len(plan.shots)}؛ کادر، رنگ و حرکت گوینده')
        clips.append((cached_shot(inputs,vf,k,length,work_dir),length)); elapsed += shot.length
        if on_progress: on_progress(min(60,10+round(elapsed/max(plan.duration,.001)*50)))
    if on_stage: on_stage('rendering composition', 'در حال ترکیب بخش‌های تدوین، زیرنویس و صدا و رمزگذاری خروجی')
    inputs = shot_concat(clips,work_dir)
    vf = ['[0:v]setpts=PTS-STARTPTS[cv]','[0:a]asetpts=PTS-STARTPTS[ca]']
    n = 1
    vf.append(f"[{n}:v]format=rgba[vig]")
    content = "vmain" if outro else "vout"
    windows = "+".join(f"between(t,{n['start']:.3f},{n['end']:.3f})" for n in plan.notes)
    emphasis = (f"gblur=sigma=9:enable='{windows}',hue=s=0:enable='{windows}',"
                f"eq=brightness=-0.07:contrast=1.05:enable='{windows}'," if windows else "")
    vf.append(f"[cv]{emphasis}null[cvx]")
    if overlay:
        vf.append(f"[cvx][vig]overlay=0:0:format=yuv420:shortest=1,{subtitles_filter(ass, fonts)},format=yuv420p[vbase]")
        vf.append(f"[{n + 1}:v]format=yuva420p,setpts=PTS-STARTPTS[tso]")
        vf.append(f"[vbase][tso]overlay=0:0:format=yuv420:eof_action=pass,format=yuv420p[{content}]")
    else:
        vf.append(f"[cvx][vig]overlay=0:0:format=yuv420:shortest=1,{subtitles_filter(ass, fonts)},"
                  f"format=yuv420p[{content}]")
    inputs += ["-threads", "1", "-loop", "1", "-framerate", "1", "-i", str(vignette)]
    next_input = n + 1
    if overlay:
        inputs += ["-c:v", "libvpx-vp9", "-i", str(overlay)]
        next_input += 1
    if outro:
        inputs += ["-i", str(outro)]
        vf.append(f"[{next_input}:v]setsar=1,format=yuv420p[vend]")
        vf.append("[vmain][vend]concat=n=2:v=1:a=0[vout]")
        next_input += 1
    # The voice ends with the talk; the outro carries only the music.
    vf.append(f"[ca]apad=pad_dur={outro_seconds + 0.1:.3f}[cpad]")
    if music and music.is_file():
        bed = music_bed(music, total + 1.0, work_dir)
        inputs += ["-i", str(bed)]
        from engine import music_mix
        mix = music_mix.resolve("talking_1", render_settings)
        vf.append(mix.bed(next_input, total))
        vf.extend(mix.graph("loudnorm=I=-16:TP=-1:LRA=9,aresample=48000[aout]"))
    else:
        # loudnorm internally upsamples.  With the source's 44.1kHz AAC and
        # this FFmpeg build, normalising before fixing the input rate changes
        # timestamps (a 5s shot became 3.32s of audio).  Establish a 48kHz
        # clock first so picture and sound keep identical duration.
        vf.append("[cpad]aresample=48000,loudnorm=I=-16:TP=-1:LRA=9,"
                  "aresample=48000[aout]")
    cmd = [ffmpeg, "-hide_banner", "-y", "-filter_complex_threads", "2", "-filter_threads", "2", *inputs, "-filter_complex", ";".join(vf),
           "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-threads", "2", "-crf", "17", "-preset", "ultrafast",
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
                try: on_progress(min(99, 60+int(int(row.split("=")[1]) / 1e6 / total * 39)))
                except ValueError: pass
    except BaseException:
        proc.terminate(); proc.wait(timeout=5); out.unlink(missing_ok=True); raise
    if proc.wait() != 0:
        detail = 'process killed (SIGKILL); check container memory/OOM limits' if proc.returncode == -9 else ffmpeg_error(''.join(log_tail))
        raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}): {detail}")
    if on_stage: on_stage('rendering finalizing', 'فایل رندر نوشته شد؛ در حال تحویل خروجی برای بررسی کیفیت')
    return out


# --- Tscaps layer for key moments (additive: without it the output is the built-in ASS rendering) -----------------

render_plain = render


def render(video: Path, plan: ReelPlan, out: Path, **kwargs) -> Path:  # noqa: F811
    """Emphasis phrases are drawn by the Tscaps engine; the pinned hook, name and Ray captions stay as they are."""
    if kwargs.get("overlay") is not None:
        return render_plain(video, plan, out, **kwargs)
    import dataclasses
    from engine import tscaps_overlay as tso
    if kwargs.get('on_stage'):
        kwargs['on_stage']('rendering captions', 'در حال رندر لایهٔ تایپوگرافی و تأکیدهای متنی')
    work_dir = kwargs.pop("work_dir")
    report = kwargs.get("on_progress")
    # The text layer is made first: its own percentage fills the first 8% of the render (the picture's work then continues from there), so this stage moves instead of sitting at 0.
    layer = (lambda pct: report(round(pct * 0.08))) if report else None
    return tso.render_with_overlay(lambda v, p, o, **k: render_plain(v, p, o, **kwargs, **k), video, plan, out, work_dir=work_dir,
                                   cues=tso.note_cues(plan.notes), strip=lambda p: p, fps=int(RENDER_FPS), duration=plan.duration, overlay_progress=layer)
