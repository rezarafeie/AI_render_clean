"""Objective checks on a finished audio file, kept apart from any model's opinion.

Everything here is measured (peak, clipping, silence, duration, loudness) or counted (words). Whether speech sounds
natural or a name is pronounced well is not decided here; the report says so rather than implying it.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import loudness
from .persian import unify_letters

_NON_WORD = re.compile(r"[^\w؀-ۿ‌]+")


def words(text: str) -> list[str]:
    return [w for w in _NON_WORD.sub(" ", unify_letters(text).lower().replace("‌", "")).split() if w]


def completeness(expected: str, recognised: str) -> dict:
    """Word-level comparison of the script and what was recognised (edit distance); text equality is not required."""
    ref, hyp = words(expected), words(recognised)
    if not ref:
        return {"word_error_rate": 0.0, "missing": [], "added": [], "expected_words": 0}
    rows = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        previous, rows[0] = rows[0], i
        for j, h in enumerate(hyp, 1):
            previous, rows[j] = rows[j], min(rows[j] + 1, rows[j - 1] + 1, previous + (r != h))
    return {"word_error_rate": round(rows[len(hyp)] / len(ref), 3), "missing": [w for w in ref if w not in hyp][:20],
            "added": [w for w in hyp if w not in ref][:20], "expected_words": len(ref)}


def _filter_stats(path: Path, graph: str) -> str:
    done = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", graph, "-f", "null", "-"], capture_output=True, text=True, timeout=300)
    return done.stderr


def analyse(path: Path, *, expected_text: str = "", recognised_text: str | None = None, expected_duration_s: float | None = None,
            preset: str | None = None, max_silence_ratio: float = 0.35) -> dict:
    """A report with `measured` values, `warnings` (what failed) and `not_checked` (what this cannot judge)."""
    path = Path(path)
    warnings, measured = [], {}
    if not path.is_file() or path.stat().st_size == 0:
        return {"ok": False, "measured": {}, "warnings": [{"code": "missing_or_empty", "message": "The audio file is missing or empty."}], "not_checked": []}
    try:
        info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,channels", "-of", "default=nw=1", str(path)],
                              capture_output=True, text=True, timeout=60).stdout
        duration = float(re.search(r"duration=([\d.]+)", info).group(1))
        if "codec_type=audio" not in info:
            raise ValueError("no audio stream")
    except Exception:
        return {"ok": False, "measured": {}, "warnings": [{"code": "unreadable", "message": "The file is not playable audio."}], "not_checked": []}
    measured["duration_s"] = round(duration, 3)
    stats = _filter_stats(path, "volumedetect")
    peak = re.search(r"max_volume: (-?[\d.]+) dB", stats)
    if peak:
        measured["peak_db"] = float(peak.group(1))
        if measured["peak_db"] >= -0.1:
            warnings.append({"code": "clipping", "message": f"The peak reaches {measured['peak_db']} dB: the signal is clipping or about to."})
    silence = _filter_stats(path, "silencedetect=noise=-45dB:d=0.4")
    total_silence = sum(float(m) for m in re.findall(r"silence_duration: ([\d.]+)", silence))
    measured["silence_ratio"] = round(total_silence / duration, 3) if duration else 0.0
    if measured["silence_ratio"] > max_silence_ratio:
        warnings.append({"code": "excess_silence", "message": f"{measured['silence_ratio']:.0%} of the audio is silent."})
    try:
        measured["loudness"] = loudness.measure(path)
        if measured["loudness"].get("silent"):
            warnings.append({"code": "silent", "message": "The audio is effectively silent."})
        elif preset in loudness.PRESETS:
            target, tp, _ = loudness.PRESETS[preset]
            if abs(measured["loudness"]["integrated_lufs"] - target) > 2.0:
                warnings.append({"code": "loudness_off_target", "message": f"Integrated loudness {measured['loudness']['integrated_lufs']} LUFS is more than 2 LU from the {preset} target ({target})."})
            if measured["loudness"]["true_peak_dbtp"] > tp + 0.5:
                warnings.append({"code": "true_peak_high", "message": f"True peak {measured['loudness']['true_peak_dbtp']} dBTP is above {tp}."})
    except loudness.AudioToolError:
        warnings.append({"code": "loudness_unmeasured", "message": "Loudness could not be measured."})
    if expected_duration_s is not None and abs(duration - expected_duration_s) > max(0.25, expected_duration_s * 0.03):
        warnings.append({"code": "duration_mismatch", "message": f"The audio lasts {duration:.1f}s but {expected_duration_s:.1f}s was expected."})
    if recognised_text is not None and expected_text:
        measured["completeness"] = completeness(expected_text, recognised_text)
        if measured["completeness"]["word_error_rate"] > 0.25:
            warnings.append({"code": "speech_incomplete", "message": f"The recognised speech differs from the script ({measured['completeness']['word_error_rate']:.0%} word error)."})
    not_checked = ["naturalness and emotion of the voice", "whether names and brands are pronounced correctly"]
    if recognised_text is None:
        not_checked.append("script completeness (no transcript was supplied)")
    return {"ok": not warnings, "measured": measured, "warnings": warnings, "not_checked": not_checked}
