"""Screenshots and pictures the person attached, made safe to show inside a motion graphic.

A picture of any shape (a phone screenshot is portrait) is checked, rotated upright, shrunk if very large and saved as a plain PNG
inside the project; scenes show it with an <img> that points at that file and nothing else. The comparison slider has its own,
stricter intake (16:9 only); this one never refuses a picture for its shape.
"""
from __future__ import annotations

import hashlib
import io
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps

MAX_BYTES = 16 * 1024 * 1024
MAX_SIDE = 2400
MAX_PIXELS = 40_000_000
ASSET = re.compile(r"^assets/ui-[0-9a-f]{16}\.png$")
SRC = re.compile(r"^\./assets/ui-[0-9a-f]{16}\.png$")


def stage(directory: Path, owned_root: Path, attachments: list[dict]) -> list[dict]:
    """Rows {attachment_id, asset, sha256, width, height} for the images that could be used (up to 9). An attachment that is not owned by this
    conversation is an error; one that is not a usable picture is skipped."""
    root, output = owned_root.resolve(), directory.resolve() / "inputs"
    rows: list[dict] = []
    for item in attachments:
        if item.get("kind") != "image" or len(rows) >= 9:
            continue
        aid = item.get("id", "")
        if not re.fullmatch("[0-9a-f]{32}", aid):
            raise ValueError("Invalid owned attachment ID")
        source = Path(item.get("path", "")).resolve()
        if source.parent != root or source.stem != aid or not source.is_file():
            raise ValueError("Attachment is not owned by this conversation")
        if source.stat().st_size > MAX_BYTES:
            continue
        try:
            with Image.open(io.BytesIO(source.read_bytes())) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"} or getattr(image, "n_frames", 1) != 1 or image.width * image.height > MAX_PIXELS:
                    continue
                image = ImageOps.exif_transpose(image)
                flat = Image.new("RGB", image.size, (255, 255, 255))
                rgba = image.convert("RGBA")
                flat.paste(rgba, mask=rgba.getchannel("A"))
                if max(flat.size) > MAX_SIDE:
                    scale = MAX_SIDE / max(flat.size)
                    flat = flat.resize((max(1, round(flat.width * scale)), max(1, round(flat.height * scale))), Image.LANCZOS)
                buffer = io.BytesIO()
                flat.save(buffer, format="PNG", optimize=True)
        except (OSError, ValueError):
            continue
        raw = buffer.getvalue()
        digest = hashlib.sha256(raw).hexdigest()
        name = f"ui-{digest[:16]}.png"
        if any(row["asset"] == f"assets/{name}" for row in rows):
            continue
        output.mkdir(parents=True, exist_ok=True)
        (output / name).write_bytes(raw)
        rows.append({"attachment_id": aid, "asset": f"assets/{name}", "sha256": digest, "width": flat.width, "height": flat.height})
    return rows


def _files(row: dict) -> list[dict]:
    """Every staged file of one picture: the whole picture, the cleaned app view and its regions."""
    return [row, *([row["app"]] if row.get("app") else []), *row.get("regions", [])]


def restore(directory: Path, work: Path, rows: list[dict]) -> None:
    """Copy the staged pictures into a version's assets folder (also on a retry); a changed or missing file is an error, not a silent gap."""
    root, assets = directory.resolve(), work.resolve() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for row in rows:
        for item in _files(row):
            name = str(item.get("asset", ""))
            if not ASSET.fullmatch(name):
                raise ValueError("Invalid saved picture")
            source = (root / "inputs" / Path(name).name).resolve()
            if not source.is_relative_to(root / "inputs") or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != item.get("sha256"):
                raise ValueError("A saved picture is missing or changed")
            shutil.copy2(source, assets / Path(name).name)


_SYSTEM = ("You look at ONE screenshot of a software product for a motion designer who cannot see it. Return only JSON: "
           '{"description": "what the app is and what this screen shows, 1-3 sentences", "visible_text": ["the main texts visible in the app, verbatim"], '
           '"app_box": [x, y, w, h], "regions": [{"name": "short name", "what": "what this part shows", "box": [x, y, w, h]}]}. '
           "All boxes are fractions 0-1 of the whole picture (x, y = top-left). app_box is the app's OWN content only: exclude the phone status bar "
           "(clock, battery), the browser address bar and tabs, the OS navigation bar and any device bezel. regions: up to 5 distinct parts worth showing on "
           "their own (an input box, a file chip, a list, a navigation bar), each tight around that part. Describe only what is visible; invent nothing.")


def _box(value, minimum: float = 0.04) -> tuple[float, float, float, float] | None:
    try:
        x, y, w, h = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    x, y = max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
    w, h = min(w, 1.0 - x), min(h, 1.0 - y)
    return (x, y, w, h) if w >= minimum and h >= minimum else None


