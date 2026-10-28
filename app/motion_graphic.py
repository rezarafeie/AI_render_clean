"""Motion graphics in chat: describe a clip, get an MP4, ask for changes.

State lives in files next to the conversation (``<studio>/<user>/<conversation>/motion/<id>/``) and a pointer in the conversation state:

  motion.json     the record (status, stage, versions, questions)
  v1/ v2/ ...     one HyperFrames project per version: index.html, page.json, assets/, motion.mp4, thumb.jpg

Work runs in a background thread, one render at a time on this server (the check and the render both drive Chromium).
"""
from __future__ import annotations

import json
import logging
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
RENDER_TIMEOUT_S = 1200


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


# ── records ──────────────────────────────────────────────────────────────────

def create(conversation_id: str, user_key: str, request: str, context: str = "", style: str = "") -> dict:
    motion_id = uuid.uuid4().hex[:12]
    directory = folder(user_key, conversation_id, motion_id)
    directory.mkdir(parents=True, exist_ok=True)
    record = {"id": motion_id, "conversation_id": conversation_id, "user_key": user_key, "request": request.strip()[:4000],
              "context": context[:9000], "style": style[:2000], "status": "queued", "stage": "queued", "progress": 0, "message": "", "questions": [],
              "versions": [], "current": 0, "error": None, "created_at": time.time(), "pending_change": None, "answers": [], "log": []}
    return save(directory, record)


def _version(record: dict, number: int | None = None) -> dict | None:
    number = number or record.get("current")
    return next((v for v in record["versions"] if v["n"] == number), None)


