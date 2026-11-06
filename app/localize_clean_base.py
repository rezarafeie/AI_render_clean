"""The Localize editing preview: the last render's picture and sound without the Persian captions.

The real render burns the captions in, so a caption dragged on the timeline's frame would be a second one above the
burned-in one. For editing, the project renders once without Persian captions (the English cards they hide stay
covered); the timeline then draws each caption live on top, so the caption being moved is the only one shown.

It is built only from what a render already made: the voice clips in ``placements`` (kept in the project's ``tts``
folder), the source video and the music. It never asks a voice or any other paid service for anything: when the voice
has not been made yet, or its clips are gone, the preview is ``unsupported`` and the timeline falls back to outlines over
the last rendered video. The file depends on everything except the caption looks, so moving captions never makes it
stale. It is never delivered as an export.
"""
from __future__ import annotations

from app import lowpriority
import hashlib
import json
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_lock = threading.Lock()
_building: set[str] = set()
_failed: dict[str, str] = {}


def folder(project_id: str) -> Path:
    from app import localize as store
    return store._dir(project_id) / "clean"


def _inputs(project_id: str):
    """(state as the next render draws it, placements) or the reason there is no preview."""
    from app import localize as store
    from app.project_document import localize_fingerprint

    state = store.load(project_id)
    placements = state.get("placements") or []
    if not state.get("lines") or not placements:
        return None, "صدای دوبله هنوز ساخته نشده؛ بعد از اولین رندر پیش‌نمایش ویرایش ساخته می‌شود."
    if any(not Path(p.get("file", "")).is_file() for p in placements):
        return None, "فایل‌های صدای دوبله موجود نیستند و برای ساخت پیش‌نمایش صدا دوباره ساخته نمی‌شود."
    style = store.render_style({**state, "caption_looks": {}}, store.next_version(project_id))
    key = hashlib.sha256(json.dumps({"fingerprint": localize_fingerprint(style), "box": style["caption_box"],
                                     "files": [p["file"] for p in placements]}, sort_keys=True).encode()).hexdigest()[:16]
    return (style, placements, key), ""


def status(project_id: str) -> dict:
    """{"state": "ready" | "building" | "missing" | "failed" | "unsupported", "key"?: str, "reason"?: str}."""
    found, reason = _inputs(project_id)
    if not found:
        return {"state": "unsupported", "reason": reason}
    key = found[2]
    with _lock:
        if key in _building:
            return {"state": "building", "key": key}
        if key in _failed:
            return {"state": "failed", "key": key, "reason": _failed[key]}
    if (folder(project_id) / f"base_{key}.mp4").is_file():
        return {"state": "ready", "key": key}
    return {"state": "missing", "key": key}


def ensure(project_id: str) -> dict:
    """Start building the preview when it does not exist (once). Returns the status."""
    current = status(project_id)
    if current["state"] != "missing":
        return current
    key = current["key"]
    with _lock:
        if key in _building:
            return {"state": "building", "key": key}
        _building.add(key)
        _failed.pop(key, None)

    def run() -> None:
        try:
            from app import localize as store
            from engine import localize as media
            found, _ = _inputs(project_id)
            if not found or found[2] != key:
                raise RuntimeError("the project changed while the preview was being prepared")
            style, placements, _key = found
            root = store._dir(project_id)
            out_dir = folder(project_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp = out_dir / f"base_{key}.part.mp4"
            logo = store.PROJECT_ROOT / "assets" / "brand" / "logo.png"
            media.render(root / style["source"], style, placements, tmp, work_dir=root / "work_clean",
                         fonts_dir=store.PROJECT_ROOT / "presets" / "fonts",
                         music=store.resolve_music(style.get("music") or store.DEFAULT_LOCALIZE_MUSIC),
                         logo=logo if logo.is_file() else None, only_covers=True)
            tmp.replace(out_dir / f"base_{key}.mp4")
            for old in out_dir.glob("base_*.mp4"):             # one preview is enough; older ones are for older projects
                if old.name != f"base_{key}.mp4":
                    old.unlink(missing_ok=True)
        except Exception as exc:
            log.exception("localize clean base failed for %s", project_id)
            with _lock:
                _failed[key] = str(exc)[:300]
        finally:
            with _lock:
                _building.discard(key)

    threading.Thread(target=lowpriority.wrap(run), daemon=True).start()
    return {"state": "building", "key": key}


def path_for(project_id: str, key: str) -> Path | None:
    if not key.isalnum():
        return None
    path = folder(project_id) / f"base_{key}.mp4"
    return path if path.is_file() else None
