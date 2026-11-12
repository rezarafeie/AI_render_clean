"""A scene made from a generated picture instead of code: the picture is drawn on screen stroke by stroke, in the order a person would draw it.

1. The image model paints ONE still for the scene (a fixed style sentence for the whole film keeps the pictures alike); a vision check rejects a picture that has letters in it or
   does not match the style (one regeneration).
2. A vision model names the parts of the picture in drawing order and boxes them (0..1000 grid). Every line pixel belongs to the smallest box that contains it.
3. The parts are drawn one after another; inside a part the pen goes to the nearest next stroke, every stroke growing along its own path with a bright pen tip; then a slow push-in.
4. The result is a short video that the page shows as a clip (the same way native components are mounted). Words are never drawn by the image model: the caption layer types them.

Everything is cached next to the picture (by prompt and by length) so a rebuild never pays twice. Any failure raises; the caller falls back to a code scene.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

SIZES = {"vertical": "1024x1536", "horizontal": "1536x1024", "square": "1024x1024"}
FRAME = {"vertical": (1080, 1920), "horizontal": (1920, 1080), "square": (1080, 1080)}
FPS = 30
NO_TEXT = "No text, no letters, no numbers, no logos anywhere in the picture."


def enabled() -> bool:
    return os.environ.get("MOTION_IMAGES", "1").strip().lower() not in {"0", "false", "off", "no"}


def share_for(mode: str, scenes: int) -> int:
    """How many scenes of a film may be pictures: economic 0, balanced about 40 % (at least one), quality all."""
    mode = (mode or "balanced").strip().lower()
    if mode in {"economic", "economy", "off", "none"}:
        return 0
    if mode in {"quality", "high", "all"}:
        return scenes
    return max(1, round(0.4 * scenes)) if scenes else 0


# ── the picture ──────────────────────────────────────────────────────────────

def _generate(prompt: str, fmt: str, destination: Path) -> Path:
    from brain.lm_gateway import complete
    import base64
    response, _record = complete("photorealistic_image", prompt, endpoint="image", required={"image"}, extra={"n": 1, "size": SIZES.get(fmt, "1024x1536")})
    item = (response.get("data") or [{}])[0]
    encoded = item.get("b64_json", "")
    if not encoded or len(encoded) > 40 * 1024 * 1024:
        raise RuntimeError("the image model returned no picture")
    destination.write_bytes(base64.b64decode(encoded, validate=True))
    return destination


CHECK_PROMPT = ("You check one generated picture for a film. The film's picture style is given. Answer strict JSON "
                '{"ok": true|false, "problem": "one short sentence in English"}. ok is false when: the picture contains any readable letters, words or numbers; or it clearly does not '
                "follow the style (colours, line weight, background, density); or it is a generic placeholder (a picture-frame icon, an empty box). Otherwise ok is true.")


def _check(path: Path, style: str) -> tuple[bool, str]:
    try:
        from brain.llm import chat_vision
        raw, _usage = chat_vision(CHECK_PROMPT, json.dumps({"style": style[:600]}), images=[str(path)], route="visual_qc", return_json=True, max_tokens=300, timeout_seconds=90)
        return bool(raw.get("ok", True)), str(raw.get("problem", ""))[:200]
    except Exception as exc:                                   # a missing check never blocks a picture that was made
        log.info("picture check unavailable: %s", str(exc)[:120])
        return True, ""


def picture(prompt: str, style: str, fmt: str, folder: Path) -> Path:
    """The still for a scene, from the cache when the same prompt and style were painted before."""
    folder.mkdir(parents=True, exist_ok=True)
    full = f"{style.strip()} {prompt.strip()} {NO_TEXT}"
    key = hashlib.sha256(f"{fmt}|{full}".encode()).hexdigest()[:16]
    target = folder / f"{key}.png"
    if target.is_file():
        return target
    _generate(full, fmt, target)
    ok, problem = _check(target, style)
    if not ok:
        log.info("picture rejected (%s); painting it once more", problem)
        _generate(full + f" Avoid: {problem}", fmt, target)
    return target


# ── the drawing order ────────────────────────────────────────────────────────

ORDER_PROMPT = ("You are an animation director. A line illustration will be drawn on screen like a person drawing it with a pen, part by part. "
                "Image 1 is the illustration; image 2 is the same picture with a coordinate grid (labels 100..900 on both axes; the picture spans 0..1000 in x and y). "
                "List the parts of the picture in the order a person would draw them: first the main structure that contains the rest (an outline, a frame, the ground line), "
                "then the objects inside it from large to small, each person as separate parts (head, then body), and last the small details and light effects (stars, glints, light cones, sparkle). "
                "Give 4 to 14 parts. For each part give a tight bounding box [x0,y0,x1,y1] in the 0..1000 grid. Boxes of inner objects may lie inside the box of the structure that contains them. "
                'Return strict JSON {"parts":[{"name":"...","box":[x0,y0,x1,y1]}]} in drawing order.')


def _grid(img, path: Path) -> None:
    import cv2
    h, w = img.shape[:2]
    canvas = img.copy()
    for k in range(1, 10):
        x, y = int(w * k / 10), int(h * k / 10)
        cv2.line(canvas, (x, 0), (x, h), (60, 60, 200), 1)
        cv2.line(canvas, (0, y), (w, y), (60, 60, 200), 1)
        cv2.putText(canvas, str(k * 100), (x + 3, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 200, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, str(k * 100), (3, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 200, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), canvas)


def _parts(png: Path, grid: Path, context: str) -> list[dict]:
    from brain.llm import chat_vision
    raw, _usage = chat_vision(ORDER_PROMPT, json.dumps({"what_the_illustration_shows": context[:500]}, ensure_ascii=False), images=[str(png), str(grid)],
                              route="visual_qc", return_json=True, max_tokens=1400, timeout_seconds=120)
    parts = []
    for item in raw.get("parts") or []:
        box = [float(v) for v in item.get("box", [])][:4]
        if len(box) == 4 and box[2] > box[0] and box[3] > box[1]:
            parts.append({"name": str(item.get("name", ""))[:40], "box": [max(0.0, box[0]), max(0.0, box[1]), min(1000.0, box[2]), min(1000.0, box[3])]})
    return parts


def _assign(core, parts):
    import numpy as np
    h, w = core.shape
    ys, xs = np.nonzero(core)
    part_of = np.full(core.shape, -1, np.int32)
    area = [(p["box"][2] - p["box"][0]) * (p["box"][3] - p["box"][1]) for p in parts]
    best = np.full(len(ys), 1e18)
    pick = np.full(len(ys), -1)
    for i, p in enumerate(parts):
        x0, y0, x1, y1 = p["box"][0] * w / 1000, p["box"][1] * h / 1000, p["box"][2] * w / 1000, p["box"][3] * h / 1000
        inside = (xs >= x0 - 6) & (xs <= x1 + 6) & (ys >= y0 - 6) & (ys <= y1 + 6)
        better = inside & (area[i] < best)
        pick[better] = i
        best[better] = area[i]
    pick[pick < 0] = len(parts)                                # anything not boxed is drawn last
    part_of[ys, xs] = pick
    return part_of


def _geodesic(mask, seed):
    import cv2
    import numpy as np
    D = np.full(mask.shape, -1, np.int32)
    seen = np.zeros_like(mask)
    front = np.zeros_like(mask)
    front[seed] = 1; seen[seed] = 1; D[seed] = 0
    k, last, kernel = 0, seed, np.ones((3, 3), np.uint8)
    while k < 8000:
        grown = cv2.dilate(front, kernel) & mask & (1 - seen)
        if not grown.any():
            break
        k += 1
        D[grown > 0] = k
        seen |= grown
        front = grown
        gy, gx = np.nonzero(grown)
        last = (int(gy[0]), int(gx[0]))
    D[(mask > 0) & (D < 0)] = k
    return D, k, last


def _timeline(core, part_of, n_parts):
    """When each line pixel is reached by the pen, in 'steps along the line' (and the total)."""
    import cv2
    import numpy as np
    when = np.full(core.shape, -1, np.float32)
    offset, pen = 0.0, (0, core.shape[1] // 2)
    for pi in range(n_parts + 1):
        mask = ((part_of == pi) & (core > 0)).astype(np.uint8)
        if not mask.any():
            continue
        count, lab = cv2.connectedComponents(mask, connectivity=8)
        pieces = []
        for c in range(1, count):
            ys, xs = np.nonzero(lab == c)
            if len(ys) >= 6:
                pieces.append((c, ys, xs))
        while pieces:
            j = min(range(len(pieces)), key=lambda q: float(np.min((pieces[q][1] - pen[0]) ** 2 + (pieces[q][2] - pen[1]) ** 2)))
            c, ys, xs = pieces.pop(j)
            i = int(np.argmin((ys - pen[0]) ** 2 + (xs - pen[1]) ** 2))
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            sub = (lab[y0:y1, x0:x1] == c).astype(np.uint8)
            D, length, last = _geodesic(sub, (int(ys[i] - y0), int(xs[i] - x0)))
            view = when[y0:y1, x0:x1]
            view[D >= 0] = D[D >= 0] + offset
            offset += length * 0.92 + 4
            pen = (last[0] + y0, last[1] + x0)
        offset += 10
    when[(core > 0) & (when < 0)] = offset
    zero = np.where(core > 0, 0, 255).astype(np.uint8)
    _, labels = cv2.distanceTransformWithLabels(zero, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(core)
    lut = np.zeros(len(ys) + 2, np.float32)
    lut[1:len(ys) + 1] = when[ys, xs]
    full = lut[np.clip(labels, 0, len(ys))]
    soft = cv2.GaussianBlur(full, (0, 0), 14)                  # the soft light between strokes follows the pen smoothly
    return np.where(core > 0, full, soft).astype(np.float32), offset


# ── the video ────────────────────────────────────────────────────────────────

def draw_video(png: Path, context: str, fmt: str, seconds: float, destination: Path) -> Path:
    """The picture drawn stroke by stroke over `seconds`, as an mp4 of the film's frame size. Cached by file name."""
    if destination.is_file() and destination.stat().st_size > 1000:
        return destination
    import cv2
    import numpy as np
    width, height = FRAME.get(fmt, FRAME["vertical"])
    seconds = max(2.0, float(seconds))
    draw_s = min(8.0, max(2.5, seconds * 0.72))
    img = cv2.imread(str(png))
    if img is None:
        raise RuntimeError("the picture could not be read")
    img = np.clip((img.astype(np.float32) - 26) * 1.12, 0, 255).astype(np.uint8)          # the model's near-black ground becomes true black
    core = (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) > 110).astype(np.uint8)
    grid = png.with_suffix(".grid.jpg")
    _grid(img, grid)
    try:
        parts = _parts(png, grid, context)
    except Exception as exc:
        log.warning("drawing order unavailable, top to bottom: %s", str(exc)[:160])
        parts = []
    part_of = _assign(core, parts)
    when, total = _timeline(core, part_of, len(parts))
    tip_zone = cv2.dilate(core, np.ones((5, 5), np.uint8)).astype(np.float32)
    imgf = img.astype(np.float32)
    frames = int(seconds * FPS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".part.mp4")
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(FPS), "-i", "-",
                           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(partial)], stdin=subprocess.PIPE)
    scale = min(width / img.shape[1], height / img.shape[0])
    try:
        for f in range(frames):
            t = f / FPS
            front = min(1.0, t / draw_s) * (total + 40)
            alpha = np.clip((front - when) / 5.0, 0, 1)
            tip = np.clip(1 - (front - when) / 26.0, 0, 1) * (when <= front) * tip_zone
            pulse = 1.0 + (0.07 * math.sin(2 * math.pi * (t - draw_s) / 1.6) if t > draw_s else 0.0)
            shown = np.clip(imgf * alpha[..., None] * pulse + tip[..., None] * 140, 0, 255).astype(np.uint8)
            zoom = 1.0 + 0.045 * (t / seconds)
            matrix = np.float32([[scale * zoom, 0, (width - img.shape[1] * scale * zoom) / 2], [0, scale * zoom, (height - img.shape[0] * scale * zoom) / 2]])
            ff.stdin.write(cv2.warpAffine(shown, matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0)).tobytes())
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError("the drawing video could not be encoded")
    except Exception:
        try:
            ff.kill()
        except Exception:
            pass
        raise
    partial.replace(destination)
    return destination


def make_draft(plan, n: int, folder: Path):
    """The scene draft for scene n of a plan: a slot for the drawing video (mounted by assemble_scenes) and a clip record. Raises when the picture cannot be made."""
    from .motion_graphic import SceneDraft
    scene = plan.scenes[n - 1]
    style = getattr(plan, "image_style", "") or ("Minimal line illustration on a pure black background. Thin glowing white lines only, soft light bloom, lots of empty black space, "
                                                  "no colour, vertical composition, flat pictogram style.")
    still = picture(scene.image_prompt or scene.idea, style, plan.format, folder / "images")
    seconds = round(scene.end - scene.start, 2)
    video = folder / "images" / f"{still.stem}-{seconds:g}-{plan.format}.mp4"
    draw_video(still, f"{scene.headline}. {scene.idea}", plan.format, seconds, video)
    return SceneDraft(timebase="local", html=f'<div id="s{n}-image-slot"></div>', build_js="tl.to({}, {duration: 0.001}, 0);",
                      image_clip={"instance": f"s{n}-art", "source": str(video), "picture": str(still), "prompt": (scene.image_prompt or scene.idea)[:400]})
