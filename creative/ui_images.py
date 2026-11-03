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


def restore(directory: Path, work: Path, rows: list[dict]) -> None:
    """Copy the staged pictures into a version's assets folder (also on a retry); a changed or missing file is an error, not a silent gap."""
    root, assets = directory.resolve(), work.resolve() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for row in rows:
        name = str(row.get("asset", ""))
        if not ASSET.fullmatch(name):
            raise ValueError("Invalid saved picture")
        source = (root / "inputs" / Path(name).name).resolve()
        if not source.is_relative_to(root / "inputs") or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != row.get("sha256"):
            raise ValueError("A saved picture is missing or changed")
        shutil.copy2(source, assets / Path(name).name)


def context_block(rows: list[dict]) -> str:
    """What the planner and the scene designers are told about the attached pictures."""
    if not rows:
        return ""
    lines = [f'- image {i}: <img src="./{row["asset"]}"> ({row["width"]}x{row["height"]} px, aspect {row["width"] / row["height"]:.2f})' for i, row in enumerate(rows, 1)]
    return ("ATTACHED PICTURES the person already gave (never ask them to upload one; use them where the request says so, in the order given):\n" + "\n".join(lines) +
            "\nShow one with an <img> whose src is exactly that path, width and height in px inside the stage, object-fit: contain, never stretched or cropped "
            "except by a device frame you draw with divs. Do not invent interface elements, text or numbers that are not visible in the picture. "
            "It is a real product screenshot: keep its details readable.\n")
