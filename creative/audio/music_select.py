"""Choosing a background track from the licensed library by what the film needs, with the reasons kept.

Only what is known about a track is used: its name, tags, mood, length and (when supplied) a measured energy. Nothing is
inferred about a track's sound from a name beyond a small, explicit vocabulary, and the ranking says why each track scored as it did.
"""
from __future__ import annotations

import re
from typing import Callable

LOW = {"calm", "ambient", "sparse", "minimal", "soft", "gentle", "quiet", "slow", "lofi", "pad", "piano", "intimate", "warm", "mellow", "آرام", "ملایم"}
HIGH = {"energetic", "upbeat", "driving", "fast", "punchy", "beat", "dynamic", "trap", "bass", "drum", "drums", "hype", "پرانرژی"}
DRUMMY = {"beat", "drum", "drums", "trap", "bass", "hype"}
_NO_DRUMS = re.compile(r"\b(?:no|without|avoid)\s+(?:any\s+)?(?:drums?|beats?|percussion)\b|بدون\s+(?:درام|ضرب)", re.I)


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z؀-ۿ]{3,}", (text or "").lower().replace("_", " "))}


def rank(brief: str, duration: float, tracks: list[dict], *, energy: float | None = None,
         measure: Callable[[dict], float | None] | None = None) -> list[dict]:
    """`tracks`: [{"path", "filename", "tags", "mood", "duration_sec", "license"?}]. Best first, each with `score` and `reasons`."""
    wanted = words(brief)
    no_drums = bool(_NO_DRUMS.search(brief or ""))
    mentioned = wanted - DRUMMY if no_drums else wanted             # "no drums" must not read as a wish for drums
    wants_low = bool(mentioned & LOW) or (energy is not None and energy <= 0.4)
    wants_high = bool(mentioned & HIGH) or (energy is not None and energy >= 0.75)
    ranked = []
    for track in tracks:
        text = " ".join([str(track.get("filename") or ""), str(track.get("mood") or ""), *[str(t) for t in track.get("tags") or []]])
        own = words(text)
        score, reasons = 0.0, []
        overlap = mentioned & own
        if overlap:
            score += 2.0 * len(overlap); reasons.append("matches: " + ", ".join(sorted(overlap)))
        if wants_low and own & LOW and not wants_high:
            score += 1.5; reasons.append("calm track for a calm brief")
        if wants_low and own & HIGH and not wants_high:
            score -= 1.5; reasons.append("driving track for a calm brief")
        if wants_high and own & HIGH:
            score += 1.5; reasons.append("driving track for an energetic brief")
        if no_drums and own & DRUMMY:
            score -= 3.0; reasons.append("the brief asks for no drums")
        measured = measure(track) if measure else None
        if measured is not None and energy is not None:
            gap = abs(measured - energy)
            score += 2.0 * (1 - min(1.0, gap / 0.5)) - 1.0; reasons.append(f"measured energy {measured:.2f} vs wanted {energy:.2f}")
        if (track.get("duration_sec") or 0) >= duration:
            score += 0.5; reasons.append("long enough for the film")
        ranked.append({**track, "score": round(score, 2), "reasons": reasons,
                       "license": track.get("license") or "unknown (library file; licence not recorded)"})
    return sorted(ranked, key=lambda t: (-t["score"], -(t.get("duration_sec") or 0), str(t.get("filename") or "")))
