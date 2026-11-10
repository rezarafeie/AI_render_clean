"""The music director: what music a film needs, where it comes from, and the emotional shape it follows.

One decision per film, in this order (cheapest and most certain first; each step is skipped when it cannot apply and every skip is reported, never silent):

  1. a track the person attached
  2. music generated earlier for a close-enough request (cache; free)
  3. the studio's licensed library, ranked by what the film needs, with the measured energy of the best candidates
  4. an authorised external catalogue (Jamendo, Epidemic Sound) when configured
  5. new music from a generator (ElevenLabs Eleven Music, then Stable Audio) when configured, the daily cap allows it and the cost preference permits
  6. the best library track even if it fits poorly, with the reason, rather than a film without music (only when nothing above produced a usable track)

Deterministic rules decide; no model is asked anything here. The text sent to a generator is built from the film's own brief, tone, duration and emotional arc.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import music_providers as providers
from . import music_select, rhythm

log = logging.getLogger(__name__)

STYLES: dict[str, dict] = {
    "cinematic": {"words": "cinematic, hybrid orchestral, wide and emotional, slow build to a big finish", "bpm": (70, 100)},
    "energetic": {"words": "energetic, driving four-on-the-floor beat, punchy drums, bright synths, confident", "bpm": (120, 140)},
    "inspirational": {"words": "inspirational, uplifting piano and strings, hopeful, gradually rising", "bpm": (90, 115)},
    "educational": {"words": "light and neutral, unobtrusive soft pulse, curious, clean", "bpm": (80, 105)},
    "luxury": {"words": "luxury, elegant, deep bass, sparse and sophisticated", "bpm": (80, 110)},
    "minimal": {"words": "minimal, ambient, sparse soft textures, very calm", "bpm": (60, 90)},
    "dramatic": {"words": "dramatic, tense, percussive hits, rising tension and release", "bpm": (80, 120)},
    "relaxed": {"words": "relaxed, warm, mellow lo-fi groove", "bpm": (70, 95)},
    "commercial": {"words": "modern commercial, upbeat electronic pop, bright and confident", "bpm": (100, 125)},
}
_STYLE_PATTERNS = [
    ("luxury", r"luxur|premium|elegant|لوکس|لاکچری|برند\s*گرانقیمت"),
    ("cinematic", r"cinematic|epic|trailer|teaser|سینمایی|تیزر"),
    ("dramatic", r"dramatic|tension|thriller|دراماتیک|هیجان‌?انگیز"),
    ("inspirational", r"inspir|motivat|uplift|الهام|انگیزشی|امیدوار"),
    ("educational", r"educat|tutorial|explain|how to|آموزش|توضیح|توضیحی"),
    ("minimal", r"minimal|ambient|مینیمال|ساده\s*و\s*آرام"),
    ("relaxed", r"relax|calm|chill|lo-?fi|آرام|ریلکس"),
    ("energetic", r"energetic|high[- ]energy|hype|fast|upbeat|پرانرژی|پر\s*انرژی|هیجانی|شاد"),
    ("commercial", r"promo|promotional|advert|\bad\b|commercial|launch|sale|offer|پروموشن|تبلیغ|فروش|معرفی|رونمایی|تخفیف"),
]
# (end as a fraction of the film, label, energy 0..1): the shape each style follows. A moment that must carry the accent (the reveal) is placed on top of it.
_ARCS = {
    "energetic": [(0.12, "attention-grabbing opening", 0.8), (0.5, "rising energy", 0.65), (1.0, "peak and call to action", 0.9)],
    "commercial": [(0.12, "hook", 0.7), (0.55, "build", 0.6), (1.0, "payoff and call to action", 0.85)],
    "cinematic": [(0.2, "quiet opening", 0.25), (0.65, "slow build", 0.5), (1.0, "climax", 0.9)],
    "dramatic": [(0.15, "tense opening", 0.4), (0.6, "mounting tension", 0.65), (1.0, "release", 0.95)],
    "inspirational": [(0.2, "gentle start", 0.3), (0.65, "growing hope", 0.55), (1.0, "uplifting finish", 0.85)],
    "educational": [(1.0, "steady, unobtrusive bed", 0.3)],
    "luxury": [(0.3, "sparse opening", 0.3), (1.0, "elegant, slowly widening", 0.5)],
    "minimal": [(1.0, "soft bed", 0.2)],
    "relaxed": [(1.0, "warm, even groove", 0.35)],
}


@dataclass
class MusicRequest:
    brief: str = ""
    words: str = ""                      # the person's own words about the music (mood, genre, instruments)
    duration_s: float = 30.0
    mode: str = "auto"                   # auto | library | search | generate | attached
    style: str = ""                      # one of STYLES; empty = chosen from the brief
    energy: float | None = None          # 0..1
    instrumental: bool = True
    accent_s: float | None = None        # the film's moment for the music's strongest accent
    cost: str = "balanced"               # free (never pay) | balanced | premium (prefer fresh generated music)
    path: str = ""                       # an attached track
    name: str = ""
    user: str = ""
    genre: str = ""
    instruments: str = ""
    bpm: tuple[int, int] | None = None
    variant: int = 0                     # 0 = the first take; a higher number asks for another (a different seed, and the tracks in `exclude` are not chosen again)
    exclude: list[str] = field(default_factory=list)
    strict: bool = False                 # an inferred wish (not asked for in words): only a good match counts, never a weak fallback or a paid generation


@dataclass
class Result:
    path: Path | None = None
    label: str = ""
    source: str = ""                     # attached | cache | library | search | generated | fallback
    track: dict | None = None
    notes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    attribution: str | None = None
    cost: dict | None = None
    style: str = ""
    arc: list[dict] = field(default_factory=list)


def pick_style(text: str, energy: float | None = None) -> str:
    for style, pattern in _STYLE_PATTERNS:
        if re.search(pattern, text or "", re.I):
            return style
    if energy is not None:
        return "energetic" if energy >= 0.75 else "commercial" if energy >= 0.55 else "relaxed" if energy <= 0.3 else "educational"
    return "commercial"


def emotional_arc(duration_s: float, style: str, accent_s: float | None = None) -> list[dict]:
    """How the music should move over the film. The shape follows the style; the accent (when the film has one) opens its own climax section so the
    strongest moment of the music is where the film's strongest moment is. Sections are measured in seconds and tile the film exactly."""
    duration_s = float(duration_s)
    template = _ARCS.get(style) or _ARCS["commercial"]
    sections, start = [], 0.0
    for end_fraction, label, energy in template:
        end = round(duration_s * end_fraction, 2)
        if end - start >= 0.5:
            sections.append({"start_s": round(start, 2), "end_s": end, "label": label, "energy": energy})
            start = end
    if sections:
        sections[-1]["end_s"] = round(duration_s, 2)
    if accent_s and 1.0 < accent_s < duration_s - 0.5 and style not in {"educational", "minimal", "relaxed"}:
        cut: list[dict] = []
        for section in sections:
            if section["end_s"] <= accent_s:
                cut.append(section)
            elif section["start_s"] < accent_s:
                cut.append({**section, "end_s": round(accent_s, 2)})
        cut.append({"start_s": round(accent_s, 2), "end_s": round(duration_s, 2), "label": "the reveal: the strongest moment of the music", "energy": 1.0})
        sections = cut
    return sections


