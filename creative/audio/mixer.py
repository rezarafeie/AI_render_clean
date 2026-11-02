"""The final mix of a narrated clip: narration clips placed on the timeline, the (already ducked) music bed under them, and the
whole thing brought to a delivery loudness with true-peak protection. One finished track means what is measured is what plays."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from . import loudness

TARGET_TOLERANCE_LU = 2.0


def master(voice: list[dict], music: dict | None, duration: float, output: Path, preset: str = "social_video") -> dict:
    """Returns {"before", "after", "target"} loudness measurements; raises when the mix cannot be made or normalised."""
    clips = [clip for clip in voice if Path(str(clip["path"])).is_file()]
    if not clips:
        raise ValueError("there is no narration audio to mix")
    duration = round(float(duration), 3)
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for clip in clips:
        command += ["-i", str(clip["path"])]
    parts = []
    for index, clip in enumerate(clips):
        delay = int(float(clip["start"]) * 1000)
        parts.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={delay}|{delay}[v{index}]")
    labels = "".join(f"[v{i}]" for i in range(len(clips)))
    parts.append(f"{labels}amix=inputs={len(clips)}:normalize=0:duration=longest[voice]")
    if music and Path(str(music["path"])).is_file():
        command += ["-i", str(music["path"])]
        parts.append(f"[{len(clips)}:a]aresample=48000,aformat=channel_layouts=stereo[bed]")
        parts.append("[voice][bed]amix=inputs=2:normalize=0:duration=longest[mix]")
    else:
        parts.append("[voice]anull[mix]")
    parts.append(f"[mix]apad=whole_dur={duration},atrim=0:{duration}[out]")
    with tempfile.TemporaryDirectory() as scratch:
        raw = Path(scratch) / "mix.wav"
        done = subprocess.run(command + ["-filter_complex", ";".join(parts), "-map", "[out]", "-c:a", "pcm_s16le", str(raw)],
                              capture_output=True, text=True, timeout=240)
        if done.returncode != 0 or not raw.is_file():
            raise RuntimeError("the mix could not be made: " + (done.stderr or "")[-200:])
        return loudness.normalize(raw, output, preset)


def within_target(measured_lufs: float, preset: str) -> bool:
    return abs(measured_lufs - loudness.PRESETS[preset][0]) <= TARGET_TOLERANCE_LU
