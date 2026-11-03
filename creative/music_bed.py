"""A background music bed for a narrated motion graphic: chosen, trimmed to the film, faded, and ducked under the voice.

The result is one finished audio file, so the renderer only has to play it.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

BASE_GAIN = 0.32          # level of the bed when nobody is speaking (about -10 dB)
FADE_IN, FADE_OUT = 1.2, 2.5


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z؀-ۿ]{3,}", (text or "").lower())}


def pick_from_library(words: str, duration: float, *, energy: float | None = None) -> tuple[Path, str] | None:
    """The track that best fits the brief (see creative.audio.music_select); the reasons are logged."""
    from creative.audio import music_select
    from engine import library
    tracks = [{"path": asset.path, "filename": asset.filename, "tags": list(asset.tags or []), "mood": asset.mood, "duration_sec": asset.duration_sec}
              for asset in library.scan_category("music") if Path(asset.path).is_file()]
    ranked = music_select.rank(words, duration, tracks, energy=energy)
    if not ranked:
        return None
    log.info("music chosen: %s (%s)", ranked[0]["filename"], "; ".join(ranked[0]["reasons"]) or "no match, first available")
    return Path(ranked[0]["path"]), ranked[0]["filename"]


def make_bed(source: Path, output: Path, duration: float, voice: list[dict], *, gain_db: float | None = None, duck_db: float | None = None) -> Path:
    """Loop or cut `source` to `duration`, fade it, and let the narration push it down smoothly (sidechain ducking)."""
    from brain.music import probe_music
    probe_music(source)                              # raises ValueError for an unreadable or non-audio file
    duration = round(float(duration), 3)
    gain = BASE_GAIN if gain_db is None else round(10 ** (max(-40.0, min(0.0, gain_db)) / 20), 4)
    depth = 12.0 if duck_db is None else max(0.0, min(30.0, duck_db))
    ratio = 9.0 if duck_db is None else round(1 + 0.67 * depth, 2)      # unchanged default; a deeper request means a higher ratio
    base = ("[0:a]atrim=0:{d},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume={g},"
            "afade=t=in:st=0:d={fi},afade=t=out:st={fo_start:g}:d={fo}[m]").format(
        d=duration, g=gain, fi=FADE_IN, fo=FADE_OUT, fo_start=max(0.0, duration - FADE_OUT))
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1", "-i", str(source)]
    clips = [clip for clip in voice if Path(str(clip["path"])).is_file()] if depth > 0 else []      # no ducking: the voice is not needed here
    for clip in clips:
        command += ["-i", str(clip["path"])]
    if clips:
        parts = [base]
        for index, clip in enumerate(clips, 1):
            delay = int(float(clip["start"]) * 1000)
            parts.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={delay}|{delay}[v{index}]")
        mixed = "".join(f"[v{i}]" for i in range(1, len(clips) + 1))
        parts.append(f"{mixed}amix=inputs={len(clips)}:normalize=0:duration=longest,apad=whole_dur={duration}[vox]")
        parts.append(f"[m][vox]sidechaincompress=threshold=0.02:ratio={ratio:g}:attack=20:release=500:makeup=1[out]")
        graph = ";".join(parts)
    else:
        graph = base.replace("[m]", "[out]")
    command += ["-filter_complex", graph, "-map", "[out]", "-t", f"{duration}", "-c:a", "aac", "-b:a", "192k", str(output)]
    done = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if done.returncode != 0 or not output.is_file():
        raise RuntimeError("music mix failed: " + (done.stderr or "")[-300:])
    return output
