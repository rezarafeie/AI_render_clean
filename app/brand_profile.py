"""Per-user brand context: who is speaking, how the brand looks, what the call to action is.

Plans are filled from this profile so the studio does not ask the same question twice, and every
answer or plan edit that touches brand fields is written back. One small JSON file per user under
the jobs volume keeps it identical in local and PostgreSQL deployments without a migration.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
from pathlib import Path

from app import jobs as jobstore

FIELDS = ("name", "tagline", "cta", "accent_color", "caption_font", "logo_motion", "preferred_style")
STYLE_IDS = {"talking_1", "talking_2", "talking_3", "talking_4", "talking_5"}
FONTS = {"default", "Vazirmatn"}
LOGO_MOTIONS = {"pop", "fade", "slide", "none"}
_lock = threading.Lock()


def _dir(user_key: str) -> Path:
    digest = hashlib.sha256(user_key.encode()).hexdigest()[:32]
    return Path(jobstore.JOBS_ROOT) / "studio" / "profiles" / digest


def _clean(field: str, value) -> str | None:
    """Normalise one field; None means the value is not acceptable and is ignored."""
    text = " ".join(str(value or "").split())
    if field == "accent_color":
        text = text.upper()
        return text if re.fullmatch(r"#[0-9A-F]{6}", text) else None
    if field == "caption_font":
        return text if text in FONTS else None
    if field == "logo_motion":
        return text if text in LOGO_MOTIONS else None
    if field == "preferred_style":
        return text if text in STYLE_IDS else None
    return text[:200]


def load(user_key: str) -> dict:
    path = _dir(user_key) / "profile.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    profile = {key: data.get(key, "") for key in FIELDS}
    # Present keys were answered, including an explicit empty "none"; absent keys were never asked.
    profile["answered"] = [key for key in FIELDS if key in data]
    profile["has_logo"] = (_dir(user_key) / "logo.png").is_file()
    profile["updated_at"] = data.get("updated_at")
    return profile


def update(user_key: str, changes: dict) -> dict:
    """Merge accepted fields. Empty strings are kept: they record an explicit 'none'."""
    with _lock:
        directory = _dir(user_key)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "profile.json"
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = {}
        for key in FIELDS:
            if key in changes:
                value = _clean(key, changes[key])
                if value is not None:
                    data[key] = value
        data["updated_at"] = time.time()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        tmp.replace(path)
    return load(user_key)


def known(profile: dict, field: str) -> bool:
    """A field the user has answered before, including an explicit empty answer."""
    return field in (profile.get("answered") or [])


def logo_path(user_key: str) -> Path | None:
    path = _dir(user_key) / "logo.png"
    return path if path.is_file() else None


def save_logo(user_key: str, source: Path) -> dict:
    """Store a verified image as the brand logo (RGBA PNG, transparency kept)."""
    from PIL import Image
    directory = _dir(user_key)
    directory.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGBA")
        image.thumbnail((1600, 1600))
        tmp = directory / "logo.tmp.png"
        image.save(tmp)
    tmp.replace(directory / "logo.png")
    return load(user_key)


def copy_logo_to(user_key: str, target: Path) -> bool:
    source = logo_path(user_key)
    if not source:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True
