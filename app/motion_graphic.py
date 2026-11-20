"""Motion graphics in chat: describe a clip, get an MP4, ask for changes.

State lives in files next to the conversation (``<studio>/<user>/<conversation>/motion/<id>/``) and a pointer in the conversation state:

  motion.json     the record (status, stage, versions, questions)
  v1/ v2/ ...     one HyperFrames project per version: index.html, page.json, assets/, motion.mp4, thumb.jpg

Work runs in a background thread, one render at a time on this server (the check and the render both drive Chromium).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from app.studio_store import ROOT

log = logging.getLogger(__name__)
_LOCKS: dict[str, threading.RLock] = {}
_RUNNING: dict[str, threading.Thread] = {}
_DIRS: dict[str, Path] = {}                  # motion id -> its folder (so a worker can re-read its own record)
_local = threading.local()                   # the run token of the worker thread (and of the threads it starts)
_depth = threading.local()
_BROWSER = threading.Semaphore(1)
ACTIVE = ("queued", "writing", "checking", "rendering")
_SCENE_WORKERS = 3
# Defaults are what the production server measured (4 vCPU, CPU-only Chromium): a 10 s clip checked in 40 s and rendered in 185 s. Real timings replace them.
_STAT_DEFAULTS = {"plan_s": 15.0, "scene_s": 35.0, "check_s": 40.0, "render_per_s": 18.0}
_stats_lock = threading.Lock()
MAX_VERSIONS = 30
RENDER_TIMEOUT_S = 1200                       # the floor; a long clip on a slow server gets more (see _render_timeout)


def _render_timeout(duration: float, per_second: float) -> float:
    """How long a render may take: three times what this server measured per second of video, never less than the floor, never more than an hour."""
    return min(3600.0, max(float(RENDER_TIMEOUT_S), per_second * duration * 3))


def _safe(user_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", user_key)


def folder(user_key: str, conversation_id: str, motion_id: str) -> Path:
    return ROOT / _safe(user_key) / conversation_id / "motion" / motion_id


class _Guard:
    """Re-entrant lock for one job: a thread lock plus an flock on the job's folder, so the API process (Stop, retry) and the worker never interleave
    a read-modify-write of the record."""

    def __init__(self, motion_id: str):
        self.key = motion_id
        self.rlock = _LOCKS.setdefault(motion_id, threading.RLock())

    def __enter__(self):
        self.rlock.acquire()
        depths = getattr(_depth, "d", None)
        if depths is None:
            depths = _depth.d = {}
        depths[self.key] = depths.get(self.key, 0) + 1
        self.fd = None
        directory = _DIRS.get(self.key)
        if depths[self.key] == 1 and directory is not None:
            try:
                import fcntl
                self.fd = open(directory / ".lock", "a")
                fcntl.flock(self.fd, fcntl.LOCK_EX)
            except (OSError, ImportError):
                self.fd = None
        return self

    def __exit__(self, *exc):
        depths = _depth.d
        depths[self.key] -= 1
        try:
            if self.fd is not None and depths[self.key] == 0:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                self.fd.close()
        finally:
            self.rlock.release()
        return False


def _lock(motion_id: str) -> _Guard:
    return _Guard(motion_id)


def load(directory: Path) -> dict:
    _DIRS[directory.name] = directory
    return json.loads((directory / "motion.json").read_text())


def save(directory: Path, record: dict) -> dict:
    _DIRS[directory.name] = directory
    with _lock(record["id"]):
        record["updated_at"] = time.time()
        temporary = directory / f"motion.{threading.get_ident()}.part"
        temporary.write_text(json.dumps(record, ensure_ascii=False))
        temporary.replace(directory / "motion.json")
    return record


def locate(motion_id: str, user_key: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", motion_id):
        raise KeyError(motion_id)
    for path in (ROOT / _safe(user_key)).glob(f"*/motion/{motion_id}"):
        if (path / "motion.json").is_file():
            return path
    raise KeyError(motion_id)


def _emit(conversation_id: str, kind: str, **data: Any) -> None:
    try:
        from app.studio_orchestrator import _emit as emit
        emit(conversation_id, kind, **data)
    except Exception:
        log.warning("motion event %s could not be published", kind, exc_info=True)


def _assistant(conversation_id: str, user_key: str, text: str) -> None:
    try:
        from app.studio_orchestrator import _assistant as say
        say(conversation_id, user_key, text)
    except Exception:
        log.warning("motion message could not be stored", exc_info=True)



def _spoken_words(path: str) -> str:
    """The transcript of an attached audio file when it is speech (at least 8 words), else ''. A failure to transcribe means 'treat it as music', as before."""
    try:
        import tempfile
        from creative.reference import speech_text
        with tempfile.TemporaryDirectory(prefix="attached-audio-") as work:
            text = speech_text(Path(path), Path(work), limit=3000)
        return text if len(text.split()) >= 8 else ""
    except Exception:
        log.info("attached audio could not be checked for speech", exc_info=True)
        return ""


# ── records ──────────────────────────────────────────────────────────────────

def create(conversation_id: str, user_key: str, request: str, context: str = "", style: str = "", voice_id: str = "", voice_style: str = "", *, attachments: list[dict] | None = None,
           photos: list[dict] | None = None) -> dict:
    from creative import directives
    request, wanted = directives.parse(request)
    if wanted.narrator is not None: voice_id = wanted.narrator
    if wanted.style is not None: voice_style = wanted.style
    from creative.audio import music_director
    music = {"mode": wanted.music, "words": wanted.music_words} if wanted.music else None
    if music is None and any(item.get("kind") == "audio" and item.get("path") for item in attachments or []):
        spoken = _spoken_words(next(item for item in attachments or [] if item.get("kind") == "audio" and item.get("path"))["path"])
        if spoken:                                             # a voice recording, not music: laid under the new narration it would be heard twice
            context = ("ATTACHED VOICE RECORDING (the person's own spoken words, transcribed; it is the source of the film's content and is NOT used as music):\n" + spoken + "\n\n" + context)
            wanted.notes.append("فایل صوتی پیوست‌شده گفتار بود، نه موسیقی؛ برای اینکه صدا دوبار پخش نشود زیر نریشن نگذاشتم و متن آن را منبع محتوا گرفتم.")
        else:
            music = {"mode": "attached", "words": ""}          # an audio file with no speech came with the request: it is the music
    elif music is None and music_director.music_wanted(request):
        music = {"mode": "auto", "words": ""}                  # the request talks about music: the studio chooses or makes it
    if music and music.get("mode") == "attached":
        track = next((item for item in attachments or [] if item.get("kind") == "audio" and item.get("path")), None)
        if track: music["path"], music["name"] = track["path"], track.get("filename", "")
        else: wanted.notes.append("موسیقی «attached» خواسته شد ولی فایل صوتی پیوست نبود؛ ویدیو بدون موسیقی ساخته می‌شود.")
    if music and music.get("mode") not in (None, "off"):
        fresh = music["mode"] in {"auto", "search", "generate"}
        music.update(cost=wanted.music_cost or "balanced", instrumental=True if wanted.music_instrumental is None else wanted.music_instrumental, variant=0,
                     sync=wanted.music_sync if wanted.music_sync is not None else (fresh or (wanted.rhythm or "speech_first") != "speech_first"))
    from creative.audio import direction
    audio_plan, plan_notes = direction.plan(request, wanted)
    if music and music.get("mode") in {"library", "auto", "search", "generate"} and audio_plan.music_energy:
        music["energy"] = audio_plan.music_energy
    motion_id = uuid.uuid4().hex[:12]
    directory = folder(user_key, conversation_id, motion_id)
    directory.mkdir(parents=True, exist_ok=True)
    record = {"id": motion_id, "conversation_id": conversation_id, "user_key": user_key, "request": request.strip()[:4000],
              "context": context[:9000], "style": style[:2000], "status": "queued", "stage": "queued", "progress": 0, "message": "", "questions": [],
              "versions": [], "current": 0, "error": None, "created_at": time.time(), "pending_change": None, "answers": [], "log": [],
              "voice_id": voice_id, "voice_style": voice_style, "music": music, "directive_notes": wanted.notes, "pronunciations": wanted.pronunciations, "rhythm": wanted.rhythm or ("balanced" if music and music.get("sync") and music.get("mode") in {"auto", "search", "generate"} else "speech_first"), "loudness": wanted.loudness or "social_video",
              "audio_plan": audio_plan.model_dump(), "audio_plan_notes": plan_notes,
              "music_gain_db": wanted.music_gain_db, "ducking_db": wanted.ducking_db}
    try:
        from creative import claude_motion
        record["engine"] = "claude" if claude_motion.enabled() else "classic"
    except Exception:
        record["engine"] = "classic"
    try:
        from creative import claude_intro
        if record["engine"] == "claude" and claude_intro.wanted(request):
            footage = next((item for item in attachments or [] if item.get("kind") == "video" and item.get("path")), None)
            record["intro"] = claude_intro.kind_of(request, bool(footage))      # «ویدیوی معرفی»: story | reel | presenter | film3d (creative/claude_intro)
            if footage:
                record["intro_footage"] = str(footage["path"])
    except Exception:
        log.warning("the intro engines could not be checked", exc_info=True)
    try:
        from creative import claude_vox
        if record["engine"] == "claude" and not record.get("intro") and claude_vox.wanted(request):
            record["vox"] = True                     # «به سبک ووکس»: the paper-collage documentary engine (creative/claude_vox)
    except Exception:
        log.warning("the vox engine could not be checked", exc_info=True)
    if attachments:
        from creative.shotcraft_compare import stage_images
        record['image_inputs']=stage_images(directory,ROOT/_safe(user_key)/conversation_id/'attachments',[a for a in attachments if a.get('kind')=='image'])
        from creative import ui_images
        record['ui_images']=ui_images.stage(directory,ROOT/_safe(user_key)/conversation_id/'attachments',[a for a in attachments if a.get('kind')=='image'])
    shots = [{"file": str(directory / "inputs" / Path(row["asset"]).name), "alt": "the person's own picture"} for row in record.get("ui_images", [])] + list(photos or [])
    if shots and record["engine"] == "claude":
        record["photos"] = shots[:16]                # real pictures for the Claude engine (product photos from the linked page, the person's own pictures)
    return save(directory, record)


def _version(record: dict, number: int | None = None) -> dict | None:
    number = number or record.get("current")
    return next((v for v in record["versions"] if v["n"] == number), None)


STALE_AFTER = 600          # seconds without any progress save, with no worker thread alive here: nobody is building this clip any more


HEARTBEAT_S = 30


def _beating(directory: Path) -> bool:
    """The film's worker is alive somewhere (this process, the Celery worker container...): its heartbeat file was touched in the last 2 minutes.
    Before (2026-11-17) the web process, which cannot see a worker thread in the Celery container, judged a Vox film dead during a 10-minute story call."""
    try:
        return time.time() - (directory / ".alive").stat().st_mtime < 4 * HEARTBEAT_S
    except OSError:
        return False


def _heartbeat(directory: Path, stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_S if (directory / ".alive").exists() else 0):
        try:
            (directory / ".alive").touch()
        except OSError:
            pass


def heal_if_dead(directory: Path) -> bool:
    """A record that says "working" but whose worker is gone (the server restarted a few seconds after its last save, so the start-up recovery, which only
    takes records silent for 45 s, skipped it) is turned into a retryable failure instead of spinning forever. A worker alive in this process is never touched;
    10 minutes without a single progress save is far longer than any step of the pipeline stays silent."""
    key = directory.name
    with _lock(key):
        try:
            record = load(directory)
        except (OSError, ValueError):
            return False
        thread = _RUNNING.get(key)
        if (record.get("status") not in ACTIVE or (thread is not None and thread.is_alive())
                or time.time() - float(record.get("updated_at") or 0) <= STALE_AFTER or _beating(directory)):
            return False
        record.update(status="failed", stage="failed", message="ساخت با راه‌اندازی دوبارهٔ سرور قطع شد؛ با «تلاش دوباره» از همان طرح و صحنه‌های آماده ادامه می‌دهد.", error="interrupted")
        save(directory, record)
    _emit(record["conversation_id"], "motion.progress", motion_id=key, status="failed", stage="failed", progress=record.get("progress", 0), message=record["message"])
    _emit(record["conversation_id"], "job.failed", motion_id=key, message=record["message"], resumable=True)
    _emit(record["conversation_id"], "work.state", busy=False)
    return True


def view(directory: Path) -> dict:
    heal_if_dead(directory)
    record = load(directory)
    versions = [{k: v for k, v in item.items() if k != "page"} for item in record["versions"]]
    return {"id": record["id"], "conversation_id": record["conversation_id"], "status": record["status"], "stage": record["stage"],
            "progress": record["progress"], "message": record["message"], "questions": record["questions"], "error": record["error"],
            "request": record["request"], "versions": versions, "current": record["current"], "updated_at": record["updated_at"], "log": record.get("log", [])[-60:], "snapshots": record.get("snapshots", []), "eta_s": record.get("eta_s"), "eta_at": record.get("eta_at"),
            "active": record["status"] in ACTIVE}


def _progress(directory: Path, status: str, progress: int, message: str, *, stage: str | None = None, eta: float | None = None) -> dict:
    if _cancelled(directory.name):
        raise _Cancelled()
    with _lock(directory.name):
        record = load(directory)
        record.update(status=status, stage=stage or status, progress=progress, message=message)
        if eta is not None:
            record.update(eta_s=round(max(0.0, eta)), eta_at=time.time())
        elif status not in ACTIVE:
            record.update(eta_s=None, eta_at=None)
        save(directory, record)
    _emit(record["conversation_id"], "motion.progress", motion_id=record["id"], status=status, stage=record["stage"], progress=progress, message=message)
    return record


def _note(directory: Path, key: str, text: str, state: str = "active", detail: str | None = None, request: str | None = None) -> None:
    """One line of what is really happening (about this clip's own content). A line with the same key is updated, not repeated.
    `detail` is the exact material of that step (the request, the lines, the choices), shown when the person opens the step."""
    if _cancelled(directory.name):
        raise _Cancelled()
    with _lock(directory.name):
        record = load(directory)
        lines = record.setdefault("log", [])
        line = next((l for l in lines if l["key"] == key), None)
        if line:
            line.update(text=text, state=state)
        else:
            lines.append({"key": key, "text": text, "state": state, "at": time.time()})
            line = lines[-1]
        if detail is not None:
            line["detail"] = str(detail)[:3500]
        if request is not None:
            line["request"] = str(request)[:3000]                  # what this step was asked (shown as its request in the chat's step log)
        if state == "done":
            line["done_at"] = time.time()
        else:
            line.pop("done_at", None)
        save(directory, record)
    _emit(record["conversation_id"], "motion.log", motion_id=record["id"], key=key, text=text, state=state)


def _stats() -> dict:
    """Timings measured on THIS server (how long a scene, a check and a second of video really take); the estimates come from them."""
    path = ROOT / "motion_stats.json"
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {}
    return {key: float(saved.get(key, default)) for key, default in _STAT_DEFAULTS.items()}


def _learn(key: str, value: float) -> None:
    if value <= 0:
        return
    with _stats_lock:
        current = _stats()
        current[key] = round(current[key] * 0.5 + value * 0.5, 2)
        try:
            (ROOT / "motion_stats.json").write_text(json.dumps(current))
        except OSError:
            pass


def _remaining(pending_scenes: int, duration: float, *, extra: float = 0.0) -> float:
    """Seconds still to go: the scenes not finished (three at a time), the browser check and the render of ``duration`` seconds of video."""
    stats = _stats()
    return extra + -(-pending_scenes // _SCENE_WORKERS) * stats["scene_s"] * (1 if pending_scenes else 0) + stats["check_s"] + stats["render_per_s"] * duration


def _cancelled(motion_id: str) -> bool:
    """True when this worker's run was superseded: Stop was pressed (in any process) or a newer start replaced it."""
    mine = getattr(_local, "run", None)
    directory = _DIRS.get(motion_id)
    if mine is None or directory is None:
        return False
    try:
        return int(json.loads((directory / "motion.json").read_text()).get("run") or 0) != mine
    except (OSError, ValueError):
        return False


# ── pipeline ─────────────────────────────────────────────────────────────────

def start(directory: Path, *, change: str = "") -> None:
    """(Re)start the pipeline in the background: a new clip from ``request`` or, with ``change``, a new version of the current one."""
    key = directory.name
    # Every start is a new run, and the run token lives in the record (a file): a worker of an older run, in this process or another, finds out at its next
    # update that it is no longer the current run and unwinds. It never writes into the new run, and the new run never waits for it.
    with _lock(key):
        record = load(directory)
        run_id = int(record.get("run") or 0) + 1
        record["run"] = run_id
        record["error"] = None
        record["running_change"] = change                    # what this run was started for: a restart goes on with the same request
        record.update(status="queued", stage="queued", progress=0, message="دارم شروع می‌کنم…")   # the card must leave "failed" the moment the person presses retry
        save(directory, record)
    _emit(record["conversation_id"], "motion.progress", motion_id=key, status="queued", stage="queued", progress=0, message="دارم شروع می‌کنم…")
    _emit(record["conversation_id"], "work.state", busy=True)
    thread = threading.Thread(target=_guard, args=(directory, change, run_id), daemon=True, name=f"motion-{key}")
    _RUNNING[key] = thread
    thread.start()


def stop(directory: Path) -> None:
    """Stop NOW as far as the person can see: the record turns "stopped" immediately (the card and the composer's button update at once) and its run token
    changes, so the worker, wherever it runs, notices at its very next update and unwinds, discarding whatever an in-flight model call returns."""
    key = directory.name
    with _lock(key):
        record = load(directory)
        record["run"] = int(record.get("run") or 0) + 1
        if record["status"] in ACTIVE:
            record.update(status="failed", stage="failed", progress=0, message="ساخت متوقف شد.", error="stopped", eta_s=None, eta_at=None)
        save(directory, record)
    if record["status"] == "failed" and record["error"] == "stopped":
        _emit(record["conversation_id"], "motion.progress", motion_id=record["id"], status="failed", stage="failed", progress=0, message="ساخت متوقف شد.")
        _emit(record["conversation_id"], "job.failed", motion_id=record["id"], message="ساخت متوقف شد.", stopped=True, resumable=True)


def _guard(directory: Path, change: str, run_id: int | None = None) -> None:
    key = directory.name
    _DIRS[key] = directory
    _local.run = run_id if run_id is not None else int(load(directory).get("run") or 0)
    from app.render_cloud.hooks import identity
    owned = load(directory)
    from brain.lm_gateway import work_scope
    usage_scope = work_scope("motion", key, user=owned.get("user_key"), conversation=owned.get("conversation_id"))
    usage_scope.__enter__()                              # every model call of this film (and of the threads it starts) is billed to its owner and shows this film
    from brain import localize as _localize
    _localize.narration_brief(owned.get("request", "") + "".join(" " + a for a in owned.get("answers", [])))   # «با صدای خانم» decides the narrator's gender for this run
    def cloud_stage(stage):
        message = {'provisioning': 'در حال آماده‌سازی منابع رندر', 'preparing': 'در حال آماده‌سازی موتور رندر',
                   'downloading': 'در حال دریافت فایل‌های صحنه', 'rendering': 'در حال رندر فریم‌ها',
                   'uploading': 'در حال انتقال خروجی رندر', 'completed': 'خروجی رندر دریافت شد'}.get(stage)
        if message:
            _note(directory, 'render', message)
    def cloud_detail(text):
        if text:
            _note(directory, 'render', text)              # "رندر ابری: ۴۰٪ · حدود … باقی مانده", the same line every other chat shows
    cloud_token = identity.set((owned.get('user_key'), owned.get('id'), (directory,),
                                lambda: _cancelled(key), cloud_stage, cloud_detail))
    beat = threading.Event()
    threading.Thread(target=_heartbeat, args=(directory, beat), daemon=True, name=f"motion-beat-{key}").start()
    try:
        _run(directory, change)
    except _Cancelled:
        # stop() already showed it. Only the CURRENT run may write: a superseded worker unwinding late must not mark the new run as stopped.
        if _is_current(key):
            with _lock(key):
                record = load(directory)
                if record["status"] in ACTIVE:
                    record.update(status="failed", stage="failed", progress=0, message="ساخت متوقف شد.", error="stopped", eta_s=None, eta_at=None)
                    save(directory, record)
    except Exception as exc:
        if not _is_current(key):
            log.info("a superseded motion graphic worker %s ended with %s", key, type(exc).__name__)
            return
        log.exception("motion graphic %s failed", key)
        message = _public_error(exc)
        try:
            record = _progress(directory, "failed", 0, message)
        except _Cancelled:
            return
        _set_error(directory, message)
        _emit(record["conversation_id"], "job.failed", motion_id=key, message=message, resumable=True)
        _assistant(record["conversation_id"], record["user_key"], f"ساخت موشن‌گرافیک کامل نشد: {message} می‌توانید دوباره امتحان کنید یا درخواست را ساده‌تر بنویسید.")
    finally:
        beat.set()
        try:
            (directory / ".alive").unlink()
        except OSError:
            pass
        identity.reset(cloud_token)
        usage_scope.__exit__(None, None, None)
        if _RUNNING.get(key) is threading.current_thread():
            _RUNNING.pop(key, None)
            try:
                if _is_current(key) and load(directory)["status"] not in ACTIVE:     # the last "busy" signal the chat saw is now out of date
                    _emit(load(directory)["conversation_id"], "work.state", busy=False)
                    _wake_agent(load(directory))
            except (OSError, ValueError, KeyError):
                pass


def _wake_agent(record: dict) -> None:
    """A Medium agent waiting for this film goes on now (it reviews, fixes or delivers it). Before, it woke only when the chat synced (the person had it open
    and polling), so a finished film could sit undelivered with the agent still 'waiting' (2026-11-17)."""
    try:
        from app.agents.medium.graph import resume_ready
        from app.studio_store import run as run_sync
        run_sync(resume_ready(record["conversation_id"], record["user_key"]))
    except ImportError:
        pass
    except Exception:
        log.warning("the waiting agent could not be woken after film %s", record.get("id"), exc_info=True)


def _is_current(key: str) -> bool:
    """This worker belongs to the latest run of the job."""
    return not _cancelled(key)


class _Cancelled(RuntimeError):
    pass


def _set_error(directory: Path, message: str) -> None:
    with _lock(directory.name):
        record = load(directory)
        record["error"] = message
        save(directory, record)


def _public_error(exc: Exception) -> str:
    text = str(exc)
    if text.startswith("did not pass validation:"):
        from creative.motion_graphic import explain_problem
        return "صفحهٔ ساخته‌شده از بررسی خودکار رد شد و اصلاحش ممکن نشد: " + explain_problem(text.split(":", 1)[1])
    if "did not pass validation" in text or "rejected" in text:
        return "طرح پیشنهادی مدل چند بار از بررسی خودکار رد شد."
    if type(exc).__name__ == "CreativeUnavailable" and any(ord(c) > 127 for c in text):
        return text[:220]                                     # a reason written for the person (e.g. the script has too many scenes), not an outage
    if "not configured" in text or "Unavailable" in type(exc).__name__:
        return "سرویس هوش مصنوعی در دسترس نبود."
    if "timed out" in text:
        return "رندر بیشتر از زمان مجاز طول کشید."
    if re.search(r"cloud render|Cloud render|delayRender|render failed|CloudRenderError", text):
        return "رندر فیلم کامل نشد؛ طرح و کد فیلم ذخیره شده است و «تلاش دوباره» از همان‌جا ادامه می‌دهد."
    return text[:220] or "خطای ناشناخته"


def _claude_film_written(directory: Path) -> bool:
    """True once the Claude engine finished BUILDING the film (code written, built, reviewed; its state is saved just before the render starts)."""
    return (directory / "claude_motion.json").is_file()


def _run(directory: Path, change: str) -> None:
    from creative import motion_graphic as mg
    record = load(directory)
    cid, user, key = record["conversation_id"], record["user_key"], record["id"]
    if record.get("engine") == "claude" and not record.get("edit_pending"):
        try:
            if _run_claude(directory, record, change):
                return
        except _Cancelled:
            raise
        except Exception as exc:
            if _cancelled(key):
                raise _Cancelled()
            if record.get("vox") or record.get("intro"):
                # The Vox film keeps its own engine: a failure is shown and «retry» continues from its checkpoint (story, pictures, code), never a classic film.
                log.exception("vox film %s failed; no fallback to another engine", key)
                raise
            if _claude_film_written(directory) and not str(exc).startswith("the film's code did not build"):
                # The Claude engine already wrote the film's code (and saved it in checkpoint.json): only a later step (render, mix) failed. The film stays on
                # the Claude engine and fails visibly; retry continues from the saved code instead of restarting on the classic engine.
                log.exception("claude motion %s failed after its code was written; no fallback to the classic engine", key)
                raise
            log.exception("claude motion %s failed; the classic engine takes over", key)
            _note(directory, "engine-switch", "── ساخت اول (موتور موشن کلاد) کامل نشد؛ از اینجا همه‌چیز از اول با موتور دوم ساخته می‌شود. پیام‌های بالای این خط مربوط به تلاش اول‌اند ──", "done", detail=f"علت: {str(exc)[:600]}")
            _progress(directory, "writing", 5, "ساخت اول کامل نشد؛ دارم از اول با موتور دوم می‌سازم.", stage="writing")
            with _lock(key):
                record = load(directory)
                record["engine"] = "classic"
                save(directory, record)
            if change and not _version(record):
                change = ""
    previous = None
    current = _version(record)
    edit = record.get("edit_pending")
    if edit:
        change = edit.get("label") or change                   # a structured edit (Edit tab): rebuilt from its changed plan, never by the model editing the page
    elif change and current:
        previous = mg.MotionPage.model_validate(current["page"])
    brief = record["request"] + "".join(f"\nپاسخ کاربر: {a}" for a in record.get("answers", []))
    used: list[str] = []
    scene_notes: list[str] = []
    build = None
    revoiced = None
    if previous is not None and _VOICE_CHANGE.search(change):
        _progress(directory, "writing", 8, "دارم نریشن را دوباره می‌سازم.", stage="writing")
        _note(directory, "voice", "دارم نریشن را دوباره با همان اسکریپت می‌سازم")
        revoiced = _revoice(directory, record, previous)
        if revoiced is None:
            previous = None                          # the voice changed the scene timing: rebuild the clip from its plan
        else:
            _note(directory, "voice", "نریشن آماده و به ویدیو اضافه شد", "done")
    if revoiced is not None:
        page, extra = revoiced
        scene_notes.extend(extra)
        if _LOOK_CHANGE.search(change):               # the same request also changes how it looks: apply that on top, keeping the audio
            audio = list(page.audio)
            page = mg.author(brief, context=record.get("context", ""), previous=page, change=change, style=record.get("style", ""), used=used)
            page = page.model_copy(update={"audio": audio})
    elif previous is not None:
        _progress(directory, "writing", 8, "دارم تغییر را روی آخرین نسخه اعمال می‌کنم.", stage="writing")
        _note(directory, "revise", f"دارم این تغییر را اعمال می‌کنم: «{change[:80]}»")
        page = mg.author(brief, context=record.get("context", ""), previous=previous, change=change, style=record.get("style", ""), used=used)
        if page.asks():
            _ask(directory, record, page.questions, change)
            return
        _note(directory, "revise", "تغییر اعمال شد.", "done")
    else:
        built = _plan_and_build(directory, record, brief, used, scene_notes)
        if built is None:
            return
        page, build = built
    if _cancelled(key):
        raise _Cancelled()
    notes: list[str] = []
    with _BROWSER:
        page, notes = _prepare_and_render(directory, page, brief, change, used, build)
    notes = scene_notes + notes + _check_final_loudness(directory, record, page, directory / "work" / "motion.mp4")
    with _lock(key):
        if _cancelled(key):
            raise _Cancelled()                                   # Stop (or a newer start) arrived during the render: nothing of this run is kept
        record = load(directory)
        number = (record["versions"][-1]["n"] if record["versions"] else 0) + 1
        target = directory / f"v{number}"
        shutil.rmtree(target, ignore_errors=True)
        (directory / "work").replace(target)      # the files first, then the record that points at them
        record["versions"].append({"n": number, "created_at": time.time(), "change": change, "notes": notes, "models": used,
                                   **page.public(), "page": page.model_dump(exclude={"questions"})})
        record["versions"] = record["versions"][-MAX_VERSIONS:]
        record.update(current=number, status="completed", stage="completed", progress=100, message="", error=None, questions=[], pending_change=None, edit_pending=None, eta_s=None, eta_at=None)
        save(directory, record)
    _emit(cid, "motion.completed", motion_id=key, version=number, duration=page.duration, format=page.format)
    from app import studio_narrator
    studio_narrator.narrate(cid, user, "motion_ready", {"title": page.title, "duration_seconds": page.duration, "format": page.format, "what_it_shows": page.summary,
                            "changes_applied": change or None, "notes_from_the_automatic_check": notes[:3], "person_can_now": "ask for changes to text, colour, timing or size"},
                            fallback=(page.summary or f"موشن‌گرافیک {page.duration:g} ثانیه‌ای آماده شد.") + " اگر چیزی را می‌خواهید عوض کنم (متن، رنگ، زمان‌بندی، اندازه)، همین‌جا بنویسید.")


def _run_claude(directory: Path, record: dict, change: str) -> bool:
    """The whole film by the Claude motion engine (creative/claude_motion): True when a version was saved or questions were asked."""
    from creative import claude_motion
    from creative import motion_graphic as mg
    cid, user, key = record["conversation_id"], record["user_key"], record["id"]
    if change and not (directory / "claude_motion.json").is_file():
        return False                                  # a version made by the classic engine is revised by the classic engine

    def progress(percent: int, message: str) -> None:
        status = "rendering" if percent >= 66 else "checking" if percent >= 40 else "writing"
        _progress(directory, status, percent, message, stage=status)

    def publish_stills(built, lines) -> None:
        _publish_claude_snapshots(directory, built, lines)

    hooks = claude_motion.Hooks(note=lambda key_, text, state="active", detail=None: _note(directory, key_, text, state, detail=detail),
                                progress=progress, cancelled=lambda: _cancelled(key), snapshots=publish_stills,
                                say=lambda text: _assistant(cid, user, text))
    try:
        if record.get("intro") == "story":
            # a Story intro is a whole Claude-motion film made for this brand (creative/claude_intro.story_as_film), not the fixed Story template
            from creative import claude_intro
            _note(directory, "engine", "موتور «ویدیوی معرفی — قصه»: کارگردان برای همین برند داستان و طراحی تازه می‌نویسد، تصویرسازی‌ها جدا کشیده می‌شوند، هر صحنه جدا کدنویسی و با چشم بازبینی می‌شود", "done")
            result = claude_motion.build(directory, claude_intro.story_as_film(record, directory, hooks), hooks, change=change,
                                         reference_sheet=directory.parent.parent / "reference" / "frame-table.jpg")
        elif record.get("intro"):
            from creative import claude_intro
            _note(directory, "engine", f"موتور «ویدیوی معرفی» — سبک {claude_intro.LABELS.get(record['intro'], record['intro'])}: محتوا فقط از واقعیت‌های منبع، زمان‌بندی از صدا، استیل‌ها قبل از رندر بازبینی می‌شوند", "done")
            result = claude_intro.build(directory, record, hooks, change=change)
        elif record.get("vox"):
            from creative import claude_vox
            _note(directory, "engine", ("موتور اکسپلینر سه‌بعدی (ووکس ۳D): تحقیق و داستان مستند، صحنه‌های سه‌بعدی با دوربین متحرک، همه روی کلمه‌های نریشن" if claude_vox.wants_3d(record.get("request", ""))
                                        else "موتور «ووکس»: مستند توضیحی با سبکی که به موضوع می‌خورد — تحقیق و داستان مستند، تصویرها، علامت‌ها و عددها روی کلمه‌های نریشن"), "done")
            result = claude_vox.build(directory, record, hooks, change=change)
        else:
            _note(directory, "engine", "موتور «موشن کلاد»: یک مدل کل فیلم را یک‌جا کارگردانی و کدنویسی می‌کند", "done")
            result = claude_motion.build(directory, record, hooks, change=change, reference_sheet=directory.parent.parent / "reference" / "frame-table.jpg")
    except claude_motion.Cancelled:
        raise _Cancelled()
    if result.get("questions"):
        _ask(directory, record, result["questions"], change)
        return True
    if result.get("deferred"):
        with _lock(key):
            latest = load(directory)
            latest.update(status="rendering", stage="rendering", progress=66, message="پروژه آماده است؛ رندر بیرون از سرور انجام می‌شود.", claude_pending=change or True)
            save(directory, latest)
        return True
    _save_claude_version(directory, result["direction"], result["timing"], result["stills"], list(result.get("notes") or []), change)
    return True


def _publish_claude_snapshots(directory: Path, built: list, lines: list[str]) -> list[dict]:
    """Scene stills of a Claude-motion film (the settled moment of every scene) into snapshots/N.jpg and the record, so the chat shows them as soon as they exist."""
    shots = directory / "snapshots"
    shutil.rmtree(shots, ignore_errors=True)
    shots.mkdir(exist_ok=True)
    items = []
    finals = [(label, Path(path)) for label, path in built if not str(label).endswith("a")]
    for n, (label, path) in enumerate(finals, 1):
        if not path.is_file():
            continue
        shutil.copy2(path, shots / f"{n}.jpg")
        items.append({"n": n, "headline": (lines[n - 1] if n <= len(lines) else label)[:80], "t": 0})
    with _lock(directory.name):
        record = load(directory)
        record["snapshots"] = items
        save(directory, record)
    return items


def finish_claude_external(directory: Path, video: Path) -> None:
    """A Claude-motion film whose video was rendered outside this server (RunPod or a workstation): mix its sound and save it as the next version."""
    from creative import claude_motion
    record = load(directory)
    work = directory / "work"
    pending = json.loads((work / "pending.json").read_text())
    (work / "out").mkdir(exist_ok=True)
    shutil.copy2(video, work / "out" / "video.mp4")
    hooks = claude_motion.Hooks(note=lambda key_, text, state="active", detail=None: _note(directory, key_, text, state, detail=detail),
                                progress=lambda percent, message: _progress(directory, "rendering", percent, message, stage="rendering"),
                                cancelled=lambda: False)
    built = [(label, Path(path)) for label, path in pending["stills"]]
    if pending.get("intro"):
        from creative import claude_intro
        claude_intro.finish(work, pending["timing"], built, hooks)
    elif pending.get("vox"):
        from creative import claude_vox
        claude_vox.finish(work, pending["timing"], built, hooks)
    else:
        claude_motion.finish(work, pending["timing"], built, hooks)
    direction = claude_motion.Direction.model_validate(json.loads((directory / "claude_motion.json").read_text())["direction"])
    change = record.get("claude_pending")
    _save_claude_version(directory, direction, pending["timing"], built, list(pending.get("notes") or []), change if isinstance(change, str) else "")


def _save_claude_version(directory: Path, direction, timeline: dict, stills: list, notes: list[str], change: str) -> None:
    from creative import motion_graphic as mg
    record = load(directory)
    cid, user, key = record["conversation_id"], record["user_key"], record["id"]
    wide = float(timeline.get("width") or 1080) > float(timeline.get("height") or 1920)          # the landscape intro films (reel, presenter, film3d)
    page = mg.MotionPage(title=direction.title, summary=direction.summary, format="horizontal" if wide else "vertical", duration=timeline["total"])
    with _lock(key):
        if _cancelled(key):
            raise _Cancelled()
        record = load(directory)
        number = (record["versions"][-1]["n"] if record["versions"] else 0) + 1
        target = directory / f"v{number}"
        shutil.rmtree(target, ignore_errors=True)
        (directory / "work").replace(target)
        record["versions"].append({"n": number, "created_at": time.time(), "change": change, "notes": notes, "models": ["claude_intro_" + record["intro"] if record.get("intro") else "claude_vox" if record.get("vox") else "claude_motion"], "engine": "claude",
                                   **page.public(), "page": page.model_dump(exclude={"questions"})})
        record["versions"] = record["versions"][-MAX_VERSIONS:]
        record.update(current=number, status="completed", stage="completed", progress=100, message="", error=None, questions=[], pending_change=None, edit_pending=None,
                      eta_s=None, eta_at=None, claude_pending=None)
        save(directory, record)
    _emit(cid, "motion.completed", motion_id=key, version=number, duration=page.duration, format=page.format)
    from app import studio_narrator
    studio_narrator.narrate(cid, user, "motion_ready", {"title": page.title, "duration_seconds": page.duration, "format": page.format, "what_it_shows": page.summary,
                            "changes_applied": change or None, "notes_from_the_automatic_check": notes[:3], "person_can_now": "ask for changes to text, colour, timing or size"},
                            fallback=(page.summary or f"موشن‌گرافیک {page.duration:g} ثانیه‌ای آماده شد."))


def _ask(directory: Path, record: dict, questions: list[str], change: str = "") -> None:
    cid, user, key = record["conversation_id"], record["user_key"], record["id"]
    with _lock(key):
        latest = load(directory)
        latest.update(status="needs_input", stage="needs_input", progress=0, questions=questions, message="", pending_change=change or None)
        save(directory, latest)
    _emit(cid, "motion.questions", motion_id=key, questions=questions)
    _assistant(cid, user, "قبل از ساخت، این‌ها را لازم دارم:\n" + "\n".join(f"- {q}" for q in questions)
               + "\nاگر نمی‌خواهید جزئیات بدهید، بنویسید «خودت انتخاب کن» تا با متن عمومی و بدون عدد یا اسم ساختگی بسازم.")


def _fingerprint(*parts: str) -> str:
    import hashlib
    return hashlib.sha1("\x00".join(parts).encode()).hexdigest()[:12]


def _save_word_timing(directory: Path, texts: list[str], voice_id: str, voice_style: str, clip_starts: list, found: list | None = None):
    """Word and pause events of the narration, from the take's own timestamps, saved for scene design and captions. Never blocks the build."""
    try:
        from brain import localize
        from creative.audio import timing
        if found is None:
            found = localize.narration_words(texts, directory / "voice", voice_id, voice_style)
        rows = timing.events(found, clip_starts)
        (directory / "audio_timing.json").write_text(json.dumps({"source": "provider character timestamps", "events": [r.model_dump() for r in rows]}, ensure_ascii=False))
        return found
    except Exception as exc:
        log.debug("word timing not saved: %s", str(exc)[:100])
    return None


def _partial_clips(directory: Path, texts: list[str], voice_id: str, voice_style: str):
    """When only some narrated lines changed since the last take (same voice and style), voice just those and keep the rest. Returns
    {"clips", "words", "changed"} or None (then the whole narration is voiced as before). Any failure here means None, never a half-made result."""
    from creative.audio import partial
    try:
        previous = json.loads((directory / "voice_takes.json").read_text())
        if previous.get("voice") != [voice_id, voice_style] or len(previous.get("texts", [])) != len(texts):
            return None
        changed = partial.changed_lines(previous["texts"], texts)
        kept = [i for i in range(len(texts)) if i not in changed and texts[i].strip()]
        if not changed or not kept:
            return None
        old = [(Path(path), float(seconds)) for path, seconds in previous["clips"]]
        if any(not old[i][0].is_file() for i in kept):
            return None
        from brain import localize
        words = previous.get("words") if len(previous.get("words") or []) == len(texts) else [[] for _ in texts]
        clips = list(old)
        for i in changed:
            if not texts[i].strip():
                clips[i], words[i] = (old[i][0], 0.0), []
                continue
            line_dir = directory / "voice" / f"line{i + 1}-{_fingerprint(texts[i])[:8]}"
            fresh = _with_retries(lambda: localize.synthesize_narration([texts[i]], line_dir, voice_id, voice_style))[0]
            leveled, _ = partial.match_level(old[kept[0]][0], Path(fresh[0]), line_dir / "leveled.wav")
            clips[i] = (leveled, localize.audio_duration(leveled) if leveled != Path(fresh[0]) else fresh[1])
            words[i] = localize.narration_words([texts[i]], line_dir, voice_id, voice_style)[0]
        return {"clips": clips, "words": words, "changed": changed}
    except _Cancelled:
        raise
    except Exception as exc:
        log.warning("partial narration not used: %s", str(exc)[:160])
        return None


def _save_takes(directory: Path, texts: list[str], voice_id: str, voice_style: str, clips, words) -> None:
    """The lines and clips of this take, so a later change to a few lines can keep the others."""
    try:
        (directory / "voice_takes.json").write_text(json.dumps({"voice": [voice_id, voice_style], "texts": texts, "words": words,
                                                                "clips": [[str(path), seconds] for path, seconds in clips]}, ensure_ascii=False))
    except OSError:
        log.debug("narration takes not saved")


def _gate_clips(plan, clips) -> list[str]:
    """Objective checks on each narrated scene (clipping, silence, an unreadable file). Problems are reported; the build goes on."""
    from creative.audio import quality
    notes = []
    for number, (scene, (path, seconds)) in enumerate(zip(plan.scenes, clips), 1):
        if not scene.narration.strip():
            continue
        try:
            report = quality.analyse(Path(path), expected_duration_s=None)
        except Exception as exc:                                  # a failing check must not stop the video
            log.debug("audio check failed: %s", str(exc)[:120]); continue
        for warning in report["warnings"]:
            if warning["code"] in {"missing_or_empty", "unreadable", "silent", "clipping", "excess_silence"}:
                notes.append(f"صدای صحنهٔ {number}: {warning['message']}")
    return notes


_PERMANENT = re.compile(r"\b(401|402|403|unauthori[sz]ed|forbidden|quota|insufficient|invalid[_ ]api[_ ]key|payment)\b", re.I)


def _with_retries(call, attempts: int = 3, pause=time.sleep):
    """A provider call that fails on the network (DNS, timeout, reset) is tried again a couple of times; a refusal that
    repeating cannot fix (key, quota, payment) is raised at once."""
    for number in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:
            if number == attempts or _PERMANENT.search(str(exc)):
                raise
            log.warning("provider call failed (%s), attempt %d of %d: %s", type(exc).__name__, number, attempts, str(exc)[:120])
            pause(2 * number)


def _save_audio_direction(directory: Path, record: dict, plan, texts: list[str]) -> None:
    """Write the director's audio plan, per-line emotion arc and sound-design cues next to the project. Informational: it never changes the
    audio and a failure here never stops the build."""
    try:
        from creative.audio import direction, sound_design
        from creative.audio.contracts import AudioDirectionPlan
        audio_plan = AudioDirectionPlan.model_validate(record.get("audio_plan") or {})
        scenes = plan.scenes
        moments = [{"time_ms": int(scene.start * 1000), "kind": "reveal" if i == len(scenes) - 1 and len(scenes) > 1 else "transition",
                    "importance": 0.9 if i == len(scenes) - 1 else 0.4} for i, scene in enumerate(scenes) if i > 0]
        cues = sound_design.plan(moments, audio_plan.sound_design, [], total_ms=int(plan.duration * 1000))
        (directory / "audio_direction.json").write_text(json.dumps(
            {"plan": audio_plan.model_dump(), "notes": record.get("audio_plan_notes", []), "emotion_arc": direction.emotion_arc(texts, audio_plan),
             "sound_design": cues}, ensure_ascii=False))
    except Exception as exc:
        log.warning("audio direction not saved: %s", str(exc)[:160])


def _narrate(directory: Path, record: dict, plan, fp: str):
    """Voice every scene (one ElevenLabs request, cut per scene), then retime the plan so each scene lasts as long as its narration plus a breath.
    Returns (plan, clips, notes). A narration that cannot be made leaves the clip silent and says so; it never stops the build."""
    from creative import motion_graphic as mg
    voice_id, voice_style = record.get("voice_id", ""), record.get("voice_style", "")
    if not voice_id:                                          # «با صدای من» in the request: the person's own cloned voice (also when an older run is retried)
        from brain import localize as _voices
        voice_id = _voices.narrator_for(record.get("request", ""), record.get("user_key"))
    pronunciations = record.get("pronunciations") or {}
    fp = f"{fp}|{_fingerprint(json.dumps(pronunciations, sort_keys=True, ensure_ascii=False))}" if pronunciations else fp
    saved = directory / "voice.json"
    try:
        cached = json.loads(saved.read_text())
        if cached.get("fp") == f"{fp}|{voice_id}|{voice_style}|{_TAKE}":
            return mg.MotionPlan.model_validate(cached["plan"]), cached["audio"], cached.get("notes", [])
    except (OSError, ValueError):
        pass
    from creative.audio import persian
    # What is spoken is derived from the script (digits spelled out, the project's pronunciation entries); the script itself is untouched.
    texts = [persian.speakable(scene.narration, pronunciations) if scene.narration.strip() else scene.narration for scene in plan.scenes]
    try:
        from creative.audio import pronounce
        texts = [new if old.strip() else old for old, new in zip(texts, pronounce.prepare(texts, route=os.environ.get("CLAUDE_MOTION_ROUTE", "motion_graphic_planner")))]
    except Exception:
        log.warning("pronunciation pass skipped", exc_info=True)
    if not any(text.strip() for text in texts):
        return plan, [], []
    _soft_progress(directory, 7, "دارم نریشن صحنه‌ها را با صدای انتخابی می‌سازم.")
    _note(directory, "voice", "دارم نریشن صحنه‌ها را با صدای انتخابی می‌سازم")
    if all(text.strip() for text in texts):
        try:
            from brain import localize
            take = _with_retries(lambda: localize.continuous_narration(texts, directory / "voice", voice_id, voice_style))
            return _fit_to_take(directory, record, plan, texts, take, fp, voice_id, voice_style)
        except _Cancelled:
            raise
        except Exception as exc:
            # No quiet return to the old line-by-line voicing (that is what sounded cut up): the failure is shown in the log and stops the build.
            log.warning("continuous narration failed: %s", str(exc)[:200])
            reason = ("اعتبار ElevenLabs کافی نیست" if "quota" in str(exc).lower() else "نریشن پیوسته ساخته نشد") + f" ({str(exc)[:140]})"
            _note(directory, "voice", "ساخت نریشن پیوسته ناموفق بود؛ ساخت متوقف شد", "done", detail=reason)
            _remember_voice_error(directory, record, f"{type(exc).__name__}: {str(exc)[:200]}")
            raise RuntimeError(f"ساخت نریشن انجام نشد: {reason}. دوباره امتحان کنید.") from exc
    partial = None
    try:
        from brain import localize
        partial = _partial_clips(directory, texts, voice_id, voice_style)
        clips = partial["clips"] if partial else _with_retries(lambda: localize.synthesize_narration(texts, directory / "voice", voice_id, voice_style))
    except Exception as exc:
        log.warning("motion narration could not be made: %s", str(exc)[:200])
        reason = ("اعتبار ElevenLabs کافی نیست" if "quota" in str(exc).lower() else "ارائه‌دهندهٔ صدا پاسخ نداد") + f" ({str(exc)[:120]})"
        _note(directory, "voice", "ساخت نریشن انجام نشد؛ ساخت متوقف شد", "done", detail=reason)
        _remember_voice_error(directory, record, f"{type(exc).__name__}: {str(exc)[:200]}")
        # a reel without its voice is not what was asked for: the build stops with the reason (the plan is kept, so retrying starts from the voice)
        raise RuntimeError(f"ساخت نریشن انجام نشد: {reason}. دوباره امتحان کنید؛ ویدیو بی‌صدا ساخته نمی‌شود.")
    _remember_voice_error(directory, record, None)
    if partial:
        verified = ["نریشن فقط برای صحنه‌های " + "، ".join(str(i + 1) for i in partial["changed"]) + " دوباره ساخته شد؛ بقیهٔ صحنه‌ها همان صدای قبلی را نگه داشتند."]
    else:
        clips, verified = _verify_clips(directory, record, texts, clips, voice_id, voice_style)
    gate_notes = [*_gate_clips(plan, clips), *verified]
    cursor, scenes, audio, clip_starts = 0.0, [], [], []
    for index, (scene, (path, seconds)) in enumerate(zip(plan.scenes, clips)):
        last = index == len(plan.scenes) - 1
        # A scene lasts as long as its narration plus a breath that outlasts the next entrance (it starts 0.9 s early): it shrinks when the
        # planned length was longer, instead of leaving seconds of silence after every line. A scene without narration keeps its planned length.
        length = seconds + 0.25 + 1.2 + (0.8 if last else 0.0) if seconds > 0 else scene.end - scene.start
        scenes.append(scene.model_copy(update={"start": round(cursor, 2), "end": round(cursor + length, 2)}))
        if seconds > 0:
            audio.append({"path": str(path), "start": round(cursor + 0.25, 2), "duration": round(seconds, 2)})
        clip_starts.append(round(cursor + 0.25, 2) if seconds > 0 else None)
        cursor += length
    found = _save_word_timing(directory, texts, voice_id, voice_style, clip_starts, partial["words"] if partial else None)
    _save_takes(directory, texts, voice_id, voice_style, clips, found if found is not None else [[] for _ in texts])
    if cursor > mg.MAX_SECONDS:
        _note(directory, "voice", "نریشن از حد مجاز طولانی‌تر شد؛ ساخت متوقف شد", "done", detail=f"{cursor:.0f} ثانیه از سقف {mg.MAX_SECONDS:.0f} ثانیه")
        raise RuntimeError(f"نریشن {cursor:.0f} ثانیه شد و از سقف {mg.MAX_SECONDS:.0f} ثانیه گذشت؛ نریشن را کوتاه‌تر کنید.")
    retimed = plan.model_copy(update={"scenes": scenes, "duration": round(cursor, 2)})
    _save_audio_direction(directory, record, retimed, texts)
    saved.write_text(json.dumps({"fp": f"{fp}|{voice_id}|{voice_style}|{_TAKE}", "plan": retimed.model_dump(), "audio": audio, "notes": gate_notes}, ensure_ascii=False))
    _note(directory, "voice", f"نریشن آماده شد: {sum(c['duration'] for c in audio):.0f} ثانیه صدا، ویدیو {cursor:.0f} ثانیه", "done",
          detail=f"راوی: {voice_id or 'پیش‌فرض'} · سبک: {voice_style or 'طبیعی'}\n" + "\n".join(f"{i}. ({c['duration']:.1f} s) {t}" for i, (c, t) in enumerate(zip(audio, [t for t in texts if t.strip()]), 1)))
    return retimed, audio, gate_notes


_TAKE = "take2"            # the narration is one continuous reading (a change of method invalidates saved per-line takes)
_PREROLL = 0.3             # silence before the voice starts (kept for tests; the shared value lives in creative.narration_take)
_LEAD = 0.35


def _fit_to_take(directory: Path, record: dict, plan, texts: list[str], take: dict, fp: str, voice_id: str, voice_style: str):
    """The scenes follow the voice, not the other way round (see creative.narration_take)."""
    from creative import motion_graphic as mg
    from creative import narration_take
    fitted = narration_take.fit(take)
    if fitted["duration"] > mg.MAX_SECONDS:
        raise RuntimeError(f"نریشن {fitted['duration']:.0f} ثانیه شد و از سقف {mg.MAX_SECONDS:.0f} ثانیه گذشت؛ نریشن را کوتاه‌تر کنید.")
    retimed = narration_take.apply(plan, fitted)
    audio = fitted["audio"]
    _save_word_timing(directory, texts, voice_id, voice_style, fitted["clip_starts"], fitted["relative"])
    try:
        (directory / "voice_takes.json").unlink()                 # the per-line takes of the old method must not be mixed with this one
    except OSError:
        pass
    _remember_voice_error(directory, record, None)
    _save_audio_direction(directory, record, retimed, texts)
    notes = ["نریشن یک اجرای پیوسته است؛ صحنه‌ها با زمان واقعی کلمات تنظیم شدند."]
    (directory / "voice.json").write_text(json.dumps({"fp": f"{fp}|{voice_id}|{voice_style}|{_TAKE}", "plan": retimed.model_dump(), "audio": audio, "notes": notes}, ensure_ascii=False))
    _note(directory, "voice", f"نریشن آماده شد: یک اجرای پیوسته، {take['total']:.0f} ثانیه صدا، ویدیو {fitted['duration']:.0f} ثانیه", "done",
          detail=f"راوی: {voice_id or 'پیش‌فرض'} · سبک: {voice_style or 'طبیعی'}\n" + "\n".join(f"{i}. [{b:.1f}–{e:.1f}s] {t}" for i, (b, e, t) in enumerate(zip(fitted["starts"], fitted["ends"], texts), 1)))
    return retimed, audio, notes


def _advice_text(advice: dict) -> str:
    if not advice or advice.get("error"):
        return ""
    return f"title_font={advice.get('title_font') or '-'}; body_font={advice.get('body_font') or '-'}; accent={advice.get('accent_font') or '-'}; because {advice.get('why', '')}"


def _font_advice(directory: Path, brief: str, reference_sheet=None) -> dict:
    """The vision model looks at the specimen sheets of the font library and recommends the film's fonts: one visible step with what it saw (a failure is shown, the planner then chooses from the list)."""
    from creative import font_catalog
    _note(directory, "fonts", "دارم نمونهٔ فونت‌های کتابخانه را می‌بینم و فونت مناسب این فیلم را انتخاب می‌کنم", request=brief[:600])
    advice = font_catalog.advise(brief, reference_sheet=reference_sheet)
    if advice.get("error") or not advice:
        reason = advice.get("error") or "پاسخی نیامد"
        _note(directory, "fonts", "انتخاب فونت با مدل بینایی انجام نشد؛ طراح برنامه از روی فهرست فونت‌ها انتخاب می‌کند", "done", detail=str(reason)[:400])
        return {}
    def label(font_id: str) -> str:
        font = font_catalog.get(font_id)
        return f"{font['label']} ({font['family']})" if font else "—"
    _note(directory, "fonts", f"فونت پیشنهادی: تیتر «{label(advice.get('title_font', ''))}» و متن «{label(advice.get('body_font', ''))}»", "done",
          detail=f"تیتر: {label(advice.get('title_font', ''))}\nمتن: {label(advice.get('body_font', ''))}\nتأکیدی: {label(advice.get('accent_font', ''))}\n\n{advice.get('why', '')}")
    return advice


def _plan_detail(brief: str, plan) -> str:
    """The request the planner was given (start of the brief) and what it decided, scene by scene."""
    scenes = "\n".join(f"{i}. {sc.headline}  [{sc.start:g}–{sc.end:g} s]\n   {sc.idea}\n   «{sc.narration}»" if sc.narration else f"{i}. {sc.headline}  [{sc.start:g}–{sc.end:g} s]\n   {sc.idea}"
                        for i, sc in enumerate(plan.scenes, 1))
    from creative import font_catalog
    title, body = font_catalog.get(plan.title_font), font_catalog.get(plan.body_font)
    fonts = f"\nفونت‌ها: تیتر «{title['label'] if title else '—'}» · متن «{body['label'] if body else '—'}»" + (f" — {plan.font_why}" if plan.font_why else "")
    skills = ("\nمهارت‌های طراحی انتخاب‌شده: " + "، ".join(plan.skills)) if getattr(plan, "skills", None) else ""
    return f"درخواست:\n{brief.strip()[:900]}\n\nطرح: «{plan.title}» · {plan.format} · {plan.duration:g} ثانیه{fonts}{skills}\n{scenes}"


def _soft_progress(directory: Path, percent: int, message: str) -> None:
    """A progress update for a step inside narration; a project folder without a record (a unit of work run on its own) is not an error."""
    try:
        _progress(directory, "writing", percent, message, stage="writing")
    except FileNotFoundError:
        pass


def _soft_note(directory: Path, key: str, text: str, state: str = "active", detail: str | None = None) -> None:
    try:
        _note(directory, key, text, state, detail)
    except FileNotFoundError:
        pass


def _snapshot_scenes(directory: Path, work: Path, plan) -> None:
    """One still per scene (at 86 % of the scene, where every element has entered and none has left) from the checked page, so the person sees the design
    while the video renders. Bounded, never costs the build, and never uses the vision-model description."""
    try:
        from engine.hyperframes.cli import cli_command
        scenes = list(getattr(plan, "scenes", None) or [])
        if not scenes:
            return
        times = [round(min(scene.start + (scene.end - scene.start) * 0.86, plan.duration - 0.1), 2) for scene in scenes]
        shots = directory / "snapshots"
        raw = work / ".snapshots"
        shutil.rmtree(raw, ignore_errors=True); shots.mkdir(exist_ok=True); raw.mkdir(parents=True)
        done = subprocess.run([*cli_command(), "snapshot", ".", "--at", ",".join(f"{t:g}" for t in times), "--no-end", "--keep", "--describe", "false", "-o", str(raw)],
                              cwd=work, capture_output=True, text=True, timeout=150, env={**os.environ, "NO_COLOR": "1"})
        items = []
        for n, (scene, t) in enumerate(zip(scenes, times), 1):
            source = raw / f"at-{t:g}s.png"
            if not source.is_file():
                continue
            target = shots / f"{n}.jpg"
            made = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-vf", "scale=640:-2", "-q:v", "5", str(target)], capture_output=True, timeout=60)
            if made.returncode == 0 and target.is_file():
                items.append({"n": n, "headline": scene.headline[:80], "t": t})
        if not items:
            log.warning("scene snapshots not made: %s", (done.stderr or done.stdout or "")[-200:])
            return
        with _lock(directory.name):
            record = load(directory)
            record["snapshots"] = items
            save(directory, record)
        _note(directory, "snapshots", f"عکس {len(items)} صحنه آماده شد", "done")
    except Exception as exc:
        log.warning("scene snapshots failed: %s", str(exc)[:160])


def _blank_scenes(directory: Path) -> list[int]:
    """Scenes whose still (taken where the scene's text and motion should be in place) shows nothing: a black or single-colour frame."""
    blank: list[int] = []
    try:
        from PIL import Image, ImageStat
        for item in load(directory).get("snapshots") or []:
            path = directory / "snapshots" / f"{item['n']}.jpg"
            if not path.is_file():
                continue
            gray = Image.open(path).convert("L")
            stat = ImageStat.Stat(gray)
            if stat.mean[0] < 14 or stat.stddev[0] < 4:
                # A thin-line drawing on a dark ground has a tiny mean and spread yet is far from empty: judge by how much of the frame differs from the ground.
                histogram = gray.histogram()
                total = sum(histogram) or 1
                ground = next((v for v in range(256) if sum(histogram[:v + 1]) >= total / 2), 0)
                ink = sum(histogram[v] for v in range(256) if abs(v - ground) > 40) / total
                if ink < 0.0015:
                    blank.append(int(item["n"]))
    except Exception as exc:
        log.warning("scene stills could not be checked for blank frames: %s", str(exc)[:120])
    return blank


_TEXT_OVERLAP = re.compile(r"content_overlap|text_occluded")


def _remember_voice_error(directory: Path, record: dict, message: str | None) -> None:
    """Keep the narration problem in the saved record (the chat agent reads it); clear it once narration works."""
    if message: record["voice_error"] = message
    else: record.pop("voice_error", None)
    try:
        with _lock(directory.name):
            saved = load(directory)
            if message: saved["voice_error"] = message
            else: saved.pop("voice_error", None)
            save(directory, saved)
    except Exception as exc:                                    # remembering must never cost the build
        log.debug("voice error not stored: %s", str(exc)[:100])


_VOICE_CHANGE = re.compile(r"نریشن|نریشین|روایت|گوینده|راوی|لحن|صدا|voice|narrat|speech|audio|tts", re.I)
_LOOK_CHANGE = re.compile(r"رنگ|متن|فونت|اندازه|سایز|زمان|سرعت|انیمیشن|تصویر|color|colour|text|font|size|timing|speed|animation|image", re.I)


def _revoice(directory: Path, record: dict, previous):
    """A change about the voice: voice the saved plan again and put the audio on the clip's current page, without redesigning anything.
    Returns (page, notes), or None when the narration moved the scene timing (then the clip has to be rebuilt). Raises when no audio can be made,
    so a request to fix the voice never ends in another silent version."""
    from creative import motion_graphic as mg
    try:
        saved = json.loads((directory / "plan.json").read_text())
        plan = mg.MotionPlan.model_validate(saved["plan"])
    except (OSError, ValueError, KeyError):
        return None
    if not any(scene.narration.strip() for scene in plan.scenes):
        return None
    (directory / "voice.json").unlink(missing_ok=True)           # an explicit request to voice it again never reuses an earlier result
    (directory / "voice_takes.json").unlink(missing_ok=True)
    voiced, audio, notes = _narrate(directory, record, plan, saved.get("fp", ""))
    if not audio:
        raise RuntimeError("نریشن ساخته نشد: " + (notes[0] if notes else "دلیلش ثبت نشد") + " (نسخهٔ بی‌صدای دیگری ساخته نمی‌شود؛ بعداً دوباره تلاش کنید)")
    if [(sc.start, sc.end) for sc in voiced.scenes] != [(sc.start, sc.end) for sc in plan.scenes]:
        return None
    audio, music_notes = _add_music(directory, record, voiced, audio)
    audio, master_notes = _master_audio(directory, record, voiced, audio)
    return previous.model_copy(update={"audio": audio}), [*notes, *music_notes, *master_notes]


def _merge_report(directory: Path, **sections) -> None:
    """Add sections to audio_report.json (measurements stay apart from any model's judgement)."""
    path = directory / "audio_report.json"
    try: report = json.loads(path.read_text())
    except (OSError, ValueError): report = {}
    report.update(sections)
    try: path.write_text(json.dumps(report, ensure_ascii=False))
    except OSError: log.debug("audio report not written")


def _master_audio(directory: Path, record: dict, plan, audio: list[dict]):
    """Mix the narration and the music bed into one track at the delivery loudness. Any failure keeps the separate tracks (the film is
    never left without sound because the mastering failed). Returns (audio, notes)."""
    from creative.audio import loudness, mixer
    preset = record.get("loudness") or "social_video"
    voice = [clip for clip in audio if clip.get("role") not in {"music", "master"}]
    if preset == "off" or not voice or preset not in loudness.PRESETS:
        return audio, []
    music = next((clip for clip in audio if clip.get("role") == "music"), None)
    try:
        result = mixer.master(voice, music, plan.duration, directory / "master.m4a", preset)
    except Exception as exc:
        log.warning("master mix failed: %s", str(exc)[:200])
        return audio, ["میکس نهایی انجام نشد؛ صدا بدون نرمال‌سازی استفاده شد: " + str(exc)[:120]]
    _merge_report(directory, mix={"preset": preset, **result})
    before, after, target = result["before"]["integrated_lufs"], result["after"]["integrated_lufs"], result["target"]["lufs"]
    return ([{"path": str(directory / "master.m4a"), "start": 0, "duration": plan.duration, "role": "master"}],
            [f"میکس نهایی: لودنس {before:.1f} به {after:.1f} LUFS رسید (هدف {target:g}، true peak {result['after']['true_peak_dbtp']:.1f} dBTP)"])


def _check_final_loudness(directory: Path, record: dict, page, mp4: Path) -> list[str]:
    """Measure the rendered file itself and report when it is off the delivery target. Measurement only; never blocks the version."""
    if not page.audio or (record.get("loudness") or "social_video") in {"off", None}:
        return []
    from creative.audio import loudness, mixer
    preset = record.get("loudness") or "social_video"
    try:
        measured = loudness.measure(mp4)
    except Exception as exc:
        log.debug("final loudness not measured: %s", str(exc)[:100]); return []
    _merge_report(directory, final={"preset": preset, **measured})
    if measured.get("silent"):
        return ["ویدیوی رندرشده بی‌صدا است، با اینکه صدا اضافه شده بود."]
    if preset in loudness.PRESETS and not mixer.within_target(measured["integrated_lufs"], preset):
        return [f"لودنس ویدیوی نهایی {measured['integrated_lufs']:.1f} LUFS است و از هدف {loudness.PRESETS[preset][0]:g} دور است."]
    return []


VERIFY_WALL_S = 90.0


def _verify_clips(directory: Path, record: dict, texts: list[str], clips, voice_id: str, voice_style: str):
    """Speech recognition on each narrated scene against the script; a scene that fails is voiced once more. Returns (clips, notes).
    A check that cannot run is skipped quietly in the notes; it never blocks the video."""
    import os
    if os.environ.get("AUDIO_VERIFY_NARRATION", "1") == "0" or sum(len(t) for t in texts) > 4000:
        return clips, []
    from brain import localize
    from creative.audio import persian, verify
    language = "fa" if any(persian.is_persian(t) for t in texts) else "en"
    work = directory / "verify"

    def recognise(path: Path, index: int):
        from brain import transcribe
        out = work / f"s{index + 1}"
        found = transcribe.transcribe(Path(path), out, language=language)
        words = found.get("words") or []
        return " ".join(str(w.get("text") or w.get("word") or "") for w in words).strip() or (found.get("text") or "")

    def regenerate(index: int):
        try:
            return localize.synthesize_narration([texts[index]], directory / "voice" / f"retry{index + 1}", voice_id, voice_style)[0]
        except Exception as exc:
            log.warning("narration retry failed: %s", str(exc)[:160]); return None
    _soft_progress(directory, 8, "دارم صدای نریشن را با متن سناریو مقایسه می‌کنم.")
    _soft_note(directory, "verify", "دارم صدای نریشن را با متن سناریو مقایسه می‌کنم (حداکثر یک دقیقه و نیم)")
    # A recogniser that is slow or down must not hold the clip: the check runs in a worker thread with a wall-clock limit. On timeout the
    # worker is left to finish by itself (it writes only into its own folder) and the narration is used as it is, marked "not checked".
    import concurrent.futures
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="verify")
    try:
        fixed, report = pool.submit(verify.verify_clips, texts, clips, recognise, regenerate).result(timeout=VERIFY_WALL_S)
    except concurrent.futures.TimeoutError:
        log.warning("narration verification used up %.0f s and was skipped", VERIFY_WALL_S)
        _soft_note(directory, "verify", "مقایسهٔ صدا با سناریو به‌موقع تمام نشد؛ نریشن همان‌طور که ساخته شد استفاده می‌شود", "done")
        try:
            (directory / "audio_report.json").write_text(json.dumps({"recognition": [{"scene": i + 1, "status": "not_checked", "reason": "time limit"} for i, t in enumerate(texts) if t.strip()],
                                                                    "judgement": "recognition is evidence, not proof of pronunciation"}, ensure_ascii=False))
        except OSError:
            pass
        return clips, ["مقایسهٔ خودکار صدا با سناریو انجام نشد (زمان تمام شد)."]
    except Exception as exc:
        log.warning("narration verification failed: %s", str(exc)[:160])
        return clips, []
    finally:
        pool.shutdown(wait=False)
    _soft_note(directory, "verify", "مقایسهٔ صدا با سناریو تمام شد", "done")
    try:
        (directory / "audio_report.json").write_text(json.dumps({"recognition": report, "judgement": "recognition is evidence, not proof of pronunciation"}, ensure_ascii=False))
    except OSError:
        pass
    notes = []
    for row in report:
        if row["status"] == "needs_review":
            notes.append(f"صدای صحنهٔ {row['scene']} با متن اسکریپت نمی‌خواند ({row['error']:.0%} اختلاف)" + ("؛ یک بار دوباره تولید شد" if row["retried"] else "") + ". گوش بدهید و در صورت نیاز تلفظ را با Pronounce: اصلاح کنید.")
        elif row["status"] == "repaired":
            notes.append(f"صدای صحنهٔ {row['scene']} بار اول با اسکریپت نمی‌خواند و دوباره تولید شد.")
    return fixed, notes


