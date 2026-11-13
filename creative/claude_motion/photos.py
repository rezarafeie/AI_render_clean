"""The real pictures a film may show (a product's photos from its page, the person's own pictures): made safe and light, named photo1.jpg ... and
described to the director; scenes show them with the kit's <Photo>."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps

MAX_PHOTOS = 8
MAX_SIDE = 1600
MIN_SIDE = 300
MAX_BYTES = 20 * 1024 * 1024


def stage(items: list[dict], folder: Path) -> list[dict]:
    """items: [{"file": path, "alt": text}] in priority order. Returns rows {name, w, h, alt, source} for the pictures that could be used."""
    folder.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if len(rows) >= MAX_PHOTOS:
            break
        try:
            source = Path(str(item.get("file", "")))
            if not source.is_file() or source.stat().st_size > MAX_BYTES:
                continue
            with Image.open(io.BytesIO(source.read_bytes())) as image:
                if getattr(image, "n_frames", 1) != 1:
                    image.seek(0)
                image = ImageOps.exif_transpose(image)
                rgba = image.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
        except (OSError, ValueError):
            continue
        if min(flat.size) < MIN_SIDE:
            continue
        if max(flat.size) > MAX_SIDE:
            scale = MAX_SIDE / max(flat.size)
            flat = flat.resize((max(1, round(flat.width * scale)), max(1, round(flat.height * scale))), Image.LANCZOS)
        digest = hashlib.sha1(flat.resize((16, 16)).tobytes()).hexdigest()      # the same picture twice (a thumbnail and its big version) is used once
        if digest in seen:
            continue
        seen.add(digest)
        name = f"photo{len(rows) + 1}.jpg"
        target = folder / name
        flat.save(target, format="JPEG", quality=88, optimize=True)
        rows.append({"name": name, "w": flat.width, "h": flat.height, "alt": str(item.get("alt", ""))[:160], "source": str(target)})
    return rows


def listing(rows: list[dict]) -> str:
    return "\n".join(f"- photos/{r['name']}: {r['w']}x{r['h']} ({'portrait' if r['h'] > r['w'] * 1.1 else 'landscape' if r['w'] > r['h'] * 1.1 else 'square'})"
                     + (f", alt: {r['alt']}" if r.get("alt") else "") for r in rows)


def sheet(rows: list[dict], path: Path) -> Path | None:
    """One image with every picture in a numbered tile, so the director can SEE what each one shows."""
    if not rows:
        return None
    from PIL import ImageDraw
    tile, label = 360, 28
    cols = min(4, len(rows))
    lines = (len(rows) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tile, lines * (tile + label)), "white")
    draw = ImageDraw.Draw(canvas)
    for i, row in enumerate(rows):
        x, y = (i % cols) * tile, (i // cols) * (tile + label)
        draw.text((x + 6, y + 6), row["name"], fill="black")
        with Image.open(row["source"]) as image:
            canvas.paste(ImageOps.contain(image.convert("RGB"), (tile - 8, tile - 4), Image.LANCZOS), (x + 4, y + label))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, format="JPEG", quality=85)
    return path