def target_bpm(style: str, energy: float | None) -> tuple[int, int]:
    low, high = STYLES.get(style, STYLES["commercial"])["bpm"]
    if energy is None:
        return low, high
    centre = low + (high - low) * max(0.0, min(1.0, energy))
    return int(round(centre - 8)), int(round(centre + 8))


def build_prompt(request: MusicRequest, style: str, arc: list[dict]) -> str:
    """The description sent to a generator: style, tempo, whether there are vocals, the film's emotional shape section by section. English works best for these models."""
    spec = STYLES.get(style, STYLES["commercial"])
    low, high = request.bpm or target_bpm(style, request.energy)
    parts = [spec["words"]]
    if request.genre:
        parts.append(request.genre)
    if request.instruments:
        parts.append(f"featuring {request.instruments}")
    if request.words and re.search(r"[A-Za-z]", request.words):
        parts.append(request.words)
    parts.append(f"{low}-{high} BPM, steady pulse, clean loop-friendly mix, no spoken words")
    parts.append("instrumental, no vocals" if request.instrumental else "vocals allowed")
    if len(arc) > 1:
        parts.append("Structure: " + "; ".join(f"{s['start_s']:g}-{s['end_s']:g}s {s['label']} (energy {int(s['energy'] * 100)}%)" for s in arc))
    return ". ".join(parts)[:3500]


