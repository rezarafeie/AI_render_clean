"""The sound of a Vox film (VOX_ENGINE_SPEC.md §8): a curious documentary underscore ducked under the narration, and a paper sound for every visual event.

The effects are read from the scene code itself: every primitive with an `at` (Stamp → stamp, Type/Counter → typewriter, marks → marker, Flash → shutter,
Pin → pin, a picture sliding in → paper, a pop → pop) is placed at the second its cue resolves to, plus a paper swoosh at every scene change. So the sound
always matches what is on screen, with no second list for the model to keep in step.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
SFX = HERE / "kit" / "sfx"
MUSIC = HERE / "kit" / "music.mp3"
PREMIUM_SFX = HERE.parent / "claude_premium" / "kit" / "sfx"
IN = 0.32

# the effects the reference film used that are not in the kit: made once with ElevenLabs sound generation (cached), else a close kit sound stands in
EXTRA = {"pop": ("short soft cartoon pop, paper cut-out popping onto a table", 0.4),
         "whoosh": ("soft airy whoosh transition, documentary", 0.8),
         "whoosh2": ("quick light whoosh of a paper plane passing", 0.6),
         "cashreg": ("vintage cash register ding with coins, short", 0.9),
         "sparkle": ("gentle sparkle chime ending sting, light", 1.2)}
STAND_IN = {"pop": PREMIUM_SFX / "tick.mp3", "whoosh": PREMIUM_SFX / "softwhoosh.mp3", "whoosh2": PREMIUM_SFX / "softwhoosh.mp3",
            "cashreg": PREMIUM_SFX / "chime.mp3", "sparkle": PREMIUM_SFX / "shimmer.mp3"}

# primitive → (effect, volume); volumes stay between 0.25 and 0.6: the effects sit UNDER the voice
BY_TAG = {"Stamp": ("stamp", 0.55), "Type": ("typewriter", 0.3), "Counter": ("typewriter", 0.3), "XMark": ("marker", 0.4), "CheckMark": ("marker", 0.4),
          "CircleMark": ("marker", 0.42), "Underline": ("marker", 0.35), "Arrow": ("marker", 0.32), "HeartMark": ("marker", 0.38), "Marker": ("marker", 0.32),
          "Flash": ("shutter", 0.55), "Pin": ("pin", 0.45)}
ENTER = {"pop": ("pop", 0.38), "drop": ("paper2", 0.45), "left": ("paper", 0.32), "right": ("paper", 0.32), "up": ("paper2", 0.3), "down": ("paper2", 0.3)}


def _cache() -> Path:
    shared = HERE.parents[1] / "assets" / "models"
    if shared.is_dir() and os.access(shared, os.W_OK):
        return shared / "vox" / "sfx"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "editorgpt" / "vox" / "sfx"


def effect(name: str) -> Path | None:
    """The file of an effect: the kit's, else the cached generated one (made now if possible), else a stand-in."""
    path = SFX / f"{name}.mp3"
    if path.is_file():
        return path
    cached = _cache() / f"{name}.mp3"
    if cached.is_file() and cached.stat().st_size > 1000:
        return cached
    if name in EXTRA:
        try:
            import httpx
            from brain.elevenlabs_transport import url as elevenlabs_url, api_key
            key = api_key()
            if key:
                text, seconds = EXTRA[name]
                response = httpx.post(elevenlabs_url("v1/sound-generation"), params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": key},
                                      json={"text": text, "duration_seconds": seconds, "prompt_influence": 0.6}, timeout=120)
                if response.status_code < 400 and len(response.content) > 1000:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_bytes(response.content)
                    return cached
        except Exception as exc:
            log.warning("vox effect %s could not be generated: %s", name, str(exc)[:120])
    stand = STAND_IN.get(name)
    return stand if stand and stand.is_file() else None


# ── reading the events out of the code ───────────────────────────────────────

_TAG = re.compile(r"<(Stamp|Type|Counter|XMark|CheckMark|CircleMark|Underline|Arrow|HeartMark|Marker|Flash|Pin|Enter)\b((?:[^<>{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)>", re.S)
_AT = re.compile(r"\bat=\{((?:[^{}]|\{[^{}]*\})*)\}")
_FROM = re.compile(r"\bfrom=[\"'{]+(\w+)")
_CUE = re.compile(r"\bc\(\s*(['\"])(.*?)\1\s*(?:,\s*(\d+)\s*)?\)")
_CONST = re.compile(r"\bconst\s+([A-Za-z_]\w*)\s*=\s*([^;\n]+);")
_SAFE = re.compile(r"^[\d\s.+\-*/()]+$")