def view(directory: Path) -> dict:
    record = load(directory)
    versions = [{k: v for k, v in item.items() if k != "page"} for item in record["versions"]]
    return {"id": record["id"], "conversation_id": record["conversation_id"], "status": record["status"], "stage": record["stage"],
            "progress": record["progress"], "message": record["message"], "questions": record["questions"], "error": record["error"],
            "request": record["request"], "versions": versions, "current": record["current"], "updated_at": record["updated_at"], "log": record.get("log", [])[-14:], "eta_s": record.get("eta_s"), "eta_at": record.get("eta_at"),
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


def _note(directory: Path, key: str, text: str, state: str = "active") -> None:
    """One line of what is really happening (about this clip's own content). A line with the same key is updated, not repeated."""
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
    from creative.motion_graphic import NOT_AVAILABLE
    record = load(directory)
    record.update(status="unavailable", stage="unavailable", progress=0,
                  message=NOT_AVAILABLE, error=NOT_AVAILABLE)
    save(directory, record)


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
        if _RUNNING.get(key) is threading.current_thread():
            _RUNNING.pop(key, None)


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
    if "not configured" in text or "Unavailable" in type(exc).__name__:
        return "سرویس هوش مصنوعی در دسترس نبود."
    if "timed out" in text:
        return "رندر بیشتر از زمان مجاز طول کشید."
    return text[:220] or "خطای ناشناخته"


def _run(directory: Path, change: str) -> None:
    from creative.motion_graphic import unavailable
    unavailable()
    from creative import motion_graphic as mg
    record = load(directory)
    cid, user, key = record["conversation_id"], record["user_key"], record["id"]
    previous = None
    current = _version(record)
    if change and current:
        previous = mg.MotionPage.model_validate(current["page"])
    brief = record["request"] + "".join(f"\nپاسخ کاربر: {a}" for a in record.get("answers", []))
    used: list[str] = []
    scene_notes: list[str] = []
    build = None
    if previous is not None:
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
    notes = scene_notes + notes
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
        record.update(current=number, status="completed", stage="completed", progress=100, message="", error=None, questions=[], pending_change=None, eta_s=None, eta_at=None)
        save(directory, record)
    _emit(cid, "motion.completed", motion_id=key, version=number, duration=page.duration, format=page.format)
    from app import studio_narrator
    studio_narrator.narrate(cid, user, "motion_ready", {"title": page.title, "duration_seconds": page.duration, "format": page.format, "what_it_shows": page.summary,
                            "changes_applied": change or None, "notes_from_the_automatic_check": notes[:3], "person_can_now": "ask for changes to text, colour, timing or size"},
                            fallback=(page.summary or f"موشن‌گرافیک {page.duration:g} ثانیه‌ای آماده شد.") + " اگر چیزی را می‌خواهید عوض کنم (متن، رنگ، زمان‌بندی، اندازه)، همین‌جا بنویسید.")


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


def _plan_and_build(directory: Path, record: dict, brief: str, used: list[str], scene_notes: list[str]):
    """Plan the clip, then design its scenes in parallel while telling the person what is really being worked on. Returns (page, build) or None
    when it asked questions. Finished work is kept on disk: a retry continues from the plan and the scenes that already exist."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from types import SimpleNamespace
    from creative import motion_graphic as mg
    cid, user, key = record["conversation_id"], record["user_key"], record["id"]
    context = record.get("context", "")
    style = record.get("style", "")
    fingerprint = _fingerprint(brief, context, style)
    saved_plan = directory / "plan.json"
    plan = None
    try:
        cached = json.loads(saved_plan.read_text())
        if cached.get("fp") == fingerprint:
            plan = mg.MotionPlan.model_validate(cached["plan"])
    except (OSError, ValueError):
        pass
    stats = _stats()
    if plan is None:
        _progress(directory, "writing", 6, "دارم از روی درخواست شما طرح کلی و صحنه‌ها را می‌نویسم.", stage="writing", eta=stats["plan_s"] + _remaining(4, 15))
        _note(directory, "plan", "دارم طرح کلی را می‌نویسم: صحنه‌ها، متن‌ها و رنگ‌ها")
        started = time.monotonic()
        plan = mg.plan(brief, context=context, style=style, used=used)
        if _cancelled(key):
            raise _Cancelled()
        if plan.asks():
            _note(directory, "plan", "برای ادامه به چند اطلاعات نیاز دارم.", "done")
            _ask(directory, record, plan.questions)
            return None
        _learn("plan_s", time.monotonic() - started)
        saved_plan.write_text(json.dumps({"fp": fingerprint, "plan": plan.model_dump()}, ensure_ascii=False))
        count = len(plan.scenes)
        _note(directory, "plan", f"طرح آماده شد: {count} صحنه، {plan.duration:g} ثانیه", "done")
        outline = "\n".join(f"{i}) {sc.headline} — {sc.idea}" for i, sc in enumerate(plan.scenes, 1))
        from app import studio_narrator
        studio_narrator.narrate(cid, user, "motion_plan", {"title": plan.title, "duration_seconds": plan.duration, "format": plan.format, "signature_idea": plan.signature,
                                "scenes": [{"headline": sc.headline, "what_happens": sc.idea} for sc in plan.scenes]},
                                fallback=f"طرح «{plan.title}» آماده شد ({plan.duration:g} ثانیه، {count} صحنه):\n{outline}\nالان هر صحنه را جداگانه طراحی می‌کنم.")
    else:
        count = len(plan.scenes)
        _note(directory, "plan", f"از طرح قبلی ادامه می‌دهم: {count} صحنه، {plan.duration:g} ثانیه", "done")
    scenes_dir = directory / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    drafts: dict[int, Any] = {}
    for n in range(1, count + 1):                                   # scenes finished by an earlier attempt are not redone
        try:
            cached = json.loads((scenes_dir / f"s{n}.json").read_text())
            if cached.get("fp") == fingerprint:
                drafts[n] = mg.SceneDraft.model_validate(cached["draft"])
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
        _note(directory, f"scene{n}", f"دارم صحنهٔ {n} را طراحی می‌کنم: «{scene.headline}»")
        started = time.monotonic()
        tries = [1]

        def retry(attempt: int, problems: list[str]) -> None:
            tries[0] = attempt
            reasons = "؛ ".join(dict.fromkeys(mg.explain_problem(p) for p in problems[:3]))
            _note(directory, f"scene{n}", f"صحنهٔ {n} («{scene.headline}») از بررسی رد شد: {reasons}. دارم همین صحنه را اصلاح می‌کنم (تلاش {attempt} از {mg.SCENE_ATTEMPTS})")
            left = len(pending) - finished
            _progress(directory, "writing", 8 + int(24 * (done + finished) / count), f"صحنهٔ {n} در حال اصلاح است.", stage="writing",
                      eta=_remaining(left, plan.duration, extra=(mg.SCENE_ATTEMPTS - attempt + 1) * stats["scene_s"] * 0.7))

        try:
            draft = mg.author_scene(plan, n, brief, context=context, used=used, on_retry=retry, style=style)
            _learn("scene_s", (time.monotonic() - started) / tries[0])
            return n, draft, False
        except Exception as exc:
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
                        (scenes_dir / f"s{n}.json").write_text(json.dumps({"fp": fingerprint, "draft": draft.model_dump()}, ensure_ascii=False))
                    _note(directory, f"scene{n}", f"صحنهٔ {n} آماده شد: «{scene.headline}»" + (" (طرح ساده)" if plain else ""), "done")
                    _progress(directory, "writing", 8 + int(24 * (done + finished) / count), f"صحنهٔ {n} از {count} آماده شد.", stage="writing",
                              eta=_remaining(len(pending) - finished, plan.duration))
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    build = SimpleNamespace(plan=plan, drafts=drafts, context=context, style=style, fingerprint=fingerprint, scenes_dir=scenes_dir)
    return mg.assemble_scenes(plan, [drafts[n] for n in range(1, count + 1)]), build


def _scenes_in(problems: list[str], count: int) -> list[int]:
    """Which scenes a check finding points at (its selector names #sN or the Nth section)."""
    found: list[int] = []
    for problem in problems:
        for match in re.finditer(r"#s(\d+)\b|section:nth-of-type\((\d+)\)", problem):
            n = int(match.group(1) or match.group(2))
            if 1 <= n <= count and n not in found:
                found.append(n)
    return found


def _prepare_and_render(directory: Path, page, brief: str, change: str, used: list[str], build=None):
    from creative import motion_graphic as mg
    from engine.hyperframes import standalone
    key = directory.name
    work = directory / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    notes: list[str] = []
    repairs_left = 2
    stats = _stats()
    while True:
        mg.write_project(work, page)
        _progress(directory, "checking", 36, "دارم صفحه را در مرورگر بررسی می‌کنم: چیدمان، خوانایی و خطاهای اجرا.", stage="checking",
                  eta=_remaining(0, page.duration))
        _note(directory, "check", "دارم صحنه‌ها را در مرورگر بررسی می‌کنم: چیدمان، خوانایی متن و خطاهای اجرا")
        started = time.monotonic()
        result = standalone.check(work, should_cancel=lambda: _cancelled(key))
        if result.ran:
            _learn("check_s", time.monotonic() - started)
        if _cancelled(key):
            raise _Cancelled()
        problems = list(result.blocking)
        if not problems:
            # Layout and contrast findings are not fatal and do not justify rewriting the page with a slow model: they are reported.
            notes = (notes + ([f"بررسی خودکار چیدمان/خوانایی: {len(result.quality)} مورد"] if result.quality else [])
                     + [q[:220] for q in result.quality[:4]] + result.notes)[:8]
            break
        reasons = "؛ ".join(dict.fromkeys(mg.explain_problem(p) for p in problems[:3]))
        if repairs_left <= 0:
            raise RuntimeError("did not pass validation: " + problems[0])
        repairs_left -= 1
        hit = _scenes_in(problems, len(build.plan.scenes)) if build else []
        if build and hit:
            # Rebuild only the scenes the findings point at (small requests); a scene that cannot be fixed is replaced by a plain one.
            for n in hit:
                scene = build.plan.scenes[n - 1]
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
            page = mg.assemble_scenes(build.plan, [build.drafts[n] for n in range(1, len(build.plan.scenes) + 1)])
            continue
        _progress(directory, "writing", 38, "مشکلی پیدا شد؛ دارم صفحه را اصلاح می‌کنم.", stage="writing",
                  eta=stats["scene_s"] * 2.5 + stats["check_s"] + stats["render_per_s"] * page.duration)
        _note(directory, "check", f"در بررسی مرورگر مشکل پیدا شد ({reasons}). دارم کل صفحه را اصلاح می‌کنم؛ این مرحله ممکن است چند دقیقه طول بکشد", "active")
        try:
            page = mg.repair(page, "\n".join(problems[:10]), brief=brief, used=used)
        except Exception as exc:
            raise RuntimeError("did not pass validation: " + problems[0]) from exc
    output = work / "motion.mp4"
    render_started = time.monotonic()
    estimate = stats["render_per_s"] * page.duration

    def on_progress(percent: int) -> None:
        elapsed = time.monotonic() - render_started
        _progress(directory, "rendering", 40 + int(percent * 0.55), "دارم ویدیو را فریم‌به‌فریم رندر می‌کنم.", stage="rendering", eta=max(4.0, estimate - elapsed))

    _note(directory, "check", "بررسی صفحه تمام شد", "done")
    _note(directory, "render", f"دارم {page.duration:g} ثانیه ویدیو را فریم‌به‌فریم رندر می‌کنم")
    _progress(directory, "rendering", 40, "دارم ویدیو را فریم‌به‌فریم رندر می‌کنم.", stage="rendering", eta=estimate)
    standalone.render(work, output, timeout=RENDER_TIMEOUT_S, on_progress=on_progress, should_cancel=lambda: _cancelled(key))
    _learn("render_per_s", min(60.0, max(0.3, (time.monotonic() - render_started) / max(page.duration, 1.0))))
    _note(directory, "render", "رندر تمام شد؛ دارم ویدیو را وارسی می‌کنم", "done")
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


def media_path(directory: Path, kind: str, version: Optional[int] = None) -> Path:
    record = load(directory)
    number = version or record.get("current")
    item = _version(record, number)
    if not item:
        raise KeyError("version")
    names = {"video": "motion.mp4", "thumb": "thumb.jpg", "source": "index.html", "page": "page.json"}
    path = directory / f"v{item['n']}" / names[kind]
    if not path.is_file():
        raise KeyError(kind)
    return path


# ── chat-side helpers ────────────────────────────────────────────────────────

def answer(directory: Path, text: str) -> None:
    """The person answered the questions: continue the same request with the answer."""
    with _lock(directory.name):
        record = load(directory)
        record["answers"] = [*record.get("answers", []), text.strip()[:2000]]
        change = record.get("pending_change") or ""
        record.update(status="queued", questions=[])
        save(directory, record)
    start(directory, change=change)


def revise(directory: Path, change: str) -> None:
    with _lock(directory.name):
        record = load(directory)
        record.update(status="queued", stage="queued", progress=0, error=None)
        save(directory, record)
    start(directory, change=change.strip()[:3000])


def recover_interrupted() -> int:
    """After a restart: records left mid-way are marked failed (resumable), never silently stuck as 'working'."""
    count = 0
    for path in ROOT.glob("*/*/motion/*/motion.json"):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if record.get("status") in ACTIVE and time.time() - float(record.get("updated_at") or 0) > 45:       # a worker in another process saves progress every few seconds
            record.update(status="failed", stage="failed", message="ساخت با راه‌اندازی دوبارهٔ سرور قطع شد.", error="interrupted")
            path.write_text(json.dumps(record, ensure_ascii=False))
            count += 1
    return count