# ── candidates ───────────────────────────────────────────────────────────────────────────────────────────────────
def analysis_dir() -> Path:
    folder = providers.store_root() / "analysis"
    folder.mkdir(exist_ok=True)
    return folder


def analysis_for(path: Path) -> dict | None:
    """The rhythm of a track, from the content-keyed cache when it was analysed before. None when the file cannot be analysed (short, silent, unreadable)."""
    try:
        return rhythm.analyse(Path(path), cache_dir=analysis_dir())
    except Exception as exc:
        log.info("rhythm of %s not available: %s", Path(path).name, str(exc)[:120])
        return None


def _energy_of(analysis: dict | None) -> float | None:
    values = [v for v in (analysis or {}).get("energy") or [] if v > 0]
    return float(sorted(values)[len(values) // 2]) if values else None


def library_tracks() -> list[dict]:
    from engine import library
    return [{"path": asset.path, "filename": asset.filename, "tags": list(asset.tags or []), "mood": asset.mood, "duration_sec": asset.duration_sec, "source": "library"}
            for asset in library.scan_category("music") if Path(asset.path).is_file()]


def generated_before() -> list[dict]:
    """Tracks generated or downloaded earlier (free to reuse), shaped like library tracks so one ranking serves both."""
    import json
    out = []
    for meta in providers.store_root().glob("*/meta.json"):
        try:
            data = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        if data.get("source") in {"generated", "search"} and Path(data.get("path", "")).is_file():
            text = data.get("prompt") or data.get("title") or ""
            out.append({"path": data["path"], "filename": str(data.get("title") or text)[:80], "tags": sorted(music_select.words(text))[:20], "mood": "",
                        "duration_sec": data.get("seconds"), "source": "cache", "provider": data.get("provider"), "key": data.get("key"), "license": data.get("license")})
    return out


def _rank(request: MusicRequest, style: str, tracks: list[dict], arc: list[dict]) -> list[dict]:
    brief = " ".join(filter(None, [request.words, request.genre, request.instruments, STYLES[style]["words"], request.brief[:400]]))
    energy = request.energy if request.energy is not None else (sum(s["energy"] * (s["end_s"] - s["start_s"]) for s in arc) / max(1.0, request.duration_s) if arc else None)
    ranked = music_select.rank(brief, request.duration_s, tracks, energy=energy)
    top = ranked[:4]                                    # only the few best are measured: decoding a track costs seconds
    measured = {t["path"]: _energy_of(analysis_for(Path(t["path"]))) for t in top}
    return music_select.rank(brief, request.duration_s, tracks, energy=energy, measure=lambda t: measured.get(t["path"])) if any(v is not None for v in measured.values()) else ranked


SUITABLE = 3.0                                          # a score from the ranking below this is a weak match: new music is preferred when it can be had


def resolve(request: MusicRequest, *, progress: Callable[[str, str], None] | None = None, clients: dict | None = None) -> Result:
    """Choose or make the music. Never raises for an unavailable provider: it explains and moves on; it returns a Result with `path=None` only when nothing at all exists."""
    say = progress or (lambda text, state="active": None)
    style = request.style if request.style in STYLES else pick_style(" ".join([request.words, request.brief]), request.energy)
    arc = emotional_arc(request.duration_s, style, request.accent_s)
    result = Result(style=style, arc=arc)

    def finish(path, label, source, **extra) -> Result:
        result.path, result.label, result.source = Path(path), label, source
        for key, value in extra.items():
            setattr(result, key, value)
        return result

    if request.mode == "attached" and request.path and Path(request.path).is_file():
        return finish(request.path, request.name or Path(request.path).name, "attached", reasons=["the person attached this track"])
    if request.mode == "attached":
        result.notes.append("فایل موسیقی پیوست پیدا نشد؛ ویدیو بدون موسیقی ساخته می‌شود (برای موسیقی خودکار «Music: auto» بنویسید).")
        return result                       # the person chose a specific file: another track is never put in its place

    library = library_tracks()
    mode = request.mode
    # 2/3: earlier generations and the studio library. "generate" and "search" are explicit wishes for something new, so they skip this step (an identical earlier
    # generation is still reused by the generator's own cache); "premium" cost preference asks for fresh music over a reused one.
    if mode == "library" or (mode == "auto" and request.cost != "premium"):
        pool = library if mode == "library" else generated_before() + library
        pool = [t for t in pool if t["path"] not in set(request.exclude)]
        ranked = _rank(request, style, pool, arc) if pool else []
        best = ranked[0] if ranked else None
        if best and (best["score"] >= SUITABLE or (mode == "library" and not request.strict)):
            src = "cache" if best.get("source") == "cache" else "library"
            weak = best["score"] < SUITABLE
            note = (f"تطابق ضعیف بود ولی نزدیک‌ترین ترک کتابخانه استفاده شد: {best['filename']}" if weak
                    else f"موسیقی از {'موسیقی‌های قبلاً ساخته‌شده' if src == 'cache' else 'کتابخانهٔ موسیقی'} انتخاب شد: {best['filename']}")
            return finish(best["path"], best["filename"], src, track=best, reasons=best["reasons"], notes=[note], attribution=_attribution(best))
        if mode == "library":
            result.notes.append("در کتابخانهٔ موسیقی ترکی پیدا نشد؛ یک ترک در «Media library» آپلود کنید یا فایل صوتی پیوست کنید.")
            return result

    # 4: authorised external catalogues
    if mode in {"auto", "search"}:
        say("دارم در کتابخانه‌های موسیقی مجاز می‌گردم…")
        low, high = request.bpm or target_bpm(style, request.energy)
        found = providers.search(" ".join(filter(None, [request.words, request.genre, STYLES[style]["words"].split(",")[0]])), instrumental=request.instrumental or None,
                                 energy=request.energy, bpm=(low, high), min_s=max(20, request.duration_s * 0.6), limit=12, clients=clients)
        for skipped in found["skipped"]:
            result.notes.append(f"جست‌وجو در {skipped['provider']} انجام نشد: {skipped['reason']}")
        usable = [t for t in found["tracks"] if t["rights"]["ok"]]
        for track in found["tracks"]:
            if not track["rights"]["ok"]:
                result.reasons.append(f"{track['provider']}:{track['title']} رد شد: {track['rights']['reason']}")
        if usable:
            ranked = music_select.rank(request.words or STYLES[style]["words"], request.duration_s,
                                       [{**t, "filename": t["title"], "mood": " ".join(t.get("tags") or []), "duration_sec": t.get("duration_s")} for t in usable],
                                       energy=request.energy)
            for choice in ranked[:3]:
                try:
                    got = providers.fetch(choice)
                except providers.MusicError as exc:
                    result.notes.append(f"دانلود «{choice['title']}» ممکن نشد: {exc}")
                    continue
                return finish(got["path"], f"{choice['title']} — {choice['artist']}", "search", track=got, reasons=[*result.reasons, *choice["reasons"]], attribution=(got.get("license") or {}).get("attribution"),
                              notes=[*result.notes, f"موسیقی از {choice['provider']} انتخاب شد: {choice['title']}"])
        elif mode == "search" and not found["skipped"]:
            result.notes.append("موسیقی مجاز مناسبی در جست‌وجو پیدا نشد.")

    # 5: generation
    if mode in {"auto", "generate", "search"} and request.cost != "free" and not request.strict:
        prompt = build_prompt(request, style, arc)
        say("دارم موسیقی تازه می‌سازم…")
        try:
            track = providers.generate(prompt, max(3.0, request.duration_s + 2.0), instrumental=request.instrumental, user=request.user, seed=request.variant or None)
            providers.ensure_rights(track)
            return finish(track["path"], track["title"][:60], "generated", track=track, cost=track.get("cost"), attribution=None,
                          reasons=[f"generated with {track['provider']}" + (" (from cache)" if track.get("cache_hit") else "")],
                          notes=[*result.notes, f"موسیقی تازه با {track['provider']} ساخته شد" + (" (از کش، بدون هزینهٔ جدید)" if track.get("cache_hit") else "")])
        except providers.MusicError as exc:
            result.notes.append(f"ساخت موسیقی انجام نشد ({exc.code}): {exc}")
    elif mode in {"auto", "generate", "search"} and request.cost == "free":
        result.notes.append("ساخت موسیقی با هزینه خاموش است (ترجیح هزینه: رایگان).")

    # 6: never a film without music because a provider was down (not for an inferred wish: a weak match is worse than none)
    if request.strict:
        result.notes.append("موسیقی مناسبی پیدا نشد؛ ویدیو بدون موسیقی ساخته می‌شود.")
        return result
    pool = [t for t in generated_before() + library if t["path"] not in set(request.exclude)]
    if pool:
        ranked = _rank(request, style, pool, arc)
        best = ranked[0] if ranked else None
        if best:
            return finish(best["path"], best["filename"], "fallback", track=best, reasons=best["reasons"], attribution=_attribution(best),
                          notes=[*result.notes, f"موسیقی مناسب‌تری در دسترس نبود؛ نزدیک‌ترین ترک موجود استفاده شد: {best['filename']}"])
    result.notes.append("هیچ موسیقی در دسترس نبود؛ ویدیو بدون موسیقی ساخته می‌شود.")
    return result


def _attribution(track: dict) -> str | None:
    licence = track.get("license")
    return licence.get("attribution") if isinstance(licence, dict) else None


# ── sound effects ───────────────────────────────────────────────────────────────────────────────────────────────
SFX_FOR = {"impact": "hit", "click": "tick", "whoosh": "whoosh", "hit": "hit"}      # a cue's sound name -> the synthesised recipe of engine/sfx.py


def _peak_normalised(path: Path, target_db: float = -3.0) -> Path:
    """A copy of a synthesised sound brought to a known peak (the recipes of engine/sfx.py differ by 10 dB), so a cue's gain means the same thing for every sound."""
    out = path.with_name(path.stem + "-n.wav")
    if out.is_file():
        return out
    measured = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, timeout=30)
    found = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", measured.stderr)
    gain = target_db - float(found.group(1)) if found else 0.0
    done = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(path), "-af", f"volume={gain:.2f}dB", str(out)], capture_output=True, text=True, timeout=30)
    return out if done.returncode == 0 and out.is_file() else path


