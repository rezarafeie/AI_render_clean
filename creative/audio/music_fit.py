"""Fitting a music track to a film: where in the track the film starts, how a track that is too short is looped, and where its drop lands.

Everything is decided from the measured rhythm (creative/audio/rhythm.analyse) and rendered with ffmpeg:

* accent: when the film has a moment that deserves the music's strongest accent (the product reveal, the final line), the track's own drop (else its strongest bar line)
  is placed exactly on that moment by choosing the offset into the track. The offset is a plain trim, so nothing is stretched.
* loop: a track shorter than the film is repeated from a bar line to a bar line and the repeats are cross-faded, so the join is on the grid and not an audible seam.
* end: the film's last seconds are faded by the music bed (creative/music_bed.make_bed); a track that is longer than the film never ends abruptly because the fade is applied to the film's end, not the track's.

No model is involved; the same input gives the same file.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

CROSSFADE_MAX_S = 1.0
MIN_LOOP_S = 6.0


def _anchor_candidates(analysis: dict) -> list[tuple[int, str]]:
    """Moments of the track that can carry an accent: its drops; only a track with no drop at all offers its loudest bar lines instead."""
    drops = [(int(t), "drop") for t in analysis.get("drops_ms") or []]
    if drops:
        return drops
    bars = analysis.get("bars_ms") or []
    energy = analysis.get("energy") or []
    strong = sorted(bars, key=lambda t: -(energy[min(len(energy) - 1, int(t // 1000))] if energy else 0))
    return [(int(t), "bar") for t in strong[:6]]


def plan(analysis: dict | None, film_s: float, accent_s: float | None = None, track_s: float | None = None) -> dict:
    """Where the film starts in the track and how it is filled.

    Returns {"offset_s", "anchor": {"kind","track_ms","film_ms","error_ms"} | None, "loop": bool, "notes": [..]}. With no usable analysis (or no accent) the
    music starts at its beginning, which is what it did before this module existed."""
    track_s = float(track_s or (analysis or {}).get("duration_ms", 0) / 1000 or 0)
    notes: list[str] = []
    result = {"offset_s": 0.0, "anchor": None, "loop": bool(track_s and track_s < film_s - 0.25), "notes": notes}
    if not analysis or accent_s is None or accent_s < 1.0:
        return result
    options = []
    for t_ms, kind in _anchor_candidates(analysis):
        offset = t_ms / 1000 - accent_s
        if offset < 0:                           # the film's accent would come before the track's own: the track cannot start earlier than its first second
            continue
        if track_s and offset > track_s - 4.0:   # almost nothing of the track would remain after the offset
            continue
        options.append((0 if kind == "drop" else 1, offset, t_ms, kind))
    if not options:
        if analysis.get("drops_ms") or analysis.get("bars_ms"):
            notes.append("accent could not be placed: the track's drop comes earlier than the film's reveal (the music starts at its beginning)")
        return result
    options.sort(key=lambda o: (o[0], o[1]))
    _, offset, t_ms, kind = options[0]
    result["offset_s"] = round(offset, 3)
    result["anchor"] = {"kind": kind, "track_ms": t_ms, "film_ms": int(accent_s * 1000), "error_ms": 0}
    result["loop"] = bool(track_s and track_s - offset < film_s - 0.25)
    notes.append(f"the track's {'drop' if kind == 'drop' else 'strongest bar'} at {t_ms / 1000:.1f}s lands on the film's accent at {accent_s:.1f}s")
    return result


def aligned(analysis: dict | None, starts_s: list[float], offset_s: float, tolerance_ms: int = 80) -> int:
    """How many of the scene starts (after the first) fall within `tolerance_ms` of a beat of the track once it starts at `offset_s`."""
    beats = [int(b) - int(round(offset_s * 1000)) for b in (analysis or {}).get("beats_ms") or []]
    if not beats:
        return 0
    return sum(1 for t in starts_s[1:] if min(abs(b - int(round(t * 1000))) for b in beats) <= tolerance_ms)


def phase_offset(analysis: dict | None, starts_s: list[float], film_s: float, track_s: float | None = None) -> dict:
    """With no drop to place, slide the track (a trim of up to one beat, never a stretch) so the beat grid falls as close as possible to the film's cuts.

    The narration fixes the cuts; the music is the free part. Returns the same shape as `plan()`; the offset stays 0 when the grid is not reliable or sliding does not help."""
    result = plan(None, film_s)
    beats = [int(b) for b in (analysis or {}).get("beats_ms") or []]
    if len(beats) < 8 or float((analysis or {}).get("beat_confidence") or 0) < 0.25 or len(starts_s) < 2:
        return result
    gaps = sorted(b - a for a, b in zip(beats, beats[1:]))
    period = gaps[len(gaps) // 2]
    if period < 250:
        return result
    cuts = [int(round(t * 1000)) for t in starts_s[1:]]
    weights = [1.0] * len(cuts)
    weights[-1] = 2.0                                           # the last cut is the film's accent: it counts double

    def score(offset_ms: int) -> float:
        grid = [b - offset_ms for b in beats]
        return sum(w * 2.718281828 ** (-0.5 * (min(abs(g - c) for g in grid) / 60.0) ** 2) for c, w in zip(cuts, weights))
    best_offset = max(range(0, min(period, 1200), 10), key=score)
    if score(best_offset) <= score(0) + 0.25:
        return result
    notes = [f"the track starts {best_offset / 1000:.2f}s in so its beat grid falls on {aligned(analysis, starts_s, best_offset / 1000)} of {len(cuts)} cuts"]
    track_s = float(track_s or (analysis or {}).get("duration_ms", 0) / 1000 or 0)
    return {"offset_s": round(best_offset / 1000, 3), "anchor": None, "loop": bool(track_s and track_s - best_offset / 1000 < film_s - 0.25), "notes": notes}


def _period_ms(analysis: dict) -> int:
    """Seconds between beats, by least squares over every beat (the median gap is off by a few percent when the detected beats jitter by a frame, which is half a second wrong after ten beats)."""
    beats = [int(b) for b in (analysis or {}).get("beats_ms") or []]
    if len(beats) < 4:
        return 0
    index = list(range(len(beats)))
    mean_i, mean_t = sum(index) / len(index), sum(beats) / len(beats)
    slope = sum((i - mean_i) * (t - mean_t) for i, t in zip(index, beats)) / sum((i - mean_i) ** 2 for i in index)
    return int(round(slope))


def solve(analysis: dict, starts_s: list[float], film_s: float, *, snap: bool, tolerance_s: float, max_total_s: float) -> dict:
    """The track's place in the film and, when asked, the cuts that wait for a beat, chosen together and checked by measurement.

    A: slide the track so its drop lands on the film's accent (the last scene), else so its beat grid falls on the cuts; no scene moves.
    B (only when `snap`): scene starts wait for a beat. They may be delayed, never moved earlier (that would cut speech).
       With a drop anchor the beat grid is attached to the reveal: it is {reveal + k * period}. A cut is on the grid when its distance to the reveal is a multiple of the period, and
       that distance grows by every delay of the scenes after it. So the delays are chosen from the last scene backwards: each scene waits just long enough (at most the tolerance)
       for the cut before it to fall on the grid. The reveal may wait too as long as the drop can still reach it (the track cannot start before its first second).
       Without an anchor, the plain "wait for the next beat" rule of rhythm.snap_starts is used on the track's own grid.
       B replaces A only if it measurably puts more cuts on a beat (each checked against the real beats at the final offset).
    Returns {"fit", "starts", "total", "aligned", "moved"}."""
    from . import rhythm
    accent = starts_s[-1] if len(starts_s) >= 2 else None
    base = plan(analysis, film_s, accent)
    if base["anchor"] is None:
        base = phase_offset(analysis, starts_s, film_s)
    best = {"fit": base, "starts": list(starts_s), "total": film_s, "aligned": aligned(analysis, starts_s, base["offset_s"], 90), "moved": False}
    if not snap or not (analysis or {}).get("beats_ms") or len(starts_s) < 2:
        return best
    period = _period_ms(analysis) / 1000.0
    if base["anchor"] is None:
        timing = film_timing(analysis, base, film_s + 8.0)
        new_starts, new_total, on_beat = rhythm.snap_starts(starts_s, film_s, timing["beats_ms"], tolerance_s, max_total_s)
        if on_beat:
            score = aligned(analysis, new_starts, base["offset_s"], 90)
            if score > best["aligned"]:
                best = {"fit": base, "starts": new_starts, "total": new_total, "aligned": score, "moved": True}
        return best
    drop_s = base["anchor"]["track_ms"] / 1000.0
    last = len(starts_s) - 1
    candidates = []
    for tolerance in (tolerance_s, tolerance_s / 2):
        for reveal_wait in [i * 0.02 for i in range(0, int(min(tolerance, period) / 0.02) + 1)]:    # how long the reveal itself waits: it shifts the phase of every cut before it
            delays = [0.0] * len(starts_s)
            delays[last] = reveal_wait
            after = reveal_wait                              # the sum of the delays of the scenes after the cut being placed
            for cut in range(last - 1, 0, -1):               # cuts 1 .. last-1 (scene 0 starts the film)
                wait = (-(starts_s[last] - starts_s[cut] + after)) % period
                if 0.02 < wait <= tolerance and wait <= period - 0.03:
                    delays[cut + 1] += wait
                    after += wait
            total_delay = sum(delays)
            if film_s + total_delay > max_total_s or starts_s[last] + total_delay > drop_s:        # the drop could no longer meet the reveal
                continue
            new_starts, cumulative = [], 0.0
            for index, start in enumerate(starts_s):
                cumulative += delays[index]
                new_starts.append(round(start + cumulative, 3))
            refit = plan(analysis, film_s + total_delay, new_starts[-1])
            if refit["anchor"] is None:
                continue
            candidates.append((aligned(analysis, new_starts, refit["offset_s"], 90), -total_delay, new_starts, refit, film_s + total_delay))
    if candidates:
        score, neg_delay, new_starts, refit, total = max(candidates, key=lambda c: (c[0], c[1]))
        if score > best["aligned"]:
            best = {"fit": refit, "starts": new_starts, "total": round(total, 3), "aligned": score, "moved": True}
    return best


def _bar_edges(analysis: dict, offset_s: float, track_s: float) -> tuple[float, float]:
    """The loop body (seconds): from a bar line to a bar line, skipping a quiet intro on the repeats and stopping before a fade-out tail.

    Start: the second section's start when the track opens with a low-energy intro, else the first bar line at/after the offset. End: the last bar line before the track's
    end where the music is still at body level (a track's final seconds are usually an outro). Falls back to the whole remainder when no such body exists."""
    bars = [b / 1000 for b in analysis.get("bars_ms") or [] if b / 1000 >= offset_s - 1e-6]
    if len(bars) < 3:
        return offset_s, track_s
    energy = analysis.get("energy") or []
    sections = analysis.get("sections") or []
    start = bars[0]
    if len(sections) >= 2 and sections[0].get("label") == "low":
        later = [b for b in bars if b >= sections[1]["start_ms"] / 1000 - 0.35]
        if later:
            start = later[0]
    body = [energy[i] for i in range(int(start), min(len(energy), int(track_s))) if energy[i] > 0]
    level = float(sorted(body)[len(body) // 2]) if body else 0.0
    end = None
    for b in sorted((b for b in bars if b <= track_s - 0.4), reverse=True):
        around = energy[max(0, int(b) - 1):int(b) + 1] if energy else []
        if not around or not level or min(around) >= 0.6 * level:
            end = b
            break
    if end and end - start >= MIN_LOOP_S:
        return start, end
    return offset_s, track_s


def render(source: Path, output: Path, film_s: float, fit: dict, analysis: dict | None = None) -> Path:
    """The fitted track as one stereo 48 kHz WAV exactly `film_s` long: trimmed at the offset, looped on bar lines with cross-fades when it is too short."""
    from creative.audio import rhythm
    film_s = round(float(film_s), 3)
    offset = float(fit.get("offset_s") or 0.0)
    track_s = float((analysis or {}).get("duration_ms", 0)) / 1000 or _duration(source)
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if not fit.get("loop") or track_s - offset >= film_s - 0.25:
        graph = f"[0:a]atrim=start={offset:.3f}:end={offset + film_s:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={film_s}[out]"
        command += ["-i", str(source), "-filter_complex", graph]
    else:
        first_end = track_s
        loop_start, loop_end = _bar_edges(analysis or {}, offset, track_s)
        body = max(MIN_LOOP_S / 2, loop_end - loop_start)
        beat_s = 60.0 / max(60.0, float((analysis or {}).get("bpm") or 120.0))
        xfade = round(min(CROSSFADE_MAX_S, max(0.25, beat_s * 2), body / 3), 3)
        pieces = [(offset, loop_end if loop_end > offset else first_end)]
        total = pieces[0][1] - pieces[0][0]
        while total < film_s + xfade and len(pieces) < 40:
            pieces.append((loop_start, loop_end)); total += (loop_end - loop_start) - xfade
        labels, parts = [], []
        for index, (a, b) in enumerate(pieces):
            command += ["-i", str(source)]
            parts.append(f"[{index}:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[p{index}]")
            labels.append(f"p{index}")
        chain, current = [], labels[0]
        for index in range(1, len(labels)):
            chain.append(f"[{current}][{labels[index]}]acrossfade=d={xfade}:c1=tri:c2=tri[x{index}]"); current = f"x{index}"
        parts += chain
        parts.append(f"[{current}]atrim=0:{film_s},asetpts=PTS-STARTPTS,apad=whole_dur={film_s}[out]")
        command += ["-filter_complex", ";".join(parts)]
    command += ["-map", "[out]", "-t", f"{film_s}", "-c:a", "pcm_s16le", str(output)]
    done = subprocess.run(command, capture_output=True, text=True, timeout=240)
    if done.returncode != 0 or not output.is_file():
        raise RuntimeError("the music could not be fitted to the film: " + (done.stderr or "")[-250:])
    return output


def _duration(path: Path) -> float:
    done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, timeout=30)
    try:
        return float(done.stdout.strip())
    except ValueError:
        return 0.0


def film_timing(analysis: dict | None, fit: dict, film_s: float) -> dict:
    """The track's rhythm on the FILM's clock (offset removed, repeats not unrolled beyond the first pass): what the scenes and effects are cued from."""
    if not analysis:
        return {}
    offset_ms = int(round(float(fit.get("offset_s") or 0) * 1000))
    horizon = int(film_s * 1000)

    def shift(values):
        return [int(v) - offset_ms for v in values or [] if 0 <= int(v) - offset_ms <= horizon]
    beats, bars = shift(analysis.get("beats_ms")), shift(analysis.get("bars_ms"))
    if fit.get("loop") and len(beats) >= 4:               # the loop repeats on the grid: carry the beat and bar lines on at the same spacing to the end of the film
        step = int(round(sorted(b - a for a, b in zip(beats, beats[1:]))[len(beats) // 2]))
        while step > 0 and beats[-1] + step <= horizon:
            beats.append(beats[-1] + step)
        if len(bars) >= 2:
            bar_step = int(round(sorted(b - a for a, b in zip(bars, bars[1:]))[len(bars) // 2]))
            while bar_step > 0 and bars[-1] + bar_step <= horizon:
                bars.append(bars[-1] + bar_step)
    return {"offset_ms": offset_ms, "bpm": analysis.get("bpm"), "bpm_confidence": analysis.get("bpm_confidence"), "beat_confidence": analysis.get("beat_confidence"),
            "beats_ms": beats, "strong_beats_ms": shift(analysis.get("strong_beats_ms")), "bars_ms": bars,
            "drops_ms": shift(analysis.get("drops_ms")), "buildups_ms": [[a - offset_ms, b - offset_ms] for a, b in analysis.get("buildups_ms") or [] if b - offset_ms >= 0 and a - offset_ms <= horizon],
            "anchor": fit.get("anchor"), "loop": bool(fit.get("loop"))}
