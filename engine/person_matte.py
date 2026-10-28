"""A matte video of the person in a crop of the source: what lets the speaker's head rise out of the card over the panel.

Segmentation is the same MediaPipe selfie segmenter + guided filter + temporal smoothing the face-effects engine uses (engine/face_effects/_fx.py
Tracker). It runs in a subprocess with the engine's environment (bundled libs, matplotlib/sounddevice stubs). One gray mp4 per request.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _hf_cli() -> list[str] | None:
    """The installed HyperFrames CLI, when it has `remove-background` (HyperFrames >= 0.8)."""
    import os
    import shutil
    for cli in (os.environ.get("HYPERFRAMES_CLI"), "/opt/hyperframes/node_modules/hyperframes/bin/hyperframes.mjs"):   # the second is the server image's install
        if cli and Path(cli).is_file() and shutil.which("node"):
            return ["node", cli]
    return None


def _hf_model_cached() -> bool:
    """The remove-background model is already on disk (a server without internet could never fetch it, and must not wait for it)."""
    import os
    root = Path(os.environ.get("HYPERFRAMES_CACHE_DIR") or Path.home() / ".cache" / "hyperframes")
    return any((root / "background-removal" / "models").glob("*.onnx")) and any((root / "optional").glob("onnxruntime-node@*"))


def engines() -> list[str]:
    """Matte engines usable here, best first: HyperFrames' own remove-background, then the MediaPipe selfie segmenter."""
    import os
    from engine import face_effects
    want = os.environ.get("PERSON_MATTE_ENGINE", "auto")
    found = []
    if _hf_cli() and (want == "hyperframes" or (want == "auto" and _hf_model_cached())):
        found.append("hyperframes")
    if face_effects.available() and want in ("auto", "mediapipe", "hyperframes"):
        found.append("mediapipe")
    return found


def available() -> bool:
    return bool(engines())


def _matte_hyperframes(job: dict, timeout: float) -> Path:
    """One job through `hyperframes remove-background` (local ONNX model, no upload): crop -> cutout webm -> its alpha as a gray video."""
    import tempfile
    mw, mh = job["size"]
    x, y, w, h = job["crop"]
    fps = float(job.get("fps") or 30)
    out = Path(job["out"])
    with tempfile.TemporaryDirectory(dir=str(out.parent)) as tmp:
        clip, cut = Path(tmp) / "in.mp4", Path(tmp) / "cut.webm"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{job['start']:.3f}", "-t", f"{job['end'] - job['start']:.3f}", "-i", job["src"], "-an",
                        "-vf", f"crop={w}:{h}:{x}:{y},scale={mw}:{mh}:flags=bilinear,fps={fps}", "-c:v", "libx264", "-crf", "12", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", str(clip)], check=True, timeout=timeout)
        proc = subprocess.run([*_hf_cli(), "remove-background", str(clip), "-o", str(cut), "--quality", "fast"], capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0 or not cut.is_file():
            raise RuntimeError("hyperframes remove-background failed: " + (proc.stderr or proc.stdout)[-400:])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-c:v", "libvpx-vp9", "-i", str(cut), "-vf", f"alphaextract,format=gray,scale={mw}:{mh}", "-c:v", "libx264",
                        "-crf", "10", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)], check=True, timeout=timeout)
    return out


def matte(jobs: list[dict], *, timeout: float = 1800) -> list[Path]:
    """jobs: [{src, start, end, crop:[x,y,w,h], size:[mw,mh], fps, out}] -> the gray matte videos (size mw x mh), in order.
    Tries HyperFrames' remove-background first; any failure falls back to MediaPipe for the whole batch."""
    import logging
    from engine.face_effects import _env
    work = Path(jobs[0]["out"]).parent
    work.mkdir(parents=True, exist_ok=True)
    order = engines()
    if "hyperframes" in order:
        try:
            return [_matte_hyperframes(j, timeout) for j in jobs]
        except Exception as exc:
            logging.getLogger(__name__).warning("hyperframes matte unavailable, using MediaPipe: %s", str(exc)[:300])
    if "mediapipe" not in order:
        raise RuntimeError("no person matte engine available")
    spec = work / "matte_spec.json"
    spec.write_text(json.dumps(jobs))
    proc = subprocess.run([sys.executable, "-m", "engine.person_matte", str(spec)], cwd=str(ROOT), env=_env(), capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("person matte failed: " + (proc.stderr or proc.stdout)[-800:])
    return [Path(j["out"]) for j in jobs]


def _main(spec_path: str) -> int:
    import numpy as np
    from engine.face_effects._fx import Tracker
    jobs = json.loads(Path(spec_path).read_text())
    mw0, mh0 = jobs[0]["size"]
    tracker = Tracker(mw0, mh0)
    clock = 0.0                      # MediaPipe's video mode wants timestamps that only ever grow, across shots too
    for job in jobs:
        mw, mh = job["size"]
        x, y, w, h = job["crop"]
        fps = float(job.get("fps") or 30)
        frames = int(round((job["end"] - job["start"]) * fps))
        reader = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-ss", f"{job['start']:.3f}", "-t", f"{job['end'] - job['start']:.3f}", "-i", job["src"],
             "-vf", f"crop={w}:{h}:{x}:{y},scale={mw}:{mh}:flags=bilinear,fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE)
        writer = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{mw}x{mh}", "-r", f"{fps}", "-i", "-",
             "-c:v", "libx264", "-crf", "10", "-preset", "ultrafast", "-pix_fmt", "yuv420p", job["out"]], stdin=subprocess.PIPE)
        size = mw * mh * 3
        index = 0
        tracker.prev = None
        while True:
            raw = reader.stdout.read(size)
            if len(raw) < size:
                break
            rgb = np.frombuffer(raw, np.uint8).reshape(mh, mw, 3)
            mask, _face = tracker(rgb, int(clock + index * 1000 / fps))
            writer.stdin.write(mask.tobytes())
            index += 1
        writer.stdin.close()
        writer.wait()
        reader.wait()
        clock += (index + 2) * 1000 / fps
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1]))