def sfx_library(folder: Path) -> list[dict]:
    """The studio's own synthesised sounds as a licensed library: generated in-process with ffmpeg, so there is no third-party audio and no licence question."""
    from engine import sfx
    made = sfx.ensure(folder, set(SFX_FOR.values()))
    items = []
    for sound, recipe in SFX_FOR.items():
        if recipe in made:
            items.append({"category": "sfx", "tags": [sound], "path": str(_peak_normalised(made[recipe])), "license": "synthesised in the studio (no third-party audio)", "source": "engine.sfx"})
    return items


def sfx_moments(scenes: list[dict], timing: dict | None, accent_s: float | None) -> list[dict]:
    """Where a sound would mean something: the cut into each scene after the first (transition), and the film's accent (reveal). Nothing else."""
    moments = [{"time_ms": int(round(float(s["start"]) * 1000)), "kind": "transition", "importance": 0.5} for s in scenes[1:]]
    if accent_s:
        moments.append({"time_ms": int(round(accent_s * 1000)), "kind": "reveal", "importance": 1.0})
    for drop in (timing or {}).get("drops_ms") or []:
        if accent_s is None or abs(drop - accent_s * 1000) > 800:
            moments.append({"time_ms": int(drop), "kind": "accent", "importance": 0.6})
    return moments


