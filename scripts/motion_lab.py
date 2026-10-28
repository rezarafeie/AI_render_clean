#!/usr/bin/env python
"""Motion lab: preview maintained templates for an existing talking_2 job, build the HyperFrames project and snapshot it.

    JOBS_DIR=/tmp/lab python scripts/motion_lab.py <job_dir> <out_dir> [--only beat-id] [--templates]

Needs a job that has been analysed and rendered once (talking_reel_work/hyperframes_base.mp4 and visual_beats in
talking_reel.json). Prints validation results and writes snapshot PNGs plus a contact sheet. No model calls.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from creative import motion  # noqa: E402
from engine.hyperframes import VisualBeat, build_project  # noqa: E402


def load(job: Path):
    state = json.loads((job / "talking_reel.json").read_text())
    beats = [VisualBeat(**b) for b in state["visual_beats"]]
    transcript = json.loads(next((job / "transcripts").glob("*.json")).read_text())
    plan = motion.plan_from_public(state.get("creative_plan"))
    return state, beats, transcript["sentences"], plan


def main() -> int:
    job, out = Path(sys.argv[1]), Path(sys.argv[2])
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    templates = "--templates" in sys.argv
    state, beats, sentences, plan = load(job)
    if only:
        beats = [b for b in beats if b.id == only]
    base = job / "talking_reel_work" / "hyperframes_base.mp4"
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    if not templates:
        motion.compose(beats, plan, sentences)
    print(f"templates prepared in {time.monotonic() - started:.0f}s: {[b.id for b in beats]}")
    duration = float(state.get("duration") or 47)
    project = out / "project"
    build_project(project, base, beats, duration=duration)
    times = []
    for b in beats:
        length = b.end - b.start
        times += [b.start + 0.45, b.start + length * 0.55, b.end - 0.5]
    if not times:
        return 1
    snap = out / "snaps"
    subprocess.run(["npx", "--yes", "hyperframes@0.8.161", "snapshot", ".", "--no-end", "--at", ",".join(f"{t:.2f}" for t in times), "-o", str(snap)],
                   cwd=project, check=False, capture_output=True, text=True, timeout=600)
    pngs = sorted(snap.glob("*.png"))
    print(f"{len(pngs)} snapshots in {snap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