def _norm(s: str) -> str:
    s = re.sub(r"[ً-ْـ‌‍]", "", s)
    return s.replace("ي", "ی").replace("ك", "ک")


def cue_time(scene: dict, word: str, occ: int = 0) -> float:
    """The scene-relative second (from the scene's start) at which `word` is heard: the same matching as the kit's c()."""
    k = _norm(word)
    words = [(_norm(w["t"]), float(w["s"])) for w in scene.get("words", [])]
    match = [s for n, s in words if n == k] or [s for n, s in words if n.startswith(k) or (len(k) > 2 and k.startswith(n) and len(n) > 1)] or [s for n, s in words if k in n]
    if not match:
        return 0.0
    return match[occ] if occ < len(match) else match[-1]


def _evaluate(expr: str, scene: dict, consts: dict[str, str], depth: int = 0) -> float | None:
    """A scene time expression (c('word') - 0.1, a number, a const defined from those, dur - 2) in seconds from the scene start; None when it is not that simple."""
    text = expr.strip()
    if depth > 3:
        return None
    off = float(scene.get("_off", 0.0))                                     # the kit's c() counts from the scene's own clock, which starts IN early
    text = _CUE.sub(lambda m: f"({cue_time(scene, m.group(2), int(m.group(3) or 0)) + off:.3f})", text)
    text = re.sub(r"\bdur\b", f"({float(scene.get('_span', scene.get('dur', 0))):.3f})", text)
    for name in re.findall(r"\b[A-Za-z_]\w*\b", text):
        if name in consts:
            value = _evaluate(consts[name], scene, consts, depth + 1)
            if value is None:
                return None
            text = re.sub(rf"\b{name}\b", f"({value:.3f})", text)
    text = re.sub(r"Math\.max\(([^,()]+),([^()]+)\)", lambda m: f"max({m.group(1)},{m.group(2)})", text)
    if not _SAFE.match(text.replace("max", "").replace(",", "")):
        return None
    try:
        return float(eval(text, {"__builtins__": {}}, {"max": max}))       # only digits, operators and max() are left
    except Exception:
        return None


def events(scenes_code: str, timeline: dict) -> list[tuple[float, str, float]]:
    """(absolute second, effect, volume) of every visual event of the film, plus the scene changes and the ending sparkle."""
    out: list[tuple[float, str, float]] = []
    scenes = timeline["scenes"]
    for i, scene in enumerate(scenes):
        body = re.search(rf"\bconst\s+S{scene['id']}\b.*?(?=\bconst\s+S\d\d\s*:|\bexport\s+const\s+SCENES\b|\Z)", scenes_code, re.S)
        start = float(scene["start"]) - (IN if i else 0.0)                   # where the scene's own clock starts on the film's clock
        scene = {**scene, "_off": float(scene["start"]) - start, "_span": float(scene.get("end", scene["start"] + scene.get("dur", 0))) - start}
        if i:
            out.append((float(scene["start"]) - IN, "whoosh" if scene.get("type") in {"big_term", "growth_chart"} else ("paper" if i % 2 else "paper2"), 0.42))
        if not body:
            continue
        code = body.group(0)
        consts = {m.group(1): m.group(2) for m in _CONST.finditer(code)}
        for tag in _TAG.finditer(code):
            name, attrs = tag.group(1), tag.group(2)
            at = _AT.search(attrs)
            if not at:
                continue
            seconds = _evaluate(at.group(1), scene, consts)
            if seconds is None or seconds < 0 or seconds > scene["_span"] + 0.2:
                continue
            if name == "Enter":
                kind = (_FROM.search(attrs).group(1) if _FROM.search(attrs) else "pop")
                if kind not in ENTER or (seconds < 0.12 and i):                 # elements already there when the page slides in make no separate sound
                    continue
                fx, volume = ENTER[kind]
            else:
                fx, volume = BY_TAG[name]
            out.append((start + seconds, fx, volume))
            if name == "XMark":
                out.append((start + seconds + 0.12, "marker", volume * 0.8))
            if name == "Counter" and re.search(r"prefix=\{?['\"]\$", attrs):
                out.append((start + seconds + 0.6, "cashreg", 0.32))
    out.append((max(0.0, float(timeline["total"]) - 1.6), "sparkle", 0.3))
    out.sort()
    thinned: list[tuple[float, str, float]] = []
    for t, fx, volume in out:                                               # the same sound twice within 0.15 s is one sound
        if any(abs(t - t2) < 0.15 and fx == f2 for t2, f2, _ in thinned[-6:]):
            continue
        thinned.append((round(t, 3), fx, round(volume, 2)))
    return thinned