def render_sfx(cues: list[dict], duration_s: float, output: Path) -> Path | None:
    """The cues as one track exactly as long as the film (each sound placed with sample-accurate adelay, its own gain and short fades). None when no cue has a file."""
    ready = [c for c in cues if c.get("asset") and Path(str(c["asset"])).is_file()]
    if not ready:
        return None
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    parts, labels = [], []
    from .music_fit import _duration
    for index, cue in enumerate(ready):
        command += ["-i", str(cue["asset"])]
        delay = int(cue["time_ms"])
        length = _duration(Path(str(cue["asset"]))) or 0.6
        fade_out = min(max(0.02, cue.get("fade_out_ms", 120) / 1000), max(0.02, length / 2))
        parts.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,volume={cue.get('gain_db', -12)}dB,afade=t=in:d={max(0.002, cue.get('fade_in_ms', 5) / 1000):.3f},"
                     f"afade=t=out:st={max(0.0, length - fade_out):.3f}:d={fade_out:.3f},asetpts=PTS-STARTPTS,adelay={delay}|{delay}[c{index}]")
        labels.append(f"[c{index}]")
    parts.append("".join(labels) + f"amix=inputs={len(ready)}:normalize=0:duration=longest,apad=whole_dur={float(duration_s):.3f},atrim=0:{float(duration_s):.3f}[out]")
    done = subprocess.run(command + ["-filter_complex", ";".join(parts), "-map", "[out]", "-c:a", "pcm_s16le", str(output)], capture_output=True, text=True, timeout=120)
    if done.returncode != 0 or not output.is_file():
        log.warning("sound effects track not made: %s", (done.stderr or "")[-200:])
        return None
    return output


