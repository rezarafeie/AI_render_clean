"""The speaker cut out of the video (an alpha WebM) for the windows where a text passes BEHIND the speaker.

u2net_human_seg (the model rembg uses) run directly with onnxruntime: decode the crop with ffmpeg -> mask every frame -> encode VP9 with alpha, in one pass with
no PNG files. Only the windows that need it are processed (a few seconds in all). When the model cannot be had, the engine drops those windows' behind text
(a card or a caption takes their place): never a failed video.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

MODEL_URL = os.environ.get("PREMIUM_SEG_MODEL_URL", "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx")
MODEL_BYTES = 150_000_000                 # the real file is ~168 MB; anything much smaller is a broken download
MODEL_SIZE = 320
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
_lock = threading.Lock()
_session = None


def model_path() -> Path:
    """Where the model file lives: PREMIUM_SEG_MODEL, else <repo>/assets/models (a folder the server keeps across deploys), else the user's cache folder."""
    custom = os.environ.get("PREMIUM_SEG_MODEL")
    if custom:
        return Path(custom)
    shared = Path(__file__).resolve().parents[2] / "assets" / "models"
    if shared.is_dir() and os.access(shared, os.W_OK):
        return shared / "u2net_human_seg.onnx"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "editorgpt" / "u2net_human_seg.onnx"


def ensure_model(path: Path | None = None) -> Path:
    """The model file (downloaded once, kept in the cache folder). Raises when it cannot be had."""
    path = path or model_path()
    if path.is_file() and path.stat().st_size >= MODEL_BYTES:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    log.info("downloading the segmentation model to %s", path)
    request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "editorgpt-segmentation/1"})
    with urllib.request.urlopen(request, timeout=120) as response, open(part, "wb") as handle:
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            handle.write(block)
    if part.stat().st_size < MODEL_BYTES:
        part.unlink(missing_ok=True)
        raise RuntimeError("the segmentation model download was incomplete")
    part.replace(path)
    return path


def available() -> bool:
    import importlib.util
    return all(importlib.util.find_spec(name) is not None for name in ("cv2", "numpy", "onnxruntime"))


def _get_session():
    global _session
    with _lock:
        if _session is None:
            import onnxruntime as ort
            options = ort.SessionOptions()
            options.intra_op_num_threads = int(os.environ.get("PREMIUM_SEG_THREADS", "3"))
            options.inter_op_num_threads = 1
            options.enable_cpu_mem_arena = False                   # the server is small: give memory back instead of keeping an arena
            options.enable_mem_pattern = False
            _session = ort.InferenceSession(str(ensure_model()), sess_options=options, providers=["CPUExecutionProvider"])
        return _session


def alpha_of(frame, session):
    """A uint8 alpha mask (h x w) of the person in an RGB frame (h x w x 3, uint8). The soft edge and the contrast are done at the model's own size and the mask is
    upsampled once: the same look as a full-size pass at a fraction of the cost."""
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (MODEL_SIZE, MODEL_SIZE), interpolation=cv2.INTER_AREA).astype("float32")
    small = small / max(float(small.max()), 1e-6)
    small = (small - np.array(MEAN, dtype="float32")) / np.array(STD, dtype="float32")
    blob = small.transpose(2, 0, 1)[None].astype("float32")
    pred = session.run(None, {session.get_inputs()[0].name: blob})[0][0, 0]
    pred = (pred - pred.min()) / max(float(pred.max() - pred.min()), 1e-6)
    pred = cv2.GaussianBlur(pred, (0, 0), 0.6)                         # a soft edge: no hard halo on hair and shoulders
    pred = np.clip((pred - 0.15) / 0.7, 0, 1)                          # drop the faint fog, keep the body solid
    mask = cv2.resize(pred, (w, h), interpolation=cv2.INTER_LINEAR)
    return (np.clip(mask, 0, 1) * 255).astype("uint8")


