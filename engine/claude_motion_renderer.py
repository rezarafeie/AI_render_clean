"""Render a Claude-motion project (creative/claude_motion): a Remotion project the studio's own kit and a film-specific art library and scenes are written into.

Runs on the cloud worker (and locally) inside the prepared workspace: `node render.mjs video out/video.mp4` with the image's Remotion packages linked as node_modules.
The video is muted (the voice and the music bed are mixed by the studio afterwards). A failure is reported with the renderer's own one-line `RENDER_ERROR ...`.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(workspace: Path, output: Path, *, timeout: float | None = None, on_progress=None) -> None:
    root = workspace.resolve()
    for required in ("render.mjs", "src/index.ts", "src/Scenes.tsx", "src/timing.json"):
        if not (root / required).is_file():
            raise ValueError(f"The Claude-motion project is missing {required}")
    if any(p.is_symlink() for p in root.rglob("*") if "node_modules" not in p.parts):
        raise ValueError("The Claude-motion project must not contain links")
    modules = root / "node_modules"
    if not modules.exists():
        modules.symlink_to((ROOT / "remotion" / "node_modules").resolve())
    out = root / "out"
    out.mkdir(exist_ok=True)
    target = out / "video.mp4"
    target.unlink(missing_ok=True)
    env = {**os.environ, "REMOTION_CONCURRENCY": os.environ.get("REMOTION_CONCURRENCY", "2")}
    process = subprocess.Popen(["node", "render.mjs", "video", "out/video.mp4"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               start_new_session=True, env=env)

    def stop():
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    deadline = float(os.environ.get("REMOTION_TIMEOUT_S", "5400"))
    timer = threading.Timer(min(deadline, timeout) if timeout else deadline, stop)
    timer.daemon = True
    timer.start()
    tail = deque(maxlen=30)
    last = -1
    try:
        for line in process.stdout:
            tail.append(line)
            if line.startswith("PROGRESS ") and on_progress:
                try:
                    value = min(95, int(line.split()[-1]))
                except ValueError:
                    continue
                if value != last:
                    on_progress(value)
                    last = value
        if process.wait() != 0:
            reason = next((l.strip() for l in reversed(tail) if l.startswith("RENDER_ERROR")), "")
            raise RuntimeError("Claude-motion render failed: " + (reason or "".join(tail))[-1800:])
    finally:
        timer.cancel()
        stop()
        process.stdout.close()
    if not target.is_file() or not target.stat().st_size:
        raise RuntimeError("Claude-motion render produced no video")
    output.parent.mkdir(parents=True, exist_ok=True)
    if target.resolve() != output.resolve():
        target.replace(output)