# ── what the person says about music, in plain words ─────────────────────────────────────────────────────────────
_WANT = re.compile(
    r"\b(?:with|add|find|get|generate|create|compose|choose|pick|use|include|need|want|suitable|matching|fitting|background|upbeat|energetic|calm|cinematic|epic|soft|ambient)\b[^.\n]{0,30}\b(?:music|soundtrack|bgm)\b"
    r"|\b(?:music|soundtrack|bgm)\b[^.\n]{0,15}\b(?:that|which|should|must|to match|to fit|for the|under)\b"
    r"|\b(?:beat[\s-]?sync|sync(?:ed|hroni[sz]ed)?\s+(?:to|with)\s+(?:the\s+)?(?:beat|music)|on the beat)\b"
    r"|موسیقی\s*(?:مناسب|پس‌?زمینه|پرانرژی|آرام|ملایم|شاد|سینمایی|بذار|بگذار|اضافه|بساز|پیدا)|(?:اضافه|بساز|پیدا|انتخاب)\s*(?:کن)?\s*(?:یک\s*)?موسیقی|با\s+(?:یک\s+)?موسیقی|روی\s*بیت|سینک\s*با\s*(?:بیت|موسیقی)", re.I)
_NO_MUSIC = re.compile(r"\b(?:no|without|mute|remove|turn off|drop)\s+(?:any\s+|the\s+)?(?:background\s+)?(?:music|soundtrack)\b|بدون\s*(?:هیچ\s*)?موسیقی|موسیقی\s*را\s*(?:حذف|خاموش)", re.I)
_REGENERATE = re.compile(r"\b(?:another|different|new|regenerate|replace|change|swap)\s+(?:the\s+)?(?:music|track|song|soundtrack)\b|\b(?:music|track|song)\s+(?:is\s+)?(?:wrong|off)\b|موسیقی\s*(?:دیگر|دیگری|جدید|عوض)|موسیقی\s*را\s*(?:عوض|تغییر)", re.I)
_CALMER = re.compile(r"\b(?:calmer|softer|more relaxed|less intense|gentler|slower)\b|آرام\s*‌?تر|ملایم\s*‌?تر", re.I)
_LIVELIER = re.compile(r"\b(?:more energetic|more upbeat|punchier|livelier|faster|more intense|higher energy)\b|پرانرژی\s*‌?تر|شادتر|تندتر", re.I)
_LOUDER = re.compile(r"\b(?:louder music|music louder|raise the music|turn up the music)\b|موسیقی\s*بلندتر|صدای\s*موسیقی\s*(?:بیشتر|بلندتر)", re.I)
_QUIETER = re.compile(r"\b(?:quieter music|music quieter|lower the music|turn down the music)\b|موسیقی\s*کم\s*‌?صداتر|صدای\s*موسیقی\s*(?:کمتر|پایین‌?تر)", re.I)
_SYNC_OFF = re.compile(r"\b(?:no|without|stop|disable|turn off)\s+beat[\s-]?sync\b|\bdon'?t sync\b|بدون\s*(?:سینک|همگام)", re.I)
_SYNC_ON = re.compile(r"\b(?:sync(?:hroni[sz]e)?\s+(?:to|with)\s+(?:the\s+)?(?:beat|music)|beat[\s-]?sync|cut on the beat|on the beat)\b|روی\s*بیت|سینک\s*با\s*(?:بیت|موسیقی)", re.I)