def cut_out(video: Path, start: float, duration: float, crop: tuple[int, int, int, int], out: Path, *, fps: int = 30,
            should_stop: Callable[[], bool] | None = None, on_frame: Callable[[int, int], None] | None = None) -> int:
    """Writes `out` (WebM VP9 with alpha) of the person in video[start:start+duration] cropped to crop = (x, y, w, h) in source pixels. Returns the source y of the
    top of the person's head (median over the window): the text that passes behind is placed against it."""
    import numpy as np
    x, y, w, h = crop
    w, h = w - w % 2, h - h % 2
    session = _get_session()
    total = max(1, int(round(duration * fps)))
    out.parent.mkdir(parents=True, exist_ok=True)
    reader = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{duration:.3f}", "-vf", f"fps={fps // 2},crop={w}:{h}:{x}:{y}",
                               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    writer = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                               "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "4M", "-auto-alt-ref", "0", "-deadline", "realtime", "-cpu-used", "5",
                               str(out)], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = w * h * 3
    done = 0
    tops: list[int] = []
    try:
        while True:
            if should_stop and should_stop():
                raise InterruptedError("stopped")
            raw = reader.stdout.read(size)
            if len(raw) < size:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
            alpha = alpha_of(frame, session)
            rows = (alpha[::4] > 128).any(axis=1)
            if rows.any():
                tops.append(y + int(rows.argmax()) * 4)
            rgba = np.dstack([frame, alpha])
            blob = rgba.tobytes()
            writer.stdin.write(blob)
            writer.stdin.write(blob)
            done += 2
            if on_frame:
                on_frame(done, total)
        writer.stdin.close()
        if writer.wait(timeout=300) != 0 or not out.is_file():
            raise RuntimeError("the alpha video could not be encoded")
    finally:
        for process in (reader, writer):
            try:
                if process.poll() is None:
                    process.kill()
            except Exception:
                pass
    if done == 0:
        raise RuntimeError("no frames were read for the cut-out")
    tops.sort()
    return tops[len(tops) // 2] if tops else y


# ── the worker process: the model runs in its own process so its memory (hundreds of MB) is returned to the server when the windows are done ──

def run_windows(video: Path, windows: list[dict], *, fps: int = 30, should_stop: Callable[[], bool] | None = None,
                on_progress: Callable[[int, int, int], None] | None = None) -> dict[int, int]:
    """Cuts out every window ({"n", "start", "duration", "crop": [x, y, w, h], "out"}) in a child process; returns {n: head-top y}. Raises when a window fails."""
    import json
    import sys
    spec = json.dumps({"video": str(video), "fps": fps, "windows": windows})
    child = subprocess.Popen([sys.executable, "-m", "creative.claude_premium.segment"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             cwd=str(Path(__file__).resolve().parents[2]))
    tops: dict[int, int] = {}
    errors: list[str] = []
    try:
        child.stdin.write(spec)
        child.stdin.close()
        for line in child.stdout:
            if should_stop and should_stop():
                raise InterruptedError("stopped")
            parts = line.split()
            if len(parts) == 4 and parts[0] == "PROGRESS" and on_progress:
                on_progress(int(parts[1]), int(parts[2]), int(parts[3]))
            elif len(parts) == 3 and parts[0] == "TOP":
                tops[int(parts[1])] = int(parts[2])
            elif parts and parts[0] == "FAIL":
                errors.append(line.strip()[:300])
        child.wait(timeout=60)
    finally:
        if child.poll() is None:
            child.kill()
    if child.returncode not in (0, None) and not tops:
        raise RuntimeError("the cut-out process failed: " + ((child.stderr.read() if child.stderr else "") or " ".join(errors))[-300:])
    if errors:
        log.warning("cut-out windows failed: %s", errors)
    return tops


def _main() -> None:
    import json
    import sys
    try:
        os.nice(5)
    except OSError:
        pass
    spec = json.load(sys.stdin)
    video, fps = Path(spec["video"]), int(spec.get("fps", 30))
    for window in spec["windows"]:
        n = int(window["n"])

        def tick(done: int, total: int, n=n) -> None:
            if done % 10 == 0:
                print("PROGRESS", n, done, total, flush=True)
        try:
            top = cut_out(video, float(window["start"]), float(window["duration"]), tuple(int(v) for v in window["crop"]), Path(window["out"]), fps=fps, on_frame=tick)
            print("TOP", n, top, flush=True)
        except Exception as exc:
            print("FAIL", n, str(exc).replace("\n", " ")[:200], flush=True)


if __name__ == "__main__":
    _main()
