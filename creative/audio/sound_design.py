"""Sound effect cues: which moments earn a sound, how loud, and from which licensed asset.

Restraint is the default. An effect is placed only for a moment that has a purpose, never on every transition, never
over a spoken word, and never invented: when the library has no suitable licensed asset the cue is reported as unfilled.
"""
from __future__ import annotations

from .contracts import AudioTimingEvent

INTENSITY = {                       # cues per 10 s at most, minimum gap (ms), kinds that may get a sound
    "none": (0, 0, set()),
    "minimal": (1, 3000, {"reveal"}),
    "balanced": (2, 2000, {"reveal", "text", "transition"}),
    "dynamic": (4, 1200, {"reveal", "text", "transition", "accent"}),
    "cinematic": (3, 2500, {"reveal", "transition", "accent"}),
}
SOUND_FOR = {"reveal": "impact", "text": "click", "transition": "whoosh", "accent": "hit"}
GAIN_DB = {"impact": -8.0, "click": -18.0, "whoosh": -14.0, "hit": -12.0}
SNAP_MS = 120


def _asset(library: list[dict], sound: str) -> dict | None:
    for item in library:
        if item.get("category") == "sfx" and sound in {t.lower() for t in item.get("tags", [])} and item.get("license"):
            return item
    return None


def plan(moments: list[dict], intensity: str, library: list[dict], *, beats_ms: list[int] | None = None,
         speech: list[AudioTimingEvent] | None = None, total_ms: int | None = None) -> list[dict]:
    """`moments`: [{"time_ms", "kind": reveal|text|transition|accent|explanation, "importance": 0..1}]. Returns cues sorted by time."""
    per_10s, gap, allowed = INTENSITY[intensity]
    if not per_10s:
        return []
    words = [(e.time_ms, e.time_ms + (e.duration_ms or 0)) for e in (speech or []) if e.type == "word"]
    cues: list[dict] = []
    for moment in sorted(moments, key=lambda m: -m.get("importance", 0.5)):
        kind = moment["kind"]
        if kind not in allowed:
            continue
        time_ms = int(moment["time_ms"])
        near = min(beats_ms or [], key=lambda b: abs(b - time_ms), default=None)
        if near is not None and abs(near - time_ms) <= SNAP_MS:
            time_ms = near
        if any(start < time_ms < end for start, end in words) and moment.get("importance", 0.5) < 0.8:
            continue                                          # do not talk over a word for a minor cue
        if any(abs(c["time_ms"] - time_ms) < gap for c in cues):
            continue
        span = (total_ms or max([m["time_ms"] for m in moments] + [0]) + 1000) / 10000
        if len(cues) >= max(1, int(per_10s * max(span, 1))):
            break
        sound = SOUND_FOR[kind]
        asset = _asset(library, sound)
        cues.append({"id": f"sfx-{len(cues) + 1}", "time_ms": time_ms, "sound": sound, "purpose": kind, "gain_db": GAIN_DB[sound],
                     "fade_in_ms": 5, "fade_out_ms": 120, "asset": asset.get("path") if asset else None,
                     "license": asset.get("license") if asset else None, "source": asset.get("source") if asset else None,
                     "status": "ready" if asset else "no_licensed_asset"})
    return sorted(cues, key=lambda c: c["time_ms"])


def as_events(cues: list[dict]) -> list[AudioTimingEvent]:
    return [AudioTimingEvent(id=c["id"], type="sfx", time_ms=c["time_ms"], metadata={"sound": c["sound"], "status": c["status"]}) for c in cues]