MUSIC_MODES = {"attached", "library", "auto", "search", "generate"}


def _music_request(record: dict, plan, accent_s: float | None = None):
    from creative.audio import music_director as md
    music = record.get("music") or {}
    audio_plan = record.get("audio_plan") or {}
    energy = music.get("energy") if music.get("energy") is not None else audio_plan.get("music_energy")
    words = " ".join(filter(None, [music.get("words", ""), audio_plan.get("music_mood", "")])).strip()
    return md.MusicRequest(brief=record.get("request", ""), words=words, duration_s=float(plan.duration) + 3.0, mode=music.get("mode") or "auto", style=music.get("style", ""),
                           energy=energy, instrumental=bool(music.get("instrumental", True)), accent_s=accent_s, cost=music.get("cost", "balanced"), path=music.get("path", ""),
                           name=music.get("name", ""), user=str(record.get("user_key", "")), variant=int(music.get("variant") or 0), exclude=list(music.get("used") or []))


def _resolve_music(directory: Path, record: dict, plan, accent_s: float | None = None):
    """The music of this film, decided once (and kept in music_choice.json, so a retry or an edit of something else never makes or pays for it again)."""
    from creative.audio import music_director as md
    request = _music_request(record, plan, accent_s)
    stamp = json.dumps([request.mode, request.words, request.style, request.energy, request.instrumental, request.cost, request.path, request.variant, request.exclude,
                        int(plan.duration // 10)], ensure_ascii=False, default=str)
    saved = directory / "music_choice.json"
    try:
        cached = json.loads(saved.read_text())
        if cached.get("stamp") == stamp and cached.get("path") and Path(cached["path"]).is_file():
            return md.Result(path=Path(cached["path"]), label=cached["label"], source=cached["source"], notes=cached.get("notes", []), reasons=cached.get("reasons", []),
                             attribution=cached.get("attribution"), cost=cached.get("cost"), style=cached.get("style", ""), arc=cached.get("arc", []), track=cached.get("track"))
    except (OSError, ValueError):
        pass

    def progress(text: str, state: str = "active") -> None:
        try: _note(directory, "music", text, state)
        except _Cancelled: raise
        except Exception: log.debug("music progress line not stored")
    chosen = md.resolve(request, progress=progress)
    if chosen.path:
        small = {k: v for k, v in (chosen.track or {}).items() if k in {"id", "source", "provider", "title", "artist", "license", "rights", "cost", "duration_s"}}
        saved.write_text(json.dumps({"stamp": stamp, "path": str(chosen.path), "label": chosen.label, "source": chosen.source, "notes": chosen.notes, "reasons": chosen.reasons,
                                     "attribution": chosen.attribution, "cost": chosen.cost, "style": chosen.style, "arc": chosen.arc, "track": small}, ensure_ascii=False))
    return chosen


def _sync_rhythm_waiting(directory: Path, record: dict, plan, audio: list[dict], wanted: dict, mode: str):
    """Balanced / music-first without Sync to Beat: a scene start waits (never moves earlier) for a near beat of the track, which starts at its beginning. Returns (plan, audio, notes)."""
    from creative import motion_graphic as mg
    from creative.audio import music_director as md, rhythm
    try:
        choice = _resolve_music(directory, record, plan, None)
        if choice.path is None:
            return plan, audio, []
        analysis = rhythm.analyse(choice.path, cache_dir=directory)
        if analysis["bpm_confidence"] < 0.2 or len(analysis["beats_ms"]) < 8:
            return plan, audio, [f"ضرب موسیقی «{choice.label}» قابل اتکا تشخیص داده نشد؛ زمان‌بندی بر پایهٔ گفتار ماند."]
        starts = [sc.start for sc in plan.scenes]
        new_starts, total, on_beat = rhythm.snap_starts(starts, plan.duration, analysis["beats_ms"], 0.35 if mode == "balanced" else 0.9, mg.MAX_SECONDS)
        if not on_beat:
            return plan, audio, [f"موسیقی {analysis['bpm']:.0f} BPM؛ هیچ صحنه‌ای بدون تأخیر زیاد روی بیت نیامد، زمان‌بندی بر پایهٔ گفتار ماند."]
        scenes = []
        for index, scene in enumerate(plan.scenes):
            end = new_starts[index + 1] if index + 1 < len(plan.scenes) else total
            scenes.append(scene.model_copy(update={"start": new_starts[index], "end": round(end, 3)}))
        moved = []
        for clip in audio:
            owner = next((i for i, sc in enumerate(plan.scenes) if sc.start - 1e-6 <= clip["start"] < sc.end + 1e-6), None)
            moved.append({**clip, "start": round(clip["start"] + (new_starts[owner] - starts[owner]), 2)} if owner is not None else clip)
        return plan.model_copy(update={"scenes": scenes, "duration": round(total, 2)}), moved, [f"موسیقی {analysis['bpm']:.0f} BPM؛ شروع {len(on_beat)} صحنه روی بیت قرار گرفت (فیلم {total - plan.duration:+.1f} ثانیه)"]
    except _Cancelled:
        raise
    except Exception as exc:
        log.warning("rhythm sync skipped: %s", str(exc)[:160])
        return plan, audio, []


def _sync_rhythm(directory: Path, record: dict, plan, audio: list[dict]):
    """The rhythm of the film's own music meets the film. Always free of cost to the narration: the music is slid (trimmed), never stretched, so that the track's drop lands on the
    film's accent (its last scene) or, without a drop, so that its beat grid falls on as many cuts as possible; and in balanced / music-first mode a scene start waits (never moves
    earlier) for a near beat. Returns (plan, audio, notes). The fit is saved in music_fit.json for the music bed."""
    mode = record.get("rhythm") or "speech_first"
    wanted = record.get("music") or {}
    if wanted.get("mode") not in MUSIC_MODES:
        return plan, audio, []
    if not wanted.get("sync"):
        if mode not in {"balanced", "music_first"}:
            return plan, audio, []
        return _sync_rhythm_waiting(directory, record, plan, audio, wanted, mode)          # the original rule, unchanged, for music the person attached or chose from the library
    from creative import motion_graphic as mg
    from creative.audio import music_director as md, music_fit, rhythm
    notes: list[str] = []
    try:
        starts = [sc.start for sc in plan.scenes]
        accent_s = starts[-1] if len(starts) >= 2 else None
        choice = _resolve_music(directory, record, plan, accent_s)
        notes += choice.notes
        if choice.path is None:
            return plan, audio, notes
        analysis = md.analysis_for(choice.path)
        if not analysis or analysis.get("bpm_confidence", 0) < 0.2 or len(analysis.get("beats_ms", [])) < 8:
            music_fit_path = directory / "music_fit.json"
            music_fit_path.write_text(json.dumps({"offset_s": 0.0, "anchor": None, "loop": None, "notes": []}))
            return plan, audio, [*notes, f"ضرب موسیقی «{choice.label}» قابل اتکا تشخیص داده نشد؛ زمان‌بندی بر پایهٔ گفتار ماند."]
        analysis, choice = _lengthen_buildup(directory, choice, analysis, accent_s, notes)
        solved = music_fit.solve(analysis, starts, float(plan.duration), snap=mode in {"balanced", "music_first"}, tolerance_s=0.35 if mode == "balanced" else 0.9, max_total_s=mg.MAX_SECONDS)
        fit, new_starts, total = solved["fit"], solved["starts"], solved["total"]
        (directory / "music_fit.json").write_text(json.dumps(fit))
        notes += [f"موسیقی {analysis['bpm']:.0f} BPM (اطمینان ضرب {analysis.get('beat_confidence', 0):.0%})"]
        for n in fit.get("notes", []):
            notes.append("دراپ موسیقی روی لحظهٔ اوج فیلم (شروع صحنهٔ آخر) قرار گرفت" if "lands on the film's accent" in n else
                         f"موسیقی {fit['offset_s']:.2f} ثانیه جابه‌جا شد تا ضرب‌ها روی برش‌ها بنشینند" if "beat grid falls" in n else n)
        if not solved["moved"]:
            return plan, audio, notes
        scenes = []
        for index, scene in enumerate(plan.scenes):
            end = new_starts[index + 1] if index + 1 < len(plan.scenes) else total
            scenes.append(scene.model_copy(update={"start": new_starts[index], "end": round(end, 3)}))
        moved = []
        for clip in audio:
            owner = next((i for i, sc in enumerate(plan.scenes) if sc.start - 1e-6 <= clip["start"] < sc.end + 1e-6), None)
            moved.append({**clip, "start": round(clip["start"] + (new_starts[owner] - starts[owner]), 2)} if owner is not None else clip)
        shifted = sum(1 for a, b2 in zip(starts, new_starts) if abs(a - b2) > 1e-6)
        notes.append(f"شروع {shifted} صحنه برای نشستن روی بیت کمی عقب رفت و {solved['aligned']} برش روی ضرب است (فیلم {total - plan.duration:+.1f} ثانیه)")
        return plan.model_copy(update={"scenes": scenes, "duration": round(total, 2)}), moved, notes
    except _Cancelled:
        raise
    except Exception as exc:
        log.warning("rhythm sync skipped: %s", str(exc)[:160])
        return plan, audio, [n for n in notes if n]


def _lengthen_buildup(directory: Path, choice, analysis: dict, accent_s: float | None, notes: list[str]):
    """A track whose drop comes before the film's reveal gets a longer build-up (music_fit.extend_buildup), so the drop can fall on the reveal. The new file is kept as the film's
    music (music_choice.json), measured again, and used only when its drop really is where it should be; otherwise the original track is kept. Returns (analysis, choice)."""
    from creative.audio import music_director as md, music_fit, music_providers
    try:
        ext = music_fit.extend_buildup(Path(choice.path), analysis, accent_s, music_providers.store_root() / "extended")
        if not ext:
            return analysis, choice
        longer = md.analysis_for(ext["path"])
        if not longer or longer.get("bpm_confidence", 0) < 0.2 or not any(abs(d - ext["drop_ms"]) <= 650 for d in longer.get("drops_ms") or []):
            return analysis, choice                  # the detector must still see a drop near where the repeats put it (it may sit up to a beat early on the lengthened build-up)
        # The repeats put the drop at an exactly known place: the measured one is replaced by it (in the cached analysis too, so every later step reads the same grid).
        added_ms = int(round(ext["added_s"] * 1000))
        original = int(ext["drop_ms"]) - added_ms
        longer["drops_ms"] = [int(ext["drop_ms"])] + [int(d) + added_ms for d in analysis.get("drops_ms") or [] if int(d) > original + 500]
        try:
            from creative.audio import rhythm
            (md.analysis_dir() / f"rhythm-{rhythm.content_key(Path(ext['path']))}.json").write_text(json.dumps(longer))
        except Exception:
            log.info("lengthened build-up analysis not cached")
        saved = directory / "music_choice.json"
        try:
            record = json.loads(saved.read_text())
            record.update({"path": str(ext["path"]), "extended_from": str(choice.path)})
            saved.write_text(json.dumps(record, ensure_ascii=False))
        except (OSError, ValueError):
            pass
        choice.path = ext["path"]
        notes.append(f"بیلدآپ موسیقی {ext['added_s']:.1f} ثانیه (دو میزان، {ext['repeats']} بار تکرار) طولانی‌تر شد تا دراپ به لحظهٔ رونمایی برسد")
        return longer, choice
    except Exception as exc:
        log.info("build-up not lengthened: %s", str(exc)[:160])
        return analysis, choice


def _add_music(directory: Path, record: dict, plan, audio: list[dict]):
    """The film's background music as one more audio clip (fitted to the film, faded, and ducked under the narration). Returns (audio, notes).
    Music that cannot be made never stops the build."""
    wanted = record.get("music") or {}
    if wanted.get("mode") not in MUSIC_MODES:
        return audio, []
    from creative import music_bed
    from creative.audio import music_director as md, music_fit

    def progress(text: str, state: str = "active") -> None:
        try: _note(directory, "music", text, state)
        except _Cancelled: raise
        except Exception: log.debug("music progress line not stored")    # a progress line must never cost the music
    try:
        choice = _resolve_music(directory, record, plan, None)
        if choice.path is None:
            return audio, choice.notes or ["در کتابخانهٔ موسیقی ترکی پیدا نشد؛ ویدیو بدون موسیقی ساخته شد. یک ترک در «Media library» آپلود کنید یا فایل صوتی پیوست کنید."]
        source, label = Path(choice.path), choice.label
        voice = [clip for clip in audio if clip.get("role") != "music"]
        try:
            fit = json.loads((directory / "music_fit.json").read_text())
        except (OSError, ValueError):
            fit = {"offset_s": 0.0, "anchor": None, "loop": None}
        use_fit = bool(wanted.get("sync")) and (float(fit.get("offset_s") or 0) > 0.001 or fit.get("loop") is True or wanted.get("mode") in {"auto", "search", "generate"})
        stamp = (f"{source.name}|{source.stat().st_size}|{plan.duration}|{record.get('music_gain_db')}|{record.get('ducking_db')}|{fit.get('offset_s')}|{use_fit}|"
                 + ",".join(f"{c['start']}-{c['duration']}" for c in voice))
        output = directory / "music_bed.m4a"
        marker = directory / "music_bed.json"
        analysis = md.analysis_for(source) if (use_fit or wanted.get("sync")) else None
        notes = [*choice.notes, f"موسیقی: {label}"]
        if choice.attribution:
            notes.append("منبع و مجوز موسیقی (برای درج در توضیحات انتشار): " + choice.attribution)
        if choice.cost and choice.cost.get("usd"):
            notes.append(f"هزینهٔ ساخت موسیقی: حدود {choice.cost['usd']:.2f} دلار")
        try:
            if json.loads(marker.read_text()).get("stamp") == stamp and output.is_file():
                _save_music_timing(directory, analysis, fit, plan, choice)
                return [*voice, {"path": str(output), "start": 0, "duration": plan.duration, "role": "music"}], notes
        except (OSError, ValueError):
            pass
        progress(f"موسیقی پس‌زمینه را با افت خودکار زیر صدا می‌سازم: {label}")
        bed_source = source
        if use_fit:
            bed_source = music_fit.render(source, directory / "music_fitted.wav", plan.duration, fit, analysis)
        music_bed.make_bed(bed_source, output, plan.duration, voice, gain_db=record.get("music_gain_db"), duck_db=record.get("ducking_db"))
        marker.write_text(json.dumps({"stamp": stamp}))
        _save_music_timing(directory, analysis, fit, plan, choice)
        progress("موسیقی پس‌زمینه آماده شد", "done")
        return [*voice, {"path": str(output), "start": 0, "duration": plan.duration, "role": "music"}], notes
    except _Cancelled:
        raise
    except Exception as exc:
        log.warning("motion music bed could not be made: %s", str(exc)[:200])
        return audio, ["ساخت موسیقی پس‌زمینه انجام نشد و ویدیو بدون موسیقی ساخته شد: " + str(exc)[:140]]


def _save_music_timing(directory: Path, analysis: dict | None, fit: dict, plan, choice) -> None:
    """The track's rhythm on the film's own clock (offset removed): what the scene designers, the sound effects and the editor read. Beside the project, with its source and licence."""
    from creative.audio import music_fit
    timing = music_fit.film_timing(analysis, fit, float(plan.duration)) if analysis else {}
    (directory / "music_timing.json").write_text(json.dumps({"timing": timing, "source": choice.source, "label": choice.label, "style": choice.style, "arc": choice.arc,
                                                             "attribution": choice.attribution, "track": choice.track and {k: choice.track.get(k) for k in ("id", "provider", "license", "rights")}},
                                                            ensure_ascii=False))


def _attach_beats(directory: Path, record: dict, plan):
    """Each scene gets the beats and the accent that fall inside it (seconds from its own start), so its designer can land the big moves on them. Only with Sync to Beat
    on, a reliable beat grid and music that is really part of the film; otherwise the plan is returned untouched."""
    wanted = record.get("music") or {}
    if not wanted.get("sync") or wanted.get("mode") not in MUSIC_MODES:
        return plan
    try:
        saved = json.loads((directory / "music_timing.json").read_text())
        timing = saved["timing"]
    except (OSError, ValueError, KeyError):
        return plan
    if not timing or float(timing.get("beat_confidence") or 0) < 0.3 or not timing.get("bpm"):
        return plan
    strong_all, bars_all, beats_all = timing.get("strong_beats_ms") or [], timing.get("bars_ms") or [], timing.get("beats_ms") or []
    accents = [d for d in timing.get("drops_ms") or []] + ([timing["anchor"]["film_ms"]] if timing.get("anchor") else [])
    period = round(60.0 / float(timing["bpm"]), 3)
    scenes = []
    for scene in plan.scenes:
        def inside(values):
            return [round(b / 1000 - scene.start, 2) for b in values if scene.start <= b / 1000 < scene.end - 0.1]
        beats = (inside(strong_all) or inside(bars_all) or inside(beats_all)[::2])[:12]       # strong beats; else bar lines; else every second beat of the grid
        accent = next((round(a / 1000 - scene.start, 2) for a in accents if scene.start - 1e-6 <= a / 1000 < scene.end), None)
        scenes.append(scene.model_copy(update={"beats": beats, "accent": accent, "beat_s": period if beats else 0.0}))
    return plan.model_copy(update={"scenes": scenes})


def _add_sfx(directory: Path, record: dict, plan, audio: list[dict]):
    """Sound effects with a purpose: one on each cut into a scene and a strong one on the film's accent, as dense as the film's sound-design level allows, snapped to a near beat
    and never over a spoken word. They are synthesised in the studio, so there is no third-party audio. Only films that asked for music or a sound-design level get any."""
    wanted = record.get("music") or {}
    level = (record.get("sfx") or "").strip() or (((record.get("audio_plan") or {}).get("sound_design") or "minimal") if wanted.get("mode") in {"auto", "search", "generate"} else "none")
    if level == "none" or not any(clip.get("role") != "music" for clip in audio):
        return audio, []
    try:
        from creative.audio import music_director as md, sound_design
        from creative.audio.contracts import AudioTimingEvent
        try:
            timing = json.loads((directory / "music_timing.json").read_text()).get("timing") or {}
        except (OSError, ValueError):
            timing = {}
        starts = [{"start": sc.start} for sc in plan.scenes]
        accent_s = plan.scenes[-1].start if len(plan.scenes) >= 2 else None
        speech = [AudioTimingEvent(id=f"w{i}-{j}", type="word", time_ms=int((sc.start + float(c["t"])) * 1000), duration_ms=280)
                  for i, sc in enumerate(plan.scenes) for j, c in enumerate(sc.cues or [])]
        cues = sound_design.plan(md.sfx_moments(starts, timing, accent_s), level, md.sfx_library(directory / "sfx"), beats_ms=timing.get("beats_ms") or None, speech=speech,
                                 total_ms=int(plan.duration * 1000))
        track = md.render_sfx(cues, plan.duration, directory / "sfx_track.wav")
        (directory / "sfx_cues.json").write_text(json.dumps(cues, ensure_ascii=False))
        if not track or not any(c["status"] == "ready" for c in cues):
            return audio, []
        placed = [c for c in cues if c["status"] == "ready"]
        return [*audio, {"path": str(track), "start": 0, "duration": plan.duration, "role": "sfx"}], [f"{len(placed)} افکت صوتی هم‌زمان با برش‌ها و لحظهٔ اوج (سطح {level})"]
    except _Cancelled:
        raise
    except Exception as exc:
        log.warning("sound effects skipped: %s", str(exc)[:200])
        return audio, []


def _image_input_questions(plan, record: dict) -> list[str]:
    """Ask for missing owned sources before paid narration or scene authoring."""
    available={row['asset']:row for row in record.get('image_inputs',[])}
    questions=[]
    for scene in plan.scenes:
        spec=scene.shotcraft_component
        resource=getattr(spec,'resource_id',None)
        if resource=='shotcraft:card-stack':
            names=[card.asset for card in spec.cards]
            if any(name not in available for name in names):
                questions.append('برای پشتهٔ کارت‌ها، نه تصویر مجاز و متفاوت را پیوست کنید و ترتیبشان را مشخص کنید؛ تصویر پنجم برجسته می‌شود.')
        elif resource=='shotcraft:before-after-slider-scrub':
            names=[spec.before_asset,spec.after_asset]
            if any(name not in available for name in names):
                questions.append('برای مقایسه، دو تصویر مجاز را پیوست کنید و مشخص کنید کدام قبل و کدام بعد است.')
            elif len({(available[name]['width'],available[name]['height']) for name in names})!=1:
                questions.append('دو تصویر مقایسه باید ابعاد پیکسلی یکسان داشته باشند؛ دو تصویر هم‌اندازه بفرستید.')
    return list(dict.fromkeys(questions))


def _scout_library(directory: Path, plan, brief: str, used: list[str]):
    """Let an image-capable model suggest ready-made components for scenes they really fit (see creative.library_scout). Never fatal: the plan is kept as it was on any failure."""
    from creative import library_scout
    if not library_scout.enabled():
        return plan
    _note(directory, "library", "دارم کتابخانهٔ کامپوننت‌های آماده را با صحنه‌ها مقایسه می‌کنم")
    try:
        result, report = library_scout.scout(plan, brief, used=used)
    except _Cancelled:
        raise
    except Exception as exc:
        log.warning("library scout failed for %s: %s", directory.name, str(exc)[:200])
        result, report = plan, {"status": "failed", "reason": type(exc).__name__, "picks": [], "offered": 0}
    with _lock(directory.name):
        saved = load(directory); saved["library"] = report; save(directory, saved)
    picked = [p for p in report.get("picks", []) if p.get("used")]
    if picked:
        text = "کامپوننت آماده: " + "؛ ".join(f"صحنهٔ {p['scene']} ← {p['resource_id'].split(':')[-1]}" for p in picked)
    elif report.get("status") == "none-fits":
        text = "کتابخانه بررسی شد؛ هیچ کامپوننت آماده‌ای از طراحی اختصاصی بهتر نبود"
    else:
        text = "کتابخانهٔ کامپوننت‌ها استفاده نشد" + (f" ({report.get('reason')})" if report.get("reason") else "")
    lines = [f"صحنهٔ {p['scene']} · {p['resource_id']} · {'استفاده شد' if p.get('used') else p.get('why_not', '')} — {p.get('reason', '')}" for p in report.get("picks", [])]
    _note(directory, "library", text, "done", detail="\n".join([f"{report.get('offered', 0)} کامپوننت آماده به مدل نشان داده شد (با تصویر)", *lines]))
    return result


def _drop_scouted(directory: Path, build, brief: str, notes: list[str]):
    """A component the scout suggested failed in the browser: its scenes are designed by hand instead, so a suggestion never costs the film. Returns the
    new page, or None when there is nothing of that kind to drop (a component the planner chose itself keeps the strict behaviour)."""
    from creative import motion_graphic as mg
    picks = (load(directory).get("library") or {}).get("picks", [])
    scouted = {p["scene"] for p in picks if p.get("used")}
    scenes = build.plan.scenes
    present = [n for n, s in enumerate(scenes, 1) if s.native_component or s.shotcraft_component]
    if not present or any(n not in scouted for n in present):
        return None
    for n in present:
        scenes[n - 1].native_component = None
        (build.scenes_dir / f"s{n}.json").unlink(missing_ok=True)
        try:
            draft = mg.author_scene(build.plan, n, brief, context=build.context, style=build.style)
        except Exception as exc:
            log.warning("scene %d could not be designed by hand after its component failed: %s", n, str(exc)[:160])
            draft = mg.fallback_scene(build.plan, n)
        build.drafts[n] = draft
        notes.append(f"کامپوننت آمادهٔ صحنهٔ {n} در بررسی مرورگر رد شد؛ این صحنه با طراحی اختصاصی ساخته شد")
        _note(directory, f"scene{n}", f"صحنهٔ {n}: کامپوننت آماده رد شد؛ با طراحی اختصاصی ساخته شد", "done")
    saved_plan = directory / "plan.json"
    try:
        cached = json.loads(saved_plan.read_text())
        saved_plan.write_text(json.dumps({"fp": cached.get("fp", ""), "plan": build.plan.model_dump()}, ensure_ascii=False))
    except (OSError, ValueError):
        pass
    with _lock(directory.name):
        saved = load(directory)
        for p in (saved.get("library") or {}).get("picks", []):
            if p.get("used") and p["scene"] in present:
                p["used"] = False; p["why_not"] = "failed the browser check; designed by hand instead"
        save(directory, saved)
    return mg.assemble_scenes(build.plan, [build.drafts[i] for i in range(1, len(scenes) + 1)], build.audio)


def _plan_and_build(directory: Path, record: dict, brief: str, used: list[str], scene_notes: list[str]):
    """Plan the clip, then design its scenes in parallel while telling the person what is really being worked on. Returns (page, build) or None
    when it asked questions. Finished work is kept on disk: a retry continues from the plan and the scenes that already exist."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from types import SimpleNamespace
    from creative import motion_graphic as mg
    cid, user, key = record["conversation_id"], record["user_key"], record["id"]
    context = record.get("context", "")
    if record.get('ui_images'):
        from creative import ui_images
        if not all(row.get('analysed') for row in record['ui_images']):
            _note(directory, "image", "دارم تصویر پیوست را می‌بینم: برنامهٔ برنامه، قسمت‌های مهم و نوار‌های سیستم که باید حذف شوند")
            rows = ui_images.enrich(directory, record['ui_images'])
            with _lock(directory.name):
                saved = load(directory); saved['ui_images'] = rows; save(directory, saved)
            record['ui_images'] = rows
            found = [r for r in rows if r.get('app')]
            _note(directory, "image", f"تصویر پیوست بررسی شد: {len(found)} نمای تمیز و {sum(len(r.get('regions', [])) for r in rows)} بخش مجزا" if found else "تصویر پیوست توصیف نشد؛ با برش محافظ استفاده می‌شود",
                  "done", detail="\n\n".join(f"{r.get('description', '')}\n" + "\n".join(f"- {x['name']}: {x['what']}" for x in r.get('regions', [])) for r in rows if r.get('description')) or None)
        context=ui_images.context_block(record['ui_images'])+context
    if record.get('image_inputs'):
        context='ELIGIBLE OWNED MOTION IMAGES (data only; ordering and comparison roles must follow the user request, never invent a before state):\n'+json.dumps(record['image_inputs'],ensure_ascii=True)+'\n'+context
    style = record.get("style", "")
    plan_fp = _fingerprint("motion-local-clock-shotcraft-v1", brief, context, style)
    saved_plan = directory / "plan.json"
    plan = None
    try:
        cached = json.loads(saved_plan.read_text())
        # A structured edit (the Edit tab) changed the saved plan itself: that plan is the one to build, whatever the request text now hashes to.
        if cached.get("fp") == plan_fp or record.get("edit_pending"):
            plan = mg.MotionPlan.model_validate(cached["plan"])
            plan_fp = cached.get("fp", plan_fp)
    except (OSError, ValueError):
        pass
    stats = _stats()
    if plan is None:
        _progress(directory, "writing", 6, "دارم از روی درخواست شما طرح کلی و صحنه‌ها را می‌نویسم.", stage="writing", eta=stats["plan_s"] + _remaining(4, 15))
        _note(directory, "plan", "دارم طرح کلی را می‌نویسم: صحنه‌ها، متن‌ها و رنگ‌ها", request=brief)
        started = time.monotonic()
        if style.startswith("THE PERSON'S OWN HABITS"):
            _note(directory, "style", "سبک و قانون‌هایی که قبلاً به استودیو یاد داده‌اید در طراحی اعمال می‌شود", "done", detail=style)
        sheet = directory.parent.parent / "reference" / "frame-table.jpg"          # the frames of a reference video in this chat: the font advisor matches their lettering
        advice = _font_advice(directory, brief, sheet if style and sheet.is_file() else None)
        plan = mg.plan(brief, context=context, style=style, used=used, fonts=_advice_text(advice), advice=advice)
        if _cancelled(key):
            raise _Cancelled()
        if not plan.asks():
            plan = mg.apply_handoff(plan, brief)          # an approved script from Instagram GPT fixes the scenes' words
            questions=_image_input_questions(plan,record)
            if questions:
                _note(directory,"plan","برای اجرای این طرح به تصاویر مجاز نیاز دارم.","done")
                _ask(directory,record,questions[:3])
                return None
        if plan.asks():
            _note(directory, "plan", "برای ادامه به چند اطلاعات نیاز دارم.", "done")
            _ask(directory, record, plan.questions)
            return None
        _learn("plan_s", time.monotonic() - started)
        plan = _scout_library(directory, plan, brief, used)
        saved = {"fp": plan_fp, "plan": plan.model_dump()}
        from creative import plan_checks
        if plan_checks.enabled():                      # advisory only: scored from the plan itself, never blocks, no model call
            quality = plan_checks.score_plan(plan)
            saved["quality"] = quality
            _note(directory, "plan_quality", f"امتیاز تنوع طرح: {quality['score']:g} از ۵ ({quality['verdict']})", "done", detail="\n".join(quality["violations"]) or None)
        saved_plan.write_text(json.dumps(saved, ensure_ascii=False))
        count = len(plan.scenes)
        _note(directory, "plan", f"طرح آماده شد: {count} صحنه، {plan.duration:g} ثانیه", "done", detail=_plan_detail(brief, plan))
        try:
            pictures = [i for i, sc in enumerate(plan.scenes, 1) if getattr(sc, "visual", "code") == "image"]
            reasons = "\n".join(f"صحنهٔ {i}: {'تصویر' if getattr(sc, 'visual', 'code') == 'image' else 'کد'} — {getattr(sc, 'visual_why', '') or '—'}" for i, sc in enumerate(plan.scenes, 1))
            _note(directory, "visuals", (f"موتور هر صحنه: صحنه‌های {'، '.join(map(str, pictures))} با تصویر (کشیده‌شدن خط‌به‌خط)، بقیه با کد" if pictures else "موتور هر صحنه: همه با کد (هیچ صحنه‌ای تصویر لازم نداشت یا بودجهٔ تصویر اجازه نداد)"),
                  "done", detail=reasons)
        except _Cancelled:
            raise
        except Exception:
            log.info("visual engine note failed", exc_info=True)
        from creative import captions as _caption_design
        _look = _caption_design.choose_style(getattr(plan, "caption_style", ""), (plan.title or "") + "|" + (plan.signature or ""))
        _note(directory, "captions", f"زیرنویس نریشن: سبک «{_look}»، با فونت متن فیلم", "done")
        outline = "\n".join(f"{i}) {sc.headline} — {sc.idea}" for i, sc in enumerate(plan.scenes, 1))
        from app import studio_narrator
        studio_narrator.narrate(cid, user, "motion_plan", {"title": plan.title, "duration_seconds": plan.duration, "format": plan.format, "signature_idea": plan.signature,
                                "scenes": [{"headline": sc.headline, "what_happens": sc.idea} for sc in plan.scenes]},
                                fallback=f"طرح «{plan.title}» آماده شد ({plan.duration:g} ثانیه، {count} صحنه):\n{outline}\nالان هر صحنه را جداگانه طراحی می‌کنم.")
    else:
        questions=_image_input_questions(plan,record)
        if questions:
            _ask(directory,record,questions)
            return None
        count = len(plan.scenes)
        _note(directory, "plan", f"از طرح قبلی ادامه می‌دهم: {count} صحنه، {plan.duration:g} ثانیه", "done")
    plan, audio, voice_notes = _narrate(directory, record, plan, plan_fp)
    plan, audio, rhythm_notes = _sync_rhythm(directory, record, plan, audio)
    audio, music_notes = _add_music(directory, record, plan, audio)
    audio, sfx_notes = _add_sfx(directory, record, plan, audio)
    plan = _attach_beats(directory, record, plan)
    audio, master_notes = _master_audio(directory, record, plan, audio)
    voice_notes = [*record.get("directive_notes", []), *voice_notes, *rhythm_notes, *music_notes, *sfx_notes, *master_notes]
    count = len(plan.scenes)
    import hashlib
    draft_inputs = [(sc.start, sc.end, sc.narration, sc.native_component.model_dump() if sc.native_component else None) for sc in plan.scenes]
    # Keep the exact legacy fingerprint shape when no new component is selected.
    if any(sc.shotcraft_component for sc in plan.scenes):
        draft_inputs = {"existing":draft_inputs,"shotcraft":[sc.shotcraft_component.model_dump() if sc.shotcraft_component else None for sc in plan.scenes]}
    fingerprint = plan_fp + hashlib.sha256(json.dumps(draft_inputs, ensure_ascii=False).encode()).hexdigest()[:8]       # the whole plan: how older drafts were saved

    def scene_fp(n: int) -> str:
        """A scene's own identity: its length, its narration and its components. A change to another scene does not touch it."""
        sc = plan.scenes[n - 1]
        own = [round(sc.end - sc.start, 2), sc.narration, sc.native_component.model_dump() if sc.native_component else None,
               sc.shotcraft_component.model_dump() if sc.shotcraft_component else None]
        if sc.beats or sc.accent is not None:
            own.append([[round(b * 20) / 20 for b in sc.beats], None if sc.accent is None else round(sc.accent * 20) / 20])       # a new beat grid redesigns the motion of that scene
        return plan_fp + "s" + hashlib.sha256(json.dumps(own, ensure_ascii=False).encode()).hexdigest()[:8]
    scenes_dir = directory / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    drafts: dict[int, Any] = {}
    for n in range(1, count + 1):                                   # scenes finished by an earlier attempt are not redone
        try:
            cached = json.loads((scenes_dir / f"s{n}.json").read_text())
            loaded = mg.SceneDraft.model_validate(cached["draft"])
            # Local-clock drafts do not depend on where the scene starts; an older absolute-clock draft also needs the same start.
            same_place = loaded.timebase == "local" or cached.get("start") == plan.scenes[n - 1].start
            if (cached.get("fp") == scene_fp(n) and same_place) or cached.get("fp") == fingerprint:
                drafts[n] = loaded
                _note(directory, f"scene{n}", f"صحنهٔ {n} از قبل آماده بود: «{plan.scenes[n - 1].headline}»", "done")
        except (OSError, ValueError):
            pass
    pending = [n for n in range(1, count + 1) if n not in drafts]
    done = count - len(pending)
    finished = 0
    if pending:
        _progress(directory, "writing", 8 + int(24 * done / count), f"دارم {len(pending)} صحنه را طراحی می‌کنم.", stage="writing", eta=_remaining(len(pending), plan.duration))

    run_id = getattr(_local, "run", None)

    def author(n: int):
        _local.run = run_id
        scene = plan.scenes[n - 1]
        _note(directory, f"scene{n}", f"دارم صحنهٔ {n} را طراحی می‌کنم: «{scene.headline}»",
              request=f"عنوان: {scene.headline}\nنریشن: {scene.narration or '—'}\nمدت: {scene.end - scene.start:.1f} ثانیه\nایدهٔ تصویری و حرکتی:\n{scene.idea}")
        started = time.monotonic()
        tries = [1]

        def retry(attempt: int, problems: list[str]) -> None:
            tries[0] = attempt
            reasons = "؛ ".join(dict.fromkeys(mg.explain_problem(p) for p in problems[:3]))
            _note(directory, f"scene{n}", f"صحنهٔ {n} («{scene.headline}») از بررسی رد شد: {reasons}. دارم همین صحنه را اصلاح می‌کنم (تلاش {attempt} از {mg.SCENE_ATTEMPTS})")
            left = len(pending) - finished
            _progress(directory, "writing", 8 + int(24 * (done + finished) / count), f"صحنهٔ {n} در حال اصلاح است.", stage="writing",
                      eta=_remaining(left, plan.duration, extra=(mg.SCENE_ATTEMPTS - attempt + 1) * stats["scene_s"] * 0.7))

        if getattr(scene, "visual", "code") == "image":
            try:
                from creative import image_scene
                _note(directory, f"scene{n}", f"دارم تصویر صحنهٔ {n} را می‌سازم و ترتیب کشیدن خط‌هایش را تعیین می‌کنم: «{scene.headline}»",
                      request=f"چرا تصویر: {scene.visual_why or '—'}\nدستور تصویر: {scene.image_prompt}\nمدت: {scene.end - scene.start:.1f} ثانیه")
                draft = image_scene.make_draft(plan, n, directory)
                _learn("scene_s", (time.monotonic() - started))
                return n, draft, False
            except _Cancelled:
                raise
            except Exception as exc:
                log.warning("picture for scene %d of %s failed, designing it with code: %s", n, key, str(exc)[:200])
                _note(directory, f"scene{n}", f"ساخت تصویر صحنهٔ {n} انجام نشد ({str(exc)[:70]})؛ این صحنه با طراحی کد ساخته می‌شود")
        try:
            draft = mg.author_scene(plan, n, brief, context=context, used=used, on_retry=retry, style=style)
            _learn("scene_s", (time.monotonic() - started) / tries[0])
            return n, draft, False
        except Exception as exc:
            if scene.native_component or getattr(scene,"shotcraft_component",None):
                raise
            log.warning("scene %d of %s fell back to a plain scene: %s", n, key, str(exc)[:200])
            return n, mg.fallback_scene(plan, n), True

    if pending:
        from concurrent.futures import FIRST_COMPLETED, wait
        pool = ThreadPoolExecutor(max_workers=_SCENE_WORKERS)
        try:
            waiting = {pool.submit(author, n) for n in pending}
            while waiting:
                done_now, waiting = wait(waiting, timeout=1.0, return_when=FIRST_COMPLETED)
                if _cancelled(key):
                    raise _Cancelled()                   # a model call in flight cannot be interrupted, but the worker no longer waits for it
                for future in done_now:
                    n, draft, plain = future.result()
                    drafts[n] = draft
                    finished += 1
                    scene = plan.scenes[n - 1]
                    if plain:
                        scene_notes.append(f"صحنهٔ {n} («{scene.headline}») با طرح ساده جایگزین شد چون طراحی کامل از بررسی رد شد")
                    else:
                        (scenes_dir / f"s{n}.json").write_text(json.dumps({"fp": scene_fp(n), "start": scene.start, "draft": draft.model_dump()}, ensure_ascii=False))
                    _note(directory, f"scene{n}", f"صحنهٔ {n} آماده شد: «{scene.headline}»" + (" (طرح ساده)" if plain else ""), "done",
                          detail=f"صحنهٔ {n} · {scene.start:g}–{scene.end:g} ثانیه\nایده: {scene.idea}\nنریشن: {scene.narration or '—'}" + ("\nطراحی کامل از بررسی رد شد؛ طرح ساده جایگزین شد." if plain else ""))
                    _progress(directory, "writing", 8 + int(24 * (done + finished) / count), f"صحنهٔ {n} از {count} آماده شد.", stage="writing",
                              eta=_remaining(len(pending) - finished, plan.duration))
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    build = SimpleNamespace(plan=plan, drafts=drafts, context=context, style=style, fingerprint=fingerprint, scenes_dir=scenes_dir, audio=audio, voice_notes=voice_notes)
    return mg.assemble_scenes(plan, [drafts[n] for n in range(1, count + 1)], audio), build


def _scenes_in(problems: list[str], count: int) -> list[int]:
    """Which scenes a check finding points at (its selector names #sN or the Nth section)."""
    found: list[int] = []
    for problem in problems:
        for match in re.finditer(r"#s(\d+)\b|section:nth-of-type\((\d+)\)", problem):
            n = int(match.group(1) or match.group(2))
            if 1 <= n <= count and n not in found:
                found.append(n)
    return found


def _isolate(directory: Path, work: Path, build, page, problems: list[str], notes: list[str], brief: str = "", used: list[str] | None = None):
    """The page fails and no finding names a scene: swap one scene at a time for its plain version until the check passes; if no single swap does,
    every scene becomes plain. Returns the page to check again."""
    from creative import motion_graphic as mg
    from engine.hyperframes import standalone
    if getattr(page, "native_components", None) or getattr(page,"shotcraft_components",None):
        raise RuntimeError("Executable component failed validation; refusing plain-title substitution: " + problems[0])
    key = directory.name
    count = len(build.plan.scenes)
    _note(directory, "check", f"مشکل اجرا پیدا شد ({mg.explain_problem(problems[0])}). دارم صحنهٔ مشکل‌دار را پیدا می‌کنم", "active")
    # Test every designed scene on its own page (the others plain) so only the scenes that really fail lose their design.
    plain = {i: mg.fallback_scene(build.plan, i) for i in range(1, count + 1)}
    failing: list[int] = []
    errors: dict[int, list[str]] = {}
    for n in range(1, count + 1):
        trial = dict(plain)
        trial[n] = build.drafts[n]
        mg.write_project(work, mg.assemble_scenes(build.plan, [trial[i] for i in range(1, count + 1)], build.audio))
        result = standalone.check(work, should_cancel=lambda: _cancelled(key))
        if _cancelled(key):
            raise _Cancelled()
        if result.blocking:
            failing.append(n)
            errors[n] = list(result.blocking)
    # A scene that fails is designed again from its own error (up to three times) before it may lose its design; the motion is fixed, not removed.
    had_failing = bool(failing)
    for attempt in (1, 2, 3):
        if not failing or not brief:
            break
        still: list[int] = []
        for n in failing:
            scene = build.plan.scenes[n - 1]
            if scene.native_component or getattr(scene, "shotcraft_component", None):
                still.append(n)
                continue
            _note(directory, f"scene{n}", f"صحنهٔ {n} در اجرا خطا می‌داد؛ دوباره طراحی می‌شود (تلاش {attempt} از ۳)", "active",
                  detail="\n".join(f"{mg.explain_problem(p)} — {p[:300]}" for p in errors.get(n, [])[:3]))
            try:
                draft = mg.author_scene(build.plan, n, brief, context=build.context, used=used, feedback=[mg.explain_problem(p) + " — " + p[:300] for p in errors.get(n, [])[:4]], style=build.style)
            except Exception as exc:
                log.warning("scene %d could not be designed again from its error: %s", n, str(exc)[:160])
                still.append(n)
                continue
            trial = dict(plain)
            trial[n] = draft
            mg.write_project(work, mg.assemble_scenes(build.plan, [trial[i] for i in range(1, count + 1)], build.audio))
            result = standalone.check(work, should_cancel=lambda: _cancelled(key))
            if _cancelled(key):
                raise _Cancelled()
            if result.blocking:
                errors[n] = list(result.blocking)
                still.append(n)
            else:
                build.drafts[n] = draft
                notes.append(f"صحنهٔ {n} («{scene.headline}») پس از خطا دوباره طراحی و درست شد")
                _note(directory, f"scene{n}", f"صحنهٔ {n} پس از اصلاح خطا آماده شد: «{scene.headline}»", "done")
        failing = still
    if had_failing and not failing:                    # every failing scene was fixed: the page keeps all its designs
        repaired = mg.assemble_scenes(build.plan, [build.drafts[i] for i in range(1, count + 1)], build.audio)
        mg.write_project(work, repaired)
        return repaired
    if failing and len(failing) < count:
        trial = {i: (plain[i] if i in failing else build.drafts[i]) for i in range(1, count + 1)}
        candidate = mg.assemble_scenes(build.plan, [trial[i] for i in range(1, count + 1)], build.audio)
        mg.write_project(work, candidate)
        result = standalone.check(work, should_cancel=lambda: _cancelled(key))
        if _cancelled(key):
            raise _Cancelled()
        if not result.blocking:
            build.drafts = trial
            for n in failing:
                headline = build.plan.scenes[n - 1].headline
                notes.append(f"صحنهٔ {n} («{headline}») با طرح ساده جایگزین شد چون در اجرا خطا می‌داد")
                _note(directory, f"scene{n}", f"صحنهٔ {n} با طرح ساده جایگزین شد", "done")
            return candidate
    build.drafts = {i: mg.fallback_scene(build.plan, i) for i in range(1, count + 1)}
    notes.append("چند صحنه در اجرا خطا می‌دادند؛ همهٔ صحنه‌ها با طرح ساده ساخته شد")
    _note(directory, "check", "صحنه‌ها با طرح ساده ساخته شدند تا ویدیو حتماً کامل شود", "done")
    return mg.assemble_scenes(build.plan, [build.drafts[i] for i in range(1, count + 1)], build.audio)


def _prepare_and_render(directory: Path, page, brief: str, change: str, used: list[str], build=None):
    from creative import motion_graphic as mg
    from engine.hyperframes import standalone
    key = directory.name
    work = directory / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    saved_record=load(directory)
    if saved_record.get('ui_images'):
        from creative import ui_images
        ui_images.restore(directory,work,saved_record['ui_images'])
    image_inputs=saved_record.get('image_inputs',[])
    if image_inputs:
        from creative.shotcraft_compare import restore_inputs
        restore_inputs(directory,work,image_inputs)
    notes: list[str] = list(getattr(build, "voice_notes", []) or [])
    repairs_left = 3
    isolated = 0
    shots_of = None
    stats = _stats()
    while True:
        def component_progress(instance,percent):
            if _cancelled(key):
                raise _Cancelled()
            number = instance.split("-",1)[0].lstrip("s")
            _progress(directory,"writing",30+round(percent*.04),f"اجرای کامپوننت آمادهٔ صحنهٔ {number} · {percent}%",stage="native_component")
        try:
            if getattr(page,"shotcraft_components",None):
                mg.write_project(work, page, on_component_progress=component_progress)
            else:
                mg.write_project(work, page)
        except _Cancelled:
            raise
        except Exception:
            dropped = _drop_scouted(directory, build, brief, notes) if build and getattr(page, "native_components", None) else None
            if dropped is None:
                raise
            page = dropped
            continue
        _progress(directory, "checking", 36, "دارم صفحه را در مرورگر بررسی می‌کنم: چیدمان، خوانایی و خطاهای اجرا.", stage="checking",
                  eta=_remaining(0, page.duration))
        _note(directory, "check", "دارم صحنه‌ها را در مرورگر بررسی می‌کنم: چیدمان، خوانایی متن و خطاهای اجرا")
        started = time.monotonic()
        page_fp = hashlib.sha256((work / "index.html").read_bytes()).hexdigest()
        if load(directory).get("checked_page") == page_fp:
            # The same page already passed the browser check (this is a retry after a failed render): it is not run, and scene stills are not taken, again.
            _note(directory, "check", "همین صفحه قبلاً بررسی شده بود؛ بررسی دوباره لازم نیست", "done")
            result = standalone.CheckResult(ran=True)
            skipped_check = True
        else:
            skipped_check = False
            result = standalone.check(work, should_cancel=lambda: _cancelled(key))
        if result.ran and not skipped_check:
            _learn("check_s", time.monotonic() - started)
        if _cancelled(key):
            raise _Cancelled()
        problems = list(result.blocking)
        if problems and (getattr(page, "native_components", None) or getattr(page,"shotcraft_components",None)):
            dropped = _drop_scouted(directory, build, brief, notes) if build else None
            if dropped is not None:
                page = dropped
                continue
            raise RuntimeError("کامپوننت اجرایی از بررسی رد شد؛ کد اصلی با طراحی ساده جایگزین نشد: " + problems[0])
        if not problems:
            # Layout and contrast findings are not fatal and do not justify rewriting the page with a slow model: they are reported.
            notes = (notes + ([f"بررسی خودکار چیدمان/خوانایی: {len(result.quality)} مورد"] if result.quality else [])
                     + [q[:220] for q in result.quality[:4]] + result.notes)[:8]
            if not skipped_check and result.ran:
                with _lock(directory.name):
                    saved = load(directory); saved["checked_page"] = page_fp; save(directory, saved)
            break
        reasons = "؛ ".join(dict.fromkeys(mg.explain_problem(p) for p in problems[:3]))
        hit = _scenes_in(problems, len(build.plan.scenes)) if build else []
        if build and not hit:
            # A browser error such as "<path> attribute d: Expected number" names no scene: the scenes' own markup is read for it (instant), so the scene is found
            # without trying them one by one in the browser.
            from creative.reel_designer import svg_problems as _svg
            broken = {n: _svg(build.drafts[n].html) for n in range(1, len(build.plan.scenes) + 1) if build.drafts.get(n) is not None}
            broken = {n: found for n, found in broken.items() if found}
            if broken and any(re.search(r"attribute d|<path>|\bpath\b", item) for item in problems):
                hit = sorted(broken)
                problems = problems + [f"#s{n} {broken[n][0]}" for n in hit]
        if build and (repairs_left <= 0 or not hit):
            # The findings do not name a scene (or the targeted fixes ran out): find the scene that breaks the page by swapping them for plain ones one at a
            # time. The clip is always finished; only the scene that cannot be made to work loses its design.
            if isolated >= 2:
                raise RuntimeError("did not pass validation: " + problems[0])
            isolated += 1
            page = _isolate(directory, work, build, page, problems, notes, brief, used)
            continue
        if repairs_left <= 0:
            raise RuntimeError("did not pass validation: " + problems[0])
        repairs_left -= 1
        if build and hit:
            # Rebuild only the scenes the findings point at (small requests); a scene that cannot be fixed is replaced by a plain one.
            for n in hit:
                scene = build.plan.scenes[n - 1]
                if scene.native_component or getattr(scene,"shotcraft_component",None):
                    raise RuntimeError("Executable component needs an adapter correction, not model rewriting: " + problems[0])
                own = [p for p in problems if n in _scenes_in([p], len(build.plan.scenes))]
                _note(directory, f"scene{n}", f"صحنهٔ {n} («{scene.headline}») در بررسی مرورگر مشکل داشت: {'؛ '.join(dict.fromkeys(mg.explain_problem(p) for p in own[:3]))}. دارم فقط همین صحنه را دوباره می‌سازم", "active")
                _progress(directory, "writing", 38, f"صحنهٔ {n} در حال اصلاح است.", stage="writing",
                          eta=stats["scene_s"] * 1.2 + stats["check_s"] + stats["render_per_s"] * page.duration)
                try:
                    draft = mg.author_scene(build.plan, n, brief, context=build.context, used=used, feedback=own[:6], style=build.style)
                    outcome = f"صحنهٔ {n} اصلاح شد"
                except Exception as exc:
                    log.warning("scene %d could not be repaired, using a plain scene: %s", n, str(exc)[:160])
                    draft = mg.fallback_scene(build.plan, n)
                    notes.append(f"صحنهٔ {n} («{scene.headline}») با طرح ساده جایگزین شد چون اصلاح کامل ممکن نشد")
                    outcome = f"صحنهٔ {n} با طرح ساده جایگزین شد"
                build.drafts[n] = draft
                _note(directory, f"scene{n}", outcome, "done")
            page = mg.assemble_scenes(build.plan, [build.drafts[n] for n in range(1, len(build.plan.scenes) + 1)], build.audio)
            continue
        _progress(directory, "writing", 38, "مشکلی پیدا شد؛ دارم صفحه را اصلاح می‌کنم.", stage="writing",
                  eta=stats["scene_s"] * 2.5 + stats["check_s"] + stats["render_per_s"] * page.duration)
        _note(directory, "check", f"در بررسی مرورگر مشکل پیدا شد ({reasons}). دارم کل صفحه را اصلاح می‌کنم؛ این مرحله ممکن است چند دقیقه طول بکشد", "active")
        try:
            page = mg.repair(page, "\n".join(problems[:10]), brief=brief, used=used)
        except Exception as exc:
            raise RuntimeError("did not pass validation: " + problems[0]) from exc
    # The visual gate, after the page passed its checks and bounded on purpose: a scene whose still is empty or whose text lies over text is designed once more from
    # that finding; if the new page does not pass the checks, the earlier design is kept. It can never replace the designed scenes with plain ones.
    if build and result.ran and not skipped_check:
        try:
            count = len(build.plan.scenes)
            flagged: dict[int, list[str]] = {}
            for line in result.quality:
                if _TEXT_OVERLAP.search(line):
                    for n in _scenes_in([line], count):
                        flagged.setdefault(n, []).append(line[:500])
            _snapshot_scenes(directory, work, build.plan)
            shots_of = page_fp
            if flagged:      # the layout check compares rough boxes (a split headline, a highlighted word): a person's eye decides whether text really lies over text
                from creative import visual_gate as _gate
                seen = _gate.confirm_text_overlap({n: directory / "snapshots" / f"{n}.jpg" for n in flagged}, work)
                waved = sorted(n for n in flagged if seen.get(n) is False)
                for n in waved:
                    flagged.pop(n, None)
                if waved:
                    _note(directory, "check", f"بررسی چیدمان صحنه‌های {'، '.join(map(str, waved))} را مشکوک دید ولی در عکس صحنه‌ها متنی روی متن نیفتاده بود؛ همان طراحی نگه داشته شد", "done")
            for n in _blank_scenes(directory):
                if getattr(build.drafts.get(n), "image_clip", None):
                    continue                           # a drawn picture: its still can be taken before the video is decoded; the design is never redone for that
                flagged.setdefault(n, []).append("this scene shows an empty frame at its settled moment (60% of its length): nothing is visible. Every element must be revealed relative to the scene's own start, and the scene must paint its background and headline.")
            if flagged:
                _note(directory, "check", f"بررسی عکس‌ها: صحنه‌های {'، '.join(map(str, sorted(flagged)))} خالی یا با متن روی‌هم‌افتاده‌اند؛ هر کدام یک بار دوباره طراحی می‌شود", "active")
                before_page, before_drafts = page, dict(build.drafts)
                changed = []
                for n, why in sorted(flagged.items()):
                    scene = build.plan.scenes[n - 1]
                    if scene.native_component or getattr(scene, "shotcraft_component", None) or getattr(build.drafts.get(n), "image_clip", None):
                        continue                       # a ready-made component or a drawn picture is never replaced by a code design here
                    try:
                        draft = mg.author_scene(build.plan, n, brief, context=build.context, used=used, feedback=why[:4], style=build.style)
                        from creative.reel_designer import svg_problems
                        if not svg_problems(draft.html):
                            build.drafts[n] = draft
                            changed.append(n)
                    except Exception as exc:
                        log.warning("scene %d was not redesigned after the still check: %s", n, str(exc)[:160])
                if changed:
                    candidate = mg.assemble_scenes(build.plan, [build.drafts[n] for n in range(1, count + 1)], build.audio)
                    mg.write_project(work, candidate)
                    again = standalone.check(work, should_cancel=lambda: _cancelled(key))
                    if again.ran and not again.blocking:
                        page = candidate
                        page_fp = hashlib.sha256((work / "index.html").read_bytes()).hexdigest()
                        _snapshot_scenes(directory, work, build.plan)
                        shots_of = page_fp
                        left = _blank_scenes(directory)
                        notes.append(f"صحنه‌های {'، '.join(map(str, changed))} پس از بررسی عکس دوباره طراحی شدند" + (f"؛ صحنه‌های {'، '.join(map(str, left))} هنوز خالی به نظر می‌رسند" if left else ""))
                    else:
                        build.drafts.clear(); build.drafts.update(before_drafts)
                        mg.write_project(work, before_page)
                        notes.append("طراحی دوباره در بررسی رد شد؛ طراحی قبلی نگه داشته شد (ممکن است متن روی هم افتاده باشد)")
                else:
                    notes.append(f"صحنه‌های {'، '.join(map(str, sorted(flagged)))} در بررسی عکس مشکل داشتند و بازطراحی ممکن نشد")
                _note(directory, "check", "بررسی عکس صحنه‌ها تمام شد", "done", detail="\n".join(notes[-3:]))
        except _Cancelled:
            raise
        except Exception as exc:
            log.warning("visual gate failed: %s", str(exc)[:200])
            notes.append("بررسی عکس صحنه‌ها اجرا نشد: " + str(exc)[:120])
    from creative import design_critic
    if build and result.ran and not skipped_check and design_critic.enabled():
        # An art director's pass: a vision model scores every scene's still; the weakest are designed again from its concrete fixes and kept only if the same eye scores them higher.
        try:
            count = len(build.plan.scenes)
            protected = {n for n, sc in enumerate(build.plan.scenes, 1) if sc.native_component or getattr(sc, "shotcraft_component", None) or getattr(build.drafts.get(n), "image_clip", None)}

            def critic_stills():
                nonlocal shots_of
                if shots_of != page_fp:
                    _snapshot_scenes(directory, work, build.plan)
                    shots_of = page_fp
                return {n: directory / "snapshots" / f"{n}.jpg" for n in range(1, count + 1) if (directory / "snapshots" / f"{n}.jpg").is_file()}

            def critic_author(n, feedback):
                from creative.reel_designer import svg_problems
                plan_for = build.plan
                if n in protected:                                   # a poor ready-made component: the scene is designed for this film instead
                    plan_for = build.plan.model_copy(update={"scenes": [sc.model_copy(update={"native_component": None, "shotcraft_component": None, "shotcraft_id": ""}) if i == n else sc
                                                                         for i, sc in enumerate(build.plan.scenes, 1)]})
                draft = mg.author_scene(plan_for, n, brief, context=build.context, used=used, feedback=feedback, style=build.style)
                if svg_problems(draft.html):
                    raise ValueError("invalid svg")
                return draft

            def critic_rebuild():
                nonlocal page, page_fp, shots_of
                candidate = mg.assemble_scenes(build.plan, [build.drafts[i] for i in range(1, count + 1)], build.audio)
                mg.write_project(work, candidate)
                again = standalone.check(work, should_cancel=lambda: _cancelled(key))
                if not (again.ran and not again.blocking):
                    return False
                page, page_fp = candidate, hashlib.sha256((work / "index.html").read_bytes()).hexdigest()
                shots_of = None                                      # the stills are of the page before this change
                return True

            def critic_restore(before):
                build.drafts.clear(); build.drafts.update(before)

            _note(directory, "critic", "طراح ارشد (مدل بینایی) دارد عکس صحنه‌ها را از نظر زیبایی، خوانایی و سلسله‌مراتب می‌سنجد")
            verdict = design_critic.refine(drafts=build.drafts, headlines={n: sc.headline for n, sc in enumerate(build.plan.scenes, 1)}, protected=protected, stills=critic_stills,
                                           author=critic_author, rebuild=critic_rebuild, restore=critic_restore, work=work / "critic", brief=brief, style_note=build.plan.design_direction,
                                           note=lambda text: (notes.append(text), _note(directory, f"critic-{len(notes)}", text, "done")), replaceable={n for n in protected if not getattr(build.drafts.get(n), "image_clip", None)},
                                           reference=(directory.parent.parent / "reference" / "frame-table.jpg"), look=mg.reference_look(build.style))
            if verdict["before"]:
                scores = "، ".join(f"{n}:{v}" for n, v in sorted(verdict["before"].items()))
                _note(directory, "critic", "نظر طراح ارشد دربارهٔ صحنه‌ها آماده شد", "done", detail=f"امتیاز هر صحنه (از ۱۰): {scores}\n" + "\n".join(notes[-2:]))
            else:
                _note(directory, "critic", "بازبینی زیبایی‌شناسی انجام نشد؛ طراحی همان‌طور که بود ماند", "done")
            if page_fp != shots_of and verdict["kept"]:
                _snapshot_scenes(directory, work, build.plan)
                shots_of = page_fp
        except _Cancelled:
            raise
        except Exception as exc:
            log.warning("design critic skipped: %s", str(exc)[:200])
    if build is not None:
        from creative import plan_checks
        if plan_checks.promise_enabled():
            broken = plan_checks.promise_broken(build.plan, build.drafts, mg.fallback_scene)
            if broken:
                notes.append(f"هشدار: {len(broken['scenes'])} از {len(build.plan.scenes)} صحنه ({'، '.join(map(str, broken['scenes']))}) با طرح ساده‌ی فقط‌متن جایگزین شده‌اند؛ ویدیو با حرکت کمتر از طرح اولیه ساخته می‌شود")
                _note(directory, "promise", "چند صحنه به طرح ساده تبدیل شدند و حرکت طراحی‌شده را ندارند", "done", detail=f"{round(broken['share'] * 100)}٪ صحنه‌ها")
    output = work / "motion.mp4"
    render_started = time.monotonic()
    estimate = stats["render_per_s"] * page.duration

    def on_progress(percent: int) -> None:
        elapsed = time.monotonic() - render_started
        _progress(directory, "rendering", 40 + int(percent * 0.55), "دارم ویدیو را فریم‌به‌فریم رندر می‌کنم.", stage="rendering", eta=max(4.0, estimate - elapsed))

    _note(directory, "check", "بررسی صفحه تمام شد", "done", detail="\n".join(notes) if notes else "بررسی چیدمان، خوانایی و خطاهای اجرا بدون هشدار تمام شد.")
    if shots_of != page_fp and not (skipped_check and (directory / "snapshots").is_dir() and load(directory).get("snapshots")):
        _snapshot_scenes(directory, work, build.plan if build else None)
    _note(directory, "render", f"دارم {page.duration:g} ثانیه ویدیو را فریم‌به‌فریم رندر می‌کنم")
    _progress(directory, "rendering", 40, "دارم ویدیو را فریم‌به‌فریم رندر می‌کنم.", stage="rendering", eta=estimate)
    standalone.render(work, output, timeout=_render_timeout(page.duration, stats["render_per_s"]), on_progress=on_progress, should_cancel=lambda: _cancelled(key), frames=round(page.duration * 30))
    _learn("render_per_s", min(60.0, max(0.3, (time.monotonic() - render_started) / max(page.duration, 1.0))))
    _note(directory, "render", "رندر تمام شد؛ دارم ویدیو را وارسی می‌کنم", "done", detail=f"{page.duration:g} ثانیه · {page.size[0]}×{page.size[1]} · {time.monotonic() - render_started:.0f} ثانیه رندر")
    problem = verify_video(output, page.duration)
    if problem:
        raise RuntimeError(problem)
    make_thumb(output, work / "thumb.jpg", page.duration)
    return page, notes


# ── checks and media ─────────────────────────────────────────────────────────

def _probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, timeout=30).stdout.strip()
    return float(out or 0)


def verify_video(path: Path, expected: float) -> str | None:
    """None when the file is a real video of about the expected length with visible, changing picture."""
    if not path.is_file() or path.stat().st_size < 2000:
        return "فایل ویدیو ساخته نشد."
    try:
        duration = _probe_duration(path)
    except (subprocess.SubprocessError, ValueError):
        return "ویدیوی ساخته‌شده خوانده نشد."
    if abs(duration - expected) > max(1.0, expected * 0.1):
        return f"مدت ویدیو ({duration:.1f}s) با طرح ({expected:g}s) نمی‌خواند."
    stats = []
    for fraction in (0.15, 0.5, 0.92):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{duration * fraction:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=48:48,format=gray",
                              "-f", "rawvideo", "-"], capture_output=True, timeout=60).stdout
        if len(raw) >= 48 * 48:
            mean = sum(raw) / len(raw)
            stats.append((mean, (sum((b - mean) ** 2 for b in raw) / len(raw)) ** 0.5))
    if not stats:
        return "از ویدیو فریم گرفته نشد."
    if all(deviation < 1.5 for _, deviation in stats):
        return "ویدیوی ساخته‌شده خالی یا تک‌رنگ است."
    return None


def make_thumb(video: Path, thumb: Path, duration: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{duration * 0.4:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "4", str(thumb)],
                   capture_output=True, timeout=60)


def media_path(directory: Path, kind: str, version: Optional[int] = None, *, restore_media: bool = True) -> Path:
    if kind == "voice":                                    # the narration take of the latest run, playable from the step's log
        try:
            audio = json.loads((directory / "voice.json").read_text())["audio"][0]["path"]
        except (OSError, ValueError, KeyError, IndexError):
            # The Claude engine says "narration ready" long before voice.json is written: the finished take is already on disk.
            takes = sorted((directory / "voice").glob("narration_*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True) if (directory / "voice").is_dir() else []
            if not takes:
                raise KeyError("voice")
            audio = str(takes[0])
        path = Path(audio)
        if not path.is_file() or directory.resolve() not in path.resolve().parents:
            raise KeyError("voice")
        return path
    record = load(directory)
    number = version or record.get("current")
    item = _version(record, number)
    if not item:
        raise KeyError("version")
    names = {"video": "motion.mp4", "thumb": "thumb.jpg", "source": "index.html", "page": "page.json"}
    path = directory / f"v{item['n']}" / names[kind]
    if kind == "video" and not path.is_file():
        from app import media_archive

        owner = record.get("user_key")
        if restore_media:
            path = media_archive.materialize(path, owner)
        elif media_archive.available(path, owner):
            return path
    if not path.is_file():
        raise KeyError(kind)
    return path


# ── chat-side helpers ────────────────────────────────────────────────────────

def answer(directory: Path, text: str, attachments: list[dict] | None = None) -> None:
    """The person answered the questions: continue the same request with the answer."""
    with _lock(directory.name):
        record = load(directory)
        record["answers"] = [*record.get("answers", []), text.strip()[:2000]]
        if record.get("intro"):                        # an intro video waiting for the presenter's footage, or the person chose another intro style instead
            footage = next((item for item in attachments or [] if item.get("kind") == "video" and item.get("path")), None)
            if footage:
                record["intro_footage"] = str(footage["path"])
            try:
                from creative import claude_intro
                named = claude_intro.kind_of(text, False) if (claude_intro._FILM.search(text) or claude_intro._PRESENTER.search(text) or claude_intro._REEL.search(text)
                                                               or claude_intro._STORY.search(text)) else ""
                if named and named != record["intro"]:
                    record["intro"] = named
                elif footage and record["intro"] != "presenter" and not named:
                    record["intro"] = "presenter"
            except Exception:
                log.warning("the intro style of the answer could not be read", exc_info=True)
        change = record.get("pending_change") or ""
        record.update(status="queued", questions=[])
        save(directory, record)
    start(directory, change=change)


def use_attached_music(directory: Path, track: dict) -> None:
    """The person attached an audio file to a follow-up message: it becomes the film's music (synced to the beat), and only the audio is rebuilt."""
    with _lock(directory.name):
        record = load(directory)
        previous = dict(record.get("music") or {})
        record["music"] = {"mode": "attached", "words": previous.get("words", ""), "path": track["path"], "name": track.get("filename", ""), "cost": previous.get("cost", "balanced"),
                           "instrumental": previous.get("instrumental", True), "variant": 0, "sync": True}
        if (record.get("rhythm") or "speech_first") == "speech_first":
            record["rhythm"] = "balanced"
        (directory / "music_choice.json").unlink(missing_ok=True)
        save(directory, record)


def apply_music_edits(directory: Path, record: dict, edits: dict) -> list[str]:
    """What a sentence about the music changes in the record (the same fields the Edit tab sets). Returns the changes in words."""
    music = dict(record.get("music") or {})
    said: list[str] = []
    if edits.get("off"):
        record["music"] = None
        return ["موسیقی خاموش شد"]
    if not music.get("mode"):
        music = {"mode": "auto", "words": "", "cost": "balanced", "instrumental": True, "variant": 0, "sync": True}
        said.append("موسیقی خودکار روشن شد")
    if edits.get("regenerate"):
        try:
            previous = json.loads((directory / "music_choice.json").read_text()).get("path")
        except (OSError, ValueError):
            previous = None
        music["used"] = [*music.get("used", []), *([previous] if previous else [])][-12:]
        music["variant"] = int(music.get("variant") or 0) + 1
        said.append("ترک دیگری انتخاب می‌شود")
    if "energy_delta" in edits:
        base = music.get("energy") if music.get("energy") is not None else (record.get("audio_plan") or {}).get("music_energy", 0.5)
        music["energy"] = round(max(0.0, min(1.0, float(base) + edits["energy_delta"])), 2)
        music["style"] = ""
        music["used"] = [*music.get("used", []), *( [json.loads((directory / "music_choice.json").read_text()).get("path")] if (directory / "music_choice.json").is_file() else [])][-12:]
        said.append(f"انرژی موسیقی {music['energy']:.2f}")
    if "sync" in edits:
        music["sync"] = bool(edits["sync"])
        said.append("همگام‌سازی با بیت " + ("روشن" if edits["sync"] else "خاموش"))
        if edits["sync"] and music.get("mode") in {"auto", "search", "generate"} and (record.get("rhythm") or "speech_first") == "speech_first":
            record["rhythm"] = "balanced"
    if "level_delta" in edits:
        base = record.get("music_gain_db") if record.get("music_gain_db") is not None else -10.0
        record["music_gain_db"] = round(max(-40.0, min(0.0, float(base) + edits["level_delta"])), 1)
        said.append(f"سطح موسیقی {record['music_gain_db']:g} dB")
    record["music"] = music
    return said


def revise(directory: Path, change: str, voice_id: str = "") -> None:
    from creative.audio import music_director
    change = change.strip()[:3000]
    edits = music_director.edits_from_text(change)
    with _lock(directory.name):
        record = load(directory)
        if voice_id:                           # «با صدای خودم»: the voice the person asked for is the film's voice from now on (a later retry keeps it too)
            record["voice_id"] = voice_id
        from creative.audio import persian as _persian
        fixes = _persian.pronunciations_from_text(change)          # «تلفظ مرتب درست نیست، مُرَتَب درسته»: kept for the film and applied to every sentence
        if fixes:
            record["pronunciations"] = {**(record.get("pronunciations") or {}), **fixes}
        if edits:
            apply_music_edits(directory, record, edits)
        record.update(status="queued", stage="queued", progress=0, error=None)
        save(directory, record)
    if edits and music_director.is_music_only(change):
        start(directory)                       # nothing but the music changed: the plan and the designed scenes are kept, only the audio is rebuilt
        return
    start(directory, change=change)


def edit(directory: Path, changes: dict) -> dict:
    """A structured change from the Edit tab: validated against what this project can change, applied to only what it touches, built as a new version."""
    from app import motion_edit
    with _lock(directory.name):
        record = load(directory)
        if record["status"] in ACTIVE:
            raise RuntimeError("busy")
        result = motion_edit.apply(directory, record, changes)
        record.update(status="queued", stage="queued", progress=0, error=None, questions=[], pending_change=None)
        save(directory, record)
    start(directory)
    return result


def recover_interrupted() -> int:
    """After a restart: records left mid-way are marked failed, and the ones that have a checkpoint (a Claude film whose plan, code or render was already made) are
    started again at once: they go on from where they stopped, they do not begin again."""
    count = 0
    again: list[tuple[Path, str]] = []
    for path in ROOT.glob("*/*/motion/*/motion.json"):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if record.get("status") in ACTIVE and time.time() - float(record.get("updated_at") or 0) > 45 and not _beating(path.parent):   # a live worker elsewhere keeps its heartbeat
            record.update(status="failed", stage="failed", message="ساخت با راه‌اندازی دوبارهٔ سرور قطع شد.", error="interrupted")
            path.write_text(json.dumps(record, ensure_ascii=False))
            count += 1
            if (path.parent / "checkpoint.json").is_file() and time.time() - float(record.get("updated_at") or 0) < 6 * 3600:
                again.append((path.parent, str(record.get("running_change") or "")))
    for directory, change in again:
        try:
            log.warning("motion %s was interrupted by a restart: going on from its checkpoint", directory.name)
            start(directory, change=change)
        except Exception:
            log.warning("motion %s could not be resumed", directory.name, exc_info=True)
    return count

