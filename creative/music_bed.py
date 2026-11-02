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


def pick_from_library(words: str, duration: float) -> tuple[Path, str] | None:
    """The music track whose tags, mood and name best match the words; a longer track wins a tie."""
    from engine import library
    wanted = _words(words)
    best, best_score = None, None
    for asset in library.scan_category("music"):
        path = Path(asset.path)
        if not path.is_file():
            continue
        text = " ".join([asset.filename, asset.mood or "", *asset.tags])
        score = (len(wanted & _words(text)), 1 if (asset.duration_sec or 0) >= duration else 0, asset.duration_sec or 0)
        if best_score is None or score > best_score:
            best, best_score = (path, asset.filename), score
    return best


def make_bed(source: Path, output: Path, duration: float, voice: list[dict]) -> Path:
    """Loop or cut `source` to `duration`, fade it, and let the narration push it down smoothly (sidechain ducking)."""
    from brain.music import probe_music
    probe_music(source)                              # raises ValueError for an unreadable or non-audio file
    duration = round(float(duration), 3)
    base = ("[0:a]atrim=0:{d},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume={g},"
            "afade=t=in:st=0:d={fi},afade=t=out:st={fo_start:g}:d={fo}[m]").format(
        d=duration, g=BASE_GAIN, fi=FADE_IN, fo=FADE_OUT, fo_start=max(0.0, duration - FADE_OUT))
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1", "-i", str(source)]
    clips = [clip for clip in voice if Path(str(clip["path"])).is_file()]
    for clip in clips:
        command += ["-i", str(clip["path"])]
    if clips:
        parts = [base]
        for index, clip in enumerate(clips, 1):
            delay = int(float(clip["start"]) * 1000)
            parts.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={delay}|{delay}[v{index}]")
        mixed = "".join(f"[v{i}]" for i in range(1, len(clips) + 1))
        parts.append(f"{mixed}amix=inputs={len(clips)}:normalize=0:duration=longest,apad=whole_dur={duration}[vox]")
        parts.append("[m][vox]sidechaincompress=threshold=0.02:ratio=9:attack=20:release=500:makeup=1[out]")
        graph = ";".join(parts)
    else:
        graph = base.replace("[m]", "[out]")
    command += ["-filter_complex", graph, "-map", "[out]", "-t", f"{duration}", "-c:a", "aac", "-b:a", "192k", str(output)]
    done = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if done.returncode != 0 or not output.is_file():
        raise RuntimeError("music mix failed: " + (done.stderr or "")[-300:])
    return output
