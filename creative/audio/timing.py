"""Narration timing from the provider's own character timestamps: words and pauses as events on the shared timeline.

These are the voice's real times (not estimates from text length). Consumers (HyperFrames scene design, captions) read the
saved file; precision is stated per event.
"""
from __future__ import annotations

from .contracts import AudioTimingEvent, ms


def words(alignment: dict, span: tuple[int, int]) -> list[dict]:
    """Words of one narrated line with start/end seconds relative to its first voiced character."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not (len(chars) == len(starts) == len(ends)):
        return []
    found, current = [], None
    for k in range(span[0], min(span[1], len(chars))):
        char = chars[k]
        if char.strip():
            if current is None:
                current = {"word": "", "start": starts[k], "end": ends[k]}
            current["word"] += char
            current["end"] = ends[k]
        elif current is not None:
            found.append(current); current = None
    if current is not None:
        found.append(current)
    # style tags such as [calm] are instructions to the voice, not words
    found = [w for w in found if not (w["word"].startswith("[") and w["word"].endswith("]"))]
    if not found:
        return []
    origin = found[0]["start"]                    # times are relative to the first spoken word
    return [{"word": w["word"], "start": round(w["start"] - origin, 3), "end": round(w["end"] - origin, 3)} for w in found]


def events(per_line_words: list[list[dict]], clip_starts: list[float | None], min_pause_s: float = 0.35) -> list[AudioTimingEvent]:
    """Word and pause events on the timeline. `clip_starts[i]` is where line i's audio begins (None when the line has no audio)."""
    out: list[AudioTimingEvent] = []
    for line, (found, start) in enumerate(zip(per_line_words, clip_starts)):
        if start is None:
            continue
        for index, item in enumerate(found):
            out.append(AudioTimingEvent(id=f"w{line + 1}-{index + 1}", type="word", time_ms=ms(start + item["start"]),
                                        duration_ms=ms(item["end"] - item["start"]), confidence=0.9,
                                        metadata={"text": item["word"], "line": line + 1, "source": "provider character timestamps"}))
            if index + 1 < len(found):
                gap = found[index + 1]["start"] - item["end"]
                if gap >= min_pause_s:
                    out.append(AudioTimingEvent(id=f"p{line + 1}-{index + 1}", type="pause", time_ms=ms(start + item["end"]), duration_ms=ms(gap),
                                                metadata={"line": line + 1}))
    return sorted(out, key=lambda e: (e.time_ms, e.type))
