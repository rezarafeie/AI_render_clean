"""Narration that sounds like a person reading a script, not a list of sentences.

The engines used to ask ElevenLabs for every line on its own, cut every pause above 0.16 s down to 0.12 s and speed the result up 1.12-1.25x with a
time-stretch. Each line then started and ended with the same intonation, nobody breathed, and the stretch added a metallic edge. Here the whole script
(or a few lines at a time when it is long) is read in ONE take, so one sentence leads into the next; the take is cut into per-line clips at the real
gaps between lines (from the character timestamps), pauses are kept (only an unusually long one is shortened) and no speed-up is applied beyond an
optional, inaudible 1.0-1.06x. An optional delivery pass gives the reader direction (ElevenLabs v3 audio tags such as [warm], [curious], [serious]),
which are performed, not spoken, and never reach the word timings.

    clips = narrate(lines, voice, model, folder)      # [{"text", "path", "dur", "chars", "starts"}], one per line, in order
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)
MAX_CHARS = 2200            # one take reads at most this much (a long film is read in a few takes, cut between lines)
LEAD_IN, TAIL_OUT = 0.06, 0.16   # what a clip keeps before the line's first sound and after its last
LONG_PAUSE, KEEP_PAUSE = 0.75, 0.42   # a pause inside a line longer than LONG_PAUSE is shortened to KEEP_PAUSE; shorter ones are the reader's own
def mode() -> str:
    """NARRATION_MODE: lines (each sentence on its own, the old chain) | take (one take, natural pauses) | directed (one take + delivery direction)."""
    import os
    value = os.environ.get("NARRATION_MODE", "lines").strip().lower()
    return value if value in {"lines", "take", "directed"} else "lines"


TAG = re.compile(r"\[[a-zA-Z][a-zA-Z \-']{1,30}\]\s*")


def _groups(lines: list[str]) -> list[list[int]]:
    out, size = [[]], 0
    for i, line in enumerate(lines):
        if out[-1] and size + len(line) > MAX_CHARS:
            out.append([])
            size = 0
        out[-1].append(i)
        size += len(line) + 1
    return out


def _decode(path: Path, out: Path, start: float, end: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, start):.3f}", "-to", f"{end:.3f}", "-i", str(path), "-ar", "48000", "-ac", "1",
                    "-af", "afade=t=in:d=0.006,areverse,afade=t=in:d=0.012,areverse", "-c:a", "pcm_s16le", str(out)], check=True)


def _pauses(wav: Path) -> list[tuple[float, float]]:
    text = subprocess.run(["ffmpeg", "-i", str(wav), "-af", f"silencedetect=n=-42dB:d={LONG_PAUSE}", "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", text)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", text)]
    return list(zip(starts, ends))


def _shorten(wav: Path, out: Path, tempo: float) -> list[tuple[float, float]]:
    """Long pauses inside the line shortened, then the optional tempo: returns the kept segments (seconds of `wav`) for re-timing the characters."""
    import numpy as np
    import wave
    with wave.open(str(wav)) as w:
        rate = w.getframerate()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    dur = len(samples) / rate
    kept, cursor = [], 0.0
    for s, e in _pauses(wav):
        if s <= 0.05 or e >= dur - 0.05:
            continue
        cut_from, cut_to = s + KEEP_PAUSE / 2, e - KEEP_PAUSE / 2
        if cut_to > cut_from:
            kept.append((cursor, cut_from))
            cursor = cut_to
    kept.append((cursor, dur))
    joined = np.concatenate([samples[int(a * rate):int(b * rate)] for a, b in kept if b > a])
    tmp = out.with_name(out.stem + "_k.wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(joined.astype(np.int16).tobytes())
    chain = f"atempo={tempo:.3f}," if abs(tempo - 1.0) > 0.005 else ""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-af", chain + "highpass=f=70", "-ar", "48000", "-ac", "2", str(out)], check=True)
    tmp.unlink(missing_ok=True)
    return kept


def _remap(x: float, kept: list[tuple[float, float]], tempo: float) -> float:
    offset = 0.0
    for a, b in kept:
        if x < a:
            return offset / tempo
        if x <= b:
            return (offset + x - a) / tempo
        offset += b - a
    return offset / tempo


def narrate(lines: list[str], voice: str, model: str, folder: Path, *, tags: list[str] | None = None, tempo: float = 1.0, on_line=None) -> list[dict]:
    """Per-line clips cut from whole takes. Each clip: {"text": the line's spoken characters, "path": wav, "dur", "chars": [...], "starts": [seconds in the clip]}."""
    from creative import claude_motion as cm
    folder.mkdir(parents=True, exist_ok=True)
    tempo = max(1.0, min(1.06, float(tempo or 1.0)))
    tags = tags or [""] * len(lines)
    out: list[dict | None] = [None] * len(lines)
    for g, group in enumerate(_groups(lines)):
        parts, spans, cursor = [], [], 0
        for i in group:
            lead = (f"[{tags[i].strip('[] ')}] " if tags[i] and tags[i].strip("[] ") else "")
            parts.append(lead + lines[i])
            spans.append((i, cursor + len(lead), cursor + len(lead) + len(lines[i])))
            cursor += len(lead) + len(lines[i]) + 1
        script = "\n".join(parts)
        take, alignment = cm._retrying(lambda: cm._tts(script, voice, model, folder, f"take{g:02d}"), tries=3, waits=(10, 25))
        chars = alignment["characters"]
        starts = alignment["character_start_times_seconds"]
        ends = alignment["character_end_times_seconds"]
        total = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(take)]).strip() or 0)
        if len(chars) != len(script):
            log.warning("alignment length %d differs from the script's %d; positions are matched by order", len(chars), len(script))
        bounds = []
        for i, a, b in spans:
            idx = [k for k in range(a, min(b, len(chars))) if chars[k].strip()]
            if not idx:
                bounds.append((i, a, b, 0.0, 0.0))
                continue
            bounds.append((i, a, b, starts[idx[0]], ends[idx[-1]]))
        for n, (i, a, b, first, last) in enumerate(bounds):
            prev_last = bounds[n - 1][4] if n else 0.0
            next_first = bounds[n + 1][3] if n + 1 < len(bounds) else total
            clip_from = max((prev_last + first) / 2 if n else 0.0, first - LEAD_IN)
            clip_to = min((last + next_first) / 2 if n + 1 < len(bounds) else total, last + TAIL_OUT)
            raw = folder / f"line{i + 1:02d}_raw.wav"
            final = folder / f"line{i + 1:02d}.wav"
            _decode(take, raw, clip_from, clip_to)
            kept = _shorten(raw, final, tempo)
            raw.unlink(missing_ok=True)
            dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(final)]).strip() or 0)
            line_chars = chars[a:b]
            line_starts = [round(_remap(max(0.0, t - clip_from), kept, tempo), 3) for t in starts[a:b]]
            out[i] = {"text": "".join(line_chars), "path": str(final), "dur": round(dur, 3), "chars": line_chars, "starts": line_starts, "take": str(take)}
            if on_line:
                on_line(i + 1, len(lines))
    return [o for o in out if o is not None]


