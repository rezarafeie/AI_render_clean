"""The editing preview: the current plan rendered without captions.

A render burns captions into the video, so a caption dragged on the timeline's frame would be a second, separate thing
above the burned-in one. For editing, the project renders once without captions; the timeline then draws each caption
live on top of it (position, size, colour, text, timing), so there is only one caption and it is the one being moved.

The file depends on everything except the captions, so editing captions never makes it stale. It is built from the
same shared plan as the real render (``talking_reel.plan_render``) and never generates media (pictures not yet made are
left out and the base is rebuilt once they exist). Nothing here is ever delivered to the user as an export.
"""
from __future__ import annotations

from app import lowpriority
import dataclasses
import hashlib
import json
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_lock = threading.Lock()
_building: set[str] = set()
_failed: dict[str, str] = {}


def folder(job_dir: Path) -> Path:
    return job_dir / "talking_reel_work" / "clean"


def _key(planned, state: dict) -> str:
    plan = dataclasses.replace(planned.plan, captions=[])
    material = {
        "plan": dataclasses.asdict(plan),
        "pictures": sorted((str(k), str(v)) for k, v in (planned.pictures or {}).items()),
        "settings": planned.settings,
        "style": planned.style,
        "hook": [state.get(k) for k in ("hook", "hook_highlight", "name", "title", "music", "music_chosen", "cta")],
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _plan(job_dir: Path, raw_video: Path):
    from app import talking_reel
    planned = talking_reel.plan_render(job_dir, raw_video, prepare_media=False)
    return planned, talking_reel.load(job_dir)


def status(job_dir: Path, raw_video: Path) -> dict:
    """{"state": "ready" | "building" | "missing" | "failed" | "unsupported", "key": str, "file": str}."""
    try:
        planned, state = _plan(job_dir, raw_video)
    except Exception as exc:                                   # no analysis yet, no transcript, ...
        return {"state": "unsupported", "reason": str(exc)[:200]}
    if planned.hyperframes:
        return {"state": "unsupported", "reason": "motion scenes"}
    key = _key(planned, state)
    path = folder(job_dir) / f"base_{key}.mp4"
    with _lock:
        if key in _building:
            return {"state": "building", "key": key}
        if key in _failed:
            return {"state": "failed", "key": key, "reason": _failed[key]}
    if path.is_file():
        return {"state": "ready", "key": key, "file": path.name}
    return {"state": "missing", "key": key}


def ensure(job_dir: Path, raw_video: Path) -> dict:
    """Start building the base when it does not exist (once). Returns the status."""
    current = status(job_dir, raw_video)
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
            from app import talking_reel
            planned, state = _plan(job_dir, raw_video)
            plan = dataclasses.replace(planned.plan, captions=[])
            out_dir = folder(job_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp = out_dir / f"base_{key}.part.mp4"
            work = job_dir / "talking_reel_work" / "clean_work"
            music = state.get("music")
            if planned.style in talking_reel.SPLIT_STYLES and music in (None, talking_reel.DEFAULT_MUSIC) and music is not None and not state.get("music_chosen"):
                music = talking_reel.SPLIT_STYLES[planned.style][2]       # same bed choice as the real render
            music = talking_reel.resolve_music(music)
            common = dict(work_dir=work, music=music, cta=state.get("cta") or "", render_settings=planned.settings,
                          logo_path=talking_reel.custom_logo(job_dir))
            if planned.style in talking_reel.SPLIT_STYLES:
                planned.media.render(raw_video, plan, tmp, **common)
            else:
                planned.media.render(raw_video, plan, tmp, hook=state["hook"], highlight=state.get("hook_highlight") or [],
                                     name=state.get("name") or "", title=state.get("title") or "", **common)
            tmp.replace(out_dir / f"base_{key}.mp4")
            for old in out_dir.glob("base_*.mp4"):             # one base is enough; older ones are for older plans
                if old.name != f"base_{key}.mp4":
                    old.unlink(missing_ok=True)
        except Exception as exc:
            log.exception("clean base failed for %s", job_dir.name)
            with _lock:
                _failed[key] = str(exc)[:300]
        finally:
            with _lock:
                _building.discard(key)

    threading.Thread(target=lowpriority.wrap(run), daemon=True).start()
    return {"state": "building", "key": key}


def path_for(job_dir: Path, key: str) -> Path | None:
    if not key.isalnum():
        return None
    path = folder(job_dir) / f"base_{key}.mp4"
    return path if path.is_file() else None
