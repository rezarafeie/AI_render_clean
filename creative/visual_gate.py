"""The visual gate that runs before a designed film is rendered: a still of every scene at the moment its text and motion should be in place; a scene that shows
nothing (a black or single-colour frame) or whose text lies over other text is sent back to its designer, never rendered."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)
TEXT_OVERLAP = re.compile(r"content_overlap|text_occluded")


def settled_times(plan) -> list[float]:
    return [round(min(scene.start + (scene.end - scene.start) * 0.6, plan.duration - 0.1), 2) for scene in plan.scenes]


def blank_scenes(project: Path, plan, work: Path) -> list[int]:
    """The scenes (1-based) whose still is black or one flat colour. Never raises: when the stills cannot be taken, nothing is reported."""
    try:
        from PIL import Image, ImageStat
        from engine.hyperframes.cli import cli_command
        times = settled_times(plan)
        raw = work / "stills"
        shutil.rmtree(raw, ignore_errors=True)
        raw.mkdir(parents=True)
        subprocess.run([*cli_command(), "snapshot", ".", "--at", ",".join(f"{t:g}" for t in times), "--no-end", "--keep", "--describe", "false", "-o", str(raw)],
                       cwd=project, capture_output=True, text=True, timeout=150, env={**os.environ, "NO_COLOR": "1"})
        blank = []
        for n, t in enumerate(times, 1):
            source = raw / f"at-{t:g}s.png"
            if not source.is_file():
                continue
            stat = ImageStat.Stat(Image.open(source).convert("L").resize((108, 192)))
            if stat.mean[0] < 14 or stat.stddev[0] < 4:
                blank.append(n)
        return blank
    except Exception as exc:
        log.warning("scene stills could not be checked: %s", str(exc)[:160])
        return []


def scene_stills(project: Path, plan, work: Path) -> dict[int, Path]:
    """{scene (1-based): PNG} of every scene at its settled moment, from the page in `project`. {} when the stills cannot be taken (never raises)."""
    try:
        from engine.hyperframes.cli import cli_command
        times = settled_times(plan)
        raw = work / "critic-stills"
        shutil.rmtree(raw, ignore_errors=True)
        raw.mkdir(parents=True)
        subprocess.run([*cli_command(), "snapshot", ".", "--at", ",".join(f"{t:g}" for t in times), "--no-end", "--keep", "--describe", "false", "-o", str(raw)],
                       cwd=project, capture_output=True, text=True, timeout=150, env={**os.environ, "NO_COLOR": "1"})
        return {n: raw / f"at-{t:g}s.png" for n, t in enumerate(times, 1) if (raw / f"at-{t:g}s.png").is_file()}
    except Exception as exc:
        log.warning("scene stills could not be taken: %s", str(exc)[:160])
        return {}


def problems(project: Path, plan, work: Path, quality: list[str], check_overlap: bool) -> list[str]:
    """Blocking findings (in the `sN-` form the repair loops read) for a page that passed the browser check."""
    out: list[str] = []
    if check_overlap:
        for line in quality:
            match = TEXT_OVERLAP.search(line) and re.search(r"#s(\d+)\b", line)
            if match:
                out.append(f"s{match.group(1)}-overlap: {line[:300]}")
    if not out:
        out += [f"s{n}-visual: this scene shows an empty frame at its settled moment (60% of its length): nothing is visible. Every element must be placed and revealed relative to the scene's own start time, and the scene must paint its background and headline."
                for n in blank_scenes(project, plan, work)]
    return out