DIRECTION = """You direct a Persian voice actor reading a short film's narration (ElevenLabs v3). For each line give AT MOST one delivery tag in English that the
reader performs (it is not spoken), or "" for a plain read. Use them sparingly - most lines get "" - and only where the film's meaning needs a shift:
[warm], [curious], [serious], [excited], [thoughtful], [confident], [softly], [emphatic], [amused], [pause]. A hook may be [curious] or [emphatic], a
turn [serious], a lesson [warm] or [thoughtful], a joke [amused]. Never two strong tags in a row. Return strict JSON {"tags": ["...", ...]} with exactly one
entry per line."""


def direct(lines: list[str], route: str) -> list[str]:
    """Sparse v3 delivery tags for the lines; plain reads when the model is unavailable."""
    from pydantic import BaseModel, ConfigDict, Field
    from creative import llm

    class Tags(BaseModel):
        model_config = ConfigDict(extra="ignore")
        tags: list[str] = Field(default_factory=list)

    try:
        got = llm.ask(Tags, DIRECTION, json.dumps(lines, ensure_ascii=False), route=route, tokens=1200, attempts=2).tags
    except Exception:
        log.warning("voice direction unavailable; plain reads", exc_info=True)
        return [""] * len(lines)
    allowed = {"warm", "curious", "serious", "excited", "thoughtful", "confident", "softly", "emphatic", "amused", "pause"}
    clean = [(t or "").strip().strip("[]").strip().lower() for t in got[:len(lines)]]
    return [t if t in allowed else "" for t in clean] + [""] * (len(lines) - len(clean))