_ADD = re.compile(r"\b(?:add|put|use|give|want|need|include)\b[^.\n]{0,40}\b(?:music|soundtrack|track|song)\b|موسیقی\s*(?:اضافه|بذار|بگذار|بزار|می‌?خوام|بده)", re.I)


def music_wanted(text: str) -> bool:
    """The request itself talks about music (and does not ask for none): the studio then chooses or makes it (mode auto)."""
    return bool(_WANT.search(text or "")) and not _NO_MUSIC.search(text or "")


def edits_from_text(text: str) -> dict:
    """The music changes a plain sentence asks for: {"off", "regenerate", "energy_delta", "level_delta", "sync"}. Only what is said; empty when nothing about music is."""
    text = text or ""
    edits: dict = {}
    if _NO_MUSIC.search(text):
        edits["off"] = True
    if _REGENERATE.search(text):
        edits["regenerate"] = True
    elif _ADD.search(text) and not _NO_MUSIC.search(text):
        edits["on"] = True
    if _CALMER.search(text) and re.search(r"music|track|song|beat|موسیقی|آهنگ", text, re.I):
        edits["energy_delta"] = -0.25
    elif _LIVELIER.search(text) and re.search(r"music|track|song|beat|موسیقی|آهنگ", text, re.I):
        edits["energy_delta"] = 0.25
    if _LOUDER.search(text):
        edits["level_delta"] = 3.0
    elif _QUIETER.search(text):
        edits["level_delta"] = -3.0
    if _SYNC_OFF.search(text):
        edits["sync"] = False
    elif _SYNC_ON.search(text):
        edits["sync"] = True
    return edits


def is_music_only(text: str) -> bool:
    """The whole message is about the music: nothing else asks for a redesign, so only the audio is rebuilt."""
    if not edits_from_text(text):
        return False
    rest = text
    for pattern in (_NO_MUSIC, _REGENERATE, _ADD, _CALMER, _LIVELIER, _LOUDER, _QUIETER, _SYNC_OFF, _SYNC_ON, _WANT):
        rest = pattern.sub(" ", rest)
    rest = re.sub(r"\b(?:please|the|a|an|it|make|set|turn|to|and|with|more|less|بکن|لطفا|لطفاً|را|رو|کن|کنید|بشه|باشه)\b", " ", rest, flags=re.I)
    return len(re.findall(r"[\w؀-ۿ]+", rest)) <= 1             # at most one stray word: anything more is a request about something else, which the designer must also see
