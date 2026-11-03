"""Regenerating only the narration lines that changed, and making the new take sit at the level of the lines that did not.

A line spoken in its own request can come out louder or quieter than its neighbours; the level is matched to a kept line
(within a limit) so the splice is not audible as a jump. Nothing here calls a provider.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import loudness

MAX_GAIN_DB = 6.0


def changed_lines(old: list[str], new: list[str]) -> list[int]:
    """Indexes (same length required) whose spoken text differs; a different length means everything changed."""
    if len(old) != len(new):
        return list(range(len(new)))
    return [i for i, (a, b) in enumerate(zip(old, new)) if a != b]


def match_level(reference: Path, candidate: Path, output: Path) -> tuple[Path, float | None]:
    """The candidate's integrated loudness matched to the reference's. Returns (file, gain_db); when either cannot be measured the
    candidate is returned as it is with gain None."""
    try:
        wanted = loudness.measure(Path(reference))["integrated_lufs"]
        actual = loudness.measure(Path(candidate))["integrated_lufs"]
    except Exception:
        return Path(candidate), None
    gain = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, wanted - actual))
    if abs(gain) < 0.3:
        return Path(candidate), 0.0
    done = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(candidate), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.95",
                           "-ar", "48000", str(output)], capture_output=True, text=True, timeout=120)
    if done.returncode != 0 or not Path(output).is_file():
        return Path(candidate), None
    return Path(output), round(gain, 2)