# ── music + mix ──────────────────────────────────────────────────────────────

def music(total: float, out: Path) -> Path | None:
    """The kit's documentary underscore at the film's length (looped with a crossfade when the film is longer)."""
    if not MUSIC.is_file():
        return None
    length = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(MUSIC)]).strip() or 0)
    out.parent.mkdir(parents=True, exist_ok=True)
    if length >= total + 1:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(MUSIC), "-t", f"{total:.2f}", "-ar", "48000", "-ac", "2", str(out)], check=True)
    else:
        loops = int(total // max(length - 3, 1)) + 1
        inputs, chain = [], ""
        for k in range(loops + 1):
            inputs += ["-i", str(MUSIC)]
        label = "[0:a]"
        for k in range(1, loops + 1):
            chain += f"{label}[{k}:a]acrossfade=d=3:c1=tri:c2=tri[x{k}];"
            label = f"[x{k}]"
        chain += f"{label}atrim=0:{total:.2f}[m]"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", chain, "-map", "[m]", "-ar", "48000", "-ac", "2", str(out)], check=True)
    return out


def mix(voice: list[dict], cues: list[tuple[float, str, float]], total: float, out: Path) -> Path:
    """voice: amix → highpass 70 → compressor → [voice][sidechain]; music 0.26 ducked; effects; limiter → loudnorm -14 LUFS (mix.py of the reference film)."""
    inputs: list[str] = []
    fc: list[str] = []
    n = 0
    fx_labels = []
    files: dict[str, Path | None] = {}
    for t, name, volume in cues:
        if name not in files:
            files[name] = effect(name)
        path = files[name]
        if not path:
            continue
        inputs += ["-i", str(path)]
        ms = int(max(0.0, t) * 1000)
        fc.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={volume:.2f},adelay={ms}|{ms}[f{n}]")
        fx_labels.append(f"[f{n}]")
        n += 1
    voice_labels = []
    for clip in voice:
        inputs += ["-i", str(clip["path"])]
        ms = int(float(clip["start"]) * 1000)
        fc.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[v{n}]")
        voice_labels.append(f"[v{n}]")
        n += 1
    fc.append("".join(voice_labels) + f"amix=inputs={len(voice_labels)}:normalize=0,highpass=f=70,acompressor=threshold=-18dB:ratio=3:attack=4:release=100:makeup=3,"
              f"apad=whole_dur={total:.2f},asplit=2[voice][sc]")
    bed = music(total, out.with_name("music.wav"))
    parts = ["[voice]"]
    if bed:
        inputs += ["-i", str(bed)]
        fc.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total:.2f},volume=0.26,afade=t=in:d=0.5,afade=t=out:st={max(0.0, total - 2.5):.2f}:d=2.5[mus0]")
        fc.append("[mus0][sc]sidechaincompress=threshold=0.04:ratio=4:attack=20:release=350[mus]")
        parts.append("[mus]")
        n += 1
    else:
        fc.append("[sc]anullsink")
    if fx_labels:
        fc.append("".join(fx_labels) + f"amix=inputs={len(fx_labels)}:normalize=0[fx]")
        parts.append("[fx]")
    fc.append("".join(parts) + f"amix=inputs={len(parts)}:normalize=0,atrim=0:{total:.2f},alimiter=limit=0.95,loudnorm=I=-14:TP=-1.2:LRA=9[out]")
    script = out.with_suffix(".fc.txt")
    script.write_text(";\n".join(fc))
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex_script", str(script), "-map", "[out]", "-ar", "48000", "-ac", "2", str(out)], check=True)
    return out


if __name__ == "__main__":
    import sys
    print(json.dumps(events(Path(sys.argv[1]).read_text(), json.loads(Path(sys.argv[2]).read_text())), ensure_ascii=False))