def _save_crop(directory: Path, image: Image.Image, box: tuple[float, float, float, float]) -> dict | None:
    left, top = round(box[0] * image.width), round(box[1] * image.height)
    right, bottom = round((box[0] + box[2]) * image.width), round((box[1] + box[3]) * image.height)
    if right - left < 80 or bottom - top < 80:
        return None
    buffer = io.BytesIO()
    image.crop((left, top, right, bottom)).save(buffer, format="PNG", optimize=True)
    raw = buffer.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    name = f"ui-{digest[:16]}.png"
    (directory / "inputs").mkdir(parents=True, exist_ok=True)
    (directory / "inputs" / name).write_bytes(raw)
    return {"asset": f"assets/{name}", "sha256": digest, "width": right - left, "height": bottom - top}


def enrich(directory: Path, rows: list[dict], *, vision=None) -> list[dict]:
    """Have the screenshot looked at once: what it shows, the app's own area (phone and browser bars cut away) and its distinct parts, each saved
    as its own picture. A picture the vision model cannot describe keeps working as it was (rows come back unchanged)."""
    if vision is None:
        from brain.llm import chat_vision as vision
    out = []
    for row in rows:
        if row.get("analysed"):
            out.append(row); continue
        try:
            source = directory / "inputs" / Path(row["asset"]).name
            answer, _ = vision(_SYSTEM, "Describe this screenshot for the motion designer.", images=[source], return_json=True, max_tokens=1500, timeout_seconds=60)
            if not isinstance(answer, dict):
                raise ValueError("no description")
            with Image.open(source) as image:
                image.load()
                updated = {**row, "analysed": True, "description": str(answer.get("description", ""))[:500],
                           "visible_text": [str(t)[:80] for t in (answer.get("visible_text") or [])[:12]]}
                app = _box(answer.get("app_box"), 0.2)
                if app:
                    updated["app"] = _save_crop(directory, image, app)
                regions = []
                for part in (answer.get("regions") or [])[:5]:
                    box = _box(part.get("box")) if isinstance(part, dict) else None
                    saved = _save_crop(directory, image, box) if box else None
                    if saved:
                        regions.append({**saved, "name": str(part.get("name", ""))[:40], "what": str(part.get("what", ""))[:160]})
                updated["regions"] = regions
                out.append(updated)
        except Exception:
            out.append({**row, "analysed": True})              # tried once; it is not asked again on every retry
    return out


def context_block(rows: list[dict]) -> str:
    """What the planner and the scene designers are told about the attached pictures. They cannot see the pictures, so they are given a
    description and the cleaned views; the raw screenshot (with phone and browser bars) is never offered when a cleaned view exists."""
    if not rows:
        return ""
    parts = ["ATTACHED PICTURES the person already gave (never ask them to upload one). You cannot see them: use what is described here."]
    for i, row in enumerate(rows, 1):
        if row.get("app"):
            app = row["app"]
            parts.append(f'- picture {i}: {row.get("description", "a product screenshot")}\n'
                         f'  visible text: {"; ".join(row.get("visible_text") or []) or "—"}\n'
                         f'  APP VIEW (system bars already cut away): <img src="./{app["asset"]}"> ({app["width"]}x{app["height"]} px, aspect {app["width"] / app["height"]:.2f})')
            for region in row.get("regions", []):
                parts.append(f'  PART "{region["name"]}" ({region["what"]}): <img src="./{region["asset"]}"> ({region["width"]}x{region["height"]} px)')
        else:
            parts.append(f'- picture {i}: <img src="./{row["asset"]}"> ({row["width"]}x{row["height"]} px, aspect {row["width"] / row["height"]:.2f}). It is a raw screenshot and '
                         'may include a phone status bar and a browser bar at the top and an OS bar at the bottom: show it only inside an overflow:hidden box, '
                         'scaled and offset so those bars are cut away.')
    parts.append("HOW TO USE THEM: a picture is reference for the real product, not a slide. Match each scene to the one PART it is about (an input box for "
                 '"describe", a file chip for "drop in your footage") and show that part large, or rebuild the control with HTML/CSS in the film\'s own palette, '
                 "type and corner style using the visible text above. Put the APP VIEW or a PART inside a device or card frame drawn with divs in the film's "
                 "palette, so it looks like part of the film, never like a pasted screenshot. Use the same frame and layout in every scene that shows the product. "
                 "<img> must use the exact src above, with width and height in px, object-fit: contain, never stretched. Do not invent interface elements, text or "
                 "numbers that are not in the description.\n")
    return "\n".join(parts)
