"""Standards-based loudness (EBU R128 via ffmpeg's loudnorm): measure, and normalize to a delivery target.

Presets are engineering defaults, not platform requirements. Peak normalization is deliberately not offered.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

PRESETS = {                                  # integrated LUFS, true peak dBTP, loudness range LU
    "instagram_reels": (-14.0, -1.5, 11.0),
    "tiktok": (-14.0, -1.5, 11.0),
    "youtube": (-14.0, -1.0, 11.0),
    "podcast": (-16.0, -1.5, 9.0),
    "social_video": (-14.0, -1.5, 11.0),
}


class AudioToolError(RuntimeError):
    pass


def _run(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if done.returncode != 0:
        raise AudioToolError((done.stderr or "ffmpeg failed")[-300:])
    return done


def measure(path: Path) -> dict:
    """Integrated loudness (LUFS), true peak (dBTP) and loudness range (LU) of a file."""
    done = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    found = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", done.stderr, re.S)
    if not found:
        raise AudioToolError("loudness could not be measured")
    data = json.loads(found.group(0))
    out = {"integrated_lufs": float(data["input_i"]), "true_peak_dbtp": float(data["input_tp"]), "loudness_range_lu": float(data["input_lra"])}
    if out["integrated_lufs"] < -70:                      # loudnorm reports -inf style values for silence
        out["silent"] = True
    return out


def normalize(source: Path, output: Path, preset: str = "social_video", *, target: tuple[float, float, float] | None = None) -> dict:
    """Two-pass loudnorm to the preset (or an explicit (LUFS, dBTP, LU) target); returns the measurement before and after."""
    lufs, peak, lra = target or PRESETS[preset]
    before = measure(source)
    if before.get("silent"):
        raise AudioToolError("the audio is silent and cannot be normalized")
    chain = (f"loudnorm=I={lufs}:TP={peak}:LRA={lra}:measured_I={before['integrated_lufs']}:measured_TP={before['true_peak_dbtp']}"
             f":measured_LRA={before['loudness_range_lu']}:linear=true:print_format=summary")
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-af", chain, "-ar", "48000", str(output)])
    return {"before": before, "after": measure(output), "target": {"lufs": lufs, "true_peak_dbtp": peak, "lra": lra}}
