"""EditorGPT Pro: the studio's own talking-head engines as tools (docs/PRO_AGENT_PLAN.md, phase 6 "engine first").

A Pro run that builds a talking edit from scratch makes ~80 model calls with a conversation that grows to 130K tokens (2026-11-19: ~$2.3 with a healthy
cache). The same edit already exists as an engine: `creative.claude_premium` (full frame: virtual camera, two-tier captions, glass cards, text behind
the speaker, graded look) and `creative.claude_talking` (split in two). Each engine plans once (its own model call, outside the agent's conversation),
then builds deterministically with checkpoints and renders on the render cloud. Here Pro starts an engine on a video of its folder, waits, reads the
engine's plan, edits it and renders again, instead of writing the edit itself.

Nothing in the engines, Lite or Medium is changed: the engines are called through their public `make` and, for a revised premium plan, through the
engine's own checkpoint (the plan a restart would continue from). Runs in the app process (the agent container has no keys): a background thread per
job, state in <chat>/.renders/<job>.json, the same file render_status reads.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path

from app.agents import pro

log = logging.getLogger(__name__)

STYLES = {"premium": "creative.claude_premium", "split": "creative.claude_talking"}
ACTIVE = {"queued", "transcribing", "running", "rendering"}
_lock = threading.Lock()
_running: dict[str, str] = {}               # chat id -> the engine job running in it (one at a time per chat)


def _state_file(cid: str, job: str) -> Path:
    if not job.isalnum():
        raise ValueError("bad job id")
    folder = pro.RUNS / cid / ".renders"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{job}.json"


def state(cid: str, job: str) -> dict:
    path = _state_file(cid, job)
    if not path.is_file():
        raise ValueError("no such job")
    return json.loads(path.read_text())


def _engine(style: str):
    import importlib
    if style not in STYLES:
        raise ValueError(f"style must be one of {', '.join(STYLES)}")
    return importlib.import_module(STYLES[style])


def _work(cid: str, style: str, video: Path) -> Path:
    return pro.inside(cid, f"engine/{style}/{video.stem}")


def _transcript(cid: str, video: Path) -> dict:
    """The words with times: the stt tool's file when the agent already made one for this video, else ElevenLabs Scribe now (cached the same way)."""
    import hashlib
    cached = pro.inside(cid, f"transcripts/{video.stem}.json")
    if cached.is_file():
        data = json.loads(cached.read_text())
        if data.get("words"):
            return data
    from brain.transcribe_elevenlabs import transcribe_elevenlabs
    folder = pro.inside(cid, ".stt")
    folder.mkdir(parents=True, exist_ok=True)
    data, _cost = transcribe_elevenlabs(video, folder, language="fa", file_digest=hashlib.sha256(video.read_bytes()).hexdigest())
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data, ensure_ascii=False))
    if not data.get("words"):
        raise ValueError("no speech with word times was found in this video")
    return data


def _plan_file(work: Path) -> Path:
    return work / "plan.json"


def _keep_plan(work: Path) -> None:
    """The engine's plan, copied where the agent can read and edit it (the checkpoint holds it after the plan step)."""
    try:
        ck = json.loads((work / "checkpoint.json").read_text())
    except (OSError, ValueError):
        return
    if ck.get("plan"):
        _plan_file(work).write_text(json.dumps(ck["plan"], ensure_ascii=False, indent=1))


def _apply_plan(engine, work: Path, video: Path, words: list[dict], context: str, edited: dict) -> None:
    """A premium plan the agent edited becomes the plan the engine continues from: the engine's own checkpoint, with the graphics code kept only for
    props whose brief did not change and the render marked as not done (the cut, grade and cut-outs are reused by the engine when still valid)."""
    plan = engine.sanitize(engine.Plan.model_validate(edited), words)
    fp = engine._fingerprint(video, words, context)
    ck = engine._load_checkpoint(work, fp)
    old = {p["name"]: p for p in ((ck.get("plan") or {}).get("props") or [])}
    code = {name: text for name, text in (ck.get("code") or {}).items()
            if name in old and any(p.name == name and p.model_dump() == old[name] for p in plan.props)}
    engine._save_checkpoint(work, fp, ck, plan=plan.model_dump(), code=code, rendered=False)


def start(claims: dict, args: dict, *, revise: bool = False, loop=None) -> dict:
    """`loop`: the app's event loop; progress lines go to the chat through it (an asyncio.run in this thread would deadlock on the shared database pool)."""
    cid, user, rid = claims["cid"], str(claims["user"]), claims["run"]
    style = str(args.get("style") or "premium").strip().lower()
    engine = _engine(style)
    video = pro.inside(cid, str(args.get("path") or ""))
    if not video.is_file():
        raise ValueError("video file not found in the working folder")
    work = _work(cid, style, video)
    work.mkdir(parents=True, exist_ok=True)
    context_file = work / "context.txt"
    if revise:
        if not context_file.is_file():
            raise ValueError("this video was not edited with this style yet: run talking_edit first")
        context = context_file.read_text()
        plan_path = pro.inside(cid, str(args.get("plan") or _plan_file(work).relative_to(pro.workdir(cid))))
        if style != "premium":
            raise ValueError("only the premium engine takes an edited plan; for split, run talking_edit again with new direction")
        try:
            edited = json.loads(plan_path.read_text())
        except (OSError, ValueError) as exc:
            raise ValueError(f"the plan file could not be read as JSON: {exc}") from exc
    else:
        context = str(args.get("direction") or "").strip()[:2000]
        context_file.write_text(context)
        edited = None
    with _lock:
        busy = _running.get(cid)
        if busy and state(cid, busy).get("state") in ACTIVE:
            raise ValueError(f"engine job {busy} is still running in this chat: wait for it with job_wait")
        job = uuid.uuid4().hex[:12]
        _running[cid] = job
    out_dir = pro.inside(cid, "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    version = 1 + len(list(out_dir.glob(f"{video.stem}-{style}-v*.mp4")))
    out = out_dir / f"{video.stem}-{style}-v{version}.mp4"
    path = _state_file(cid, job)
    current = {"job_id": job, "kind": "talking_edit", "style": style, "state": "queued", "progress": 0, "output": str(out.relative_to(pro.workdir(cid))),
               "notes": []}
    path.write_text(json.dumps(current, ensure_ascii=False))

    def save(**values):
        data = json.loads(path.read_text())
        data.update(values)
        path.write_text(json.dumps(data, ensure_ascii=False))

    def note(step: str, text: str, state_: str = "active", detail: str | None = None) -> None:
        data = json.loads(path.read_text())
        data["notes"] = (data.get("notes") or [])[-11:] + [f"{step}: {text}"[:300]]
        path.write_text(json.dumps(data, ensure_ascii=False))
        _emit(loop, cid, rid, text)

    checked = {"at": 0.0, "stop": False}

    def cancelled() -> bool:
        """The person stopped the run, or it ended: asked on the app's loop every few seconds (never asyncio.run in this thread)."""
        if loop is None or loop.is_closed() or time.time() - checked["at"] < 5:
            return checked["stop"]
        checked["at"] = time.time()
        try:
            import asyncio
            from app.agents import store
            record = asyncio.run_coroutine_threadsafe(store.get_run(rid, user), loop).result(timeout=15)
            checked["stop"] = record.get("status") != "running"
        except Exception:
            pass                                   # unknown: keep working
        return checked["stop"]

    def progress(percent: int, message: str) -> None:
        save(state="rendering" if "رندر" in message else "running", progress=int(percent), stage=str(message)[:200])

    def music(_feel: str, _total: float):
        pick = str(args.get("music") or "").strip()
        if pick == "none":
            return None
        if pick:
            chosen = pro.inside(cid, pick)
            if chosen.is_file():
                return chosen
        return engine.KIT / "music.mp3"

    def cloud(project: Path, target: Path) -> bool:
        from app.render_cloud import hooks
        return bool(hooks.claude_motion(project, target, timeout=5400, user=user, project_id="pro" + rid, owned_roots=(pro.workdir(cid),)))

    def work_thread():
        from brain.lm_gateway import work_scope
        try:
            with work_scope("pro", rid, user=user, conversation=cid):       # the engine's own model calls are billed to this person's run
                save(state="transcribing", progress=2)
                transcript = _transcript(cid, video)
                if edited is not None:
                    from creative.claude_talking import indexed
                    _apply_plan(engine, work, video, indexed(transcript), context, edited)
                save(state="running", progress=5)
                result = engine.make(video, transcript, work, out, note=note, progress=progress, cancelled=cancelled, render_cloud=cloud, music=music,
                                     context=context)
            _keep_plan(work)
            save(state="done", progress=100, duration=round(float(result.get("duration") or 0), 2),
                 plan=str(_plan_file(work).relative_to(pro.workdir(cid))) if _plan_file(work).is_file() else None,
                 size_bytes=out.stat().st_size if out.is_file() else 0)
        except Exception as exc:
            _keep_plan(work)
            stopped = type(exc).__name__ == "Cancelled"
            if not stopped:
                log.warning("pro engine job %s failed", job, exc_info=True)
            save(state="failed", error="stopped" if stopped else f"{type(exc).__name__}: {str(exc)[:400]}")
        finally:
            with _lock:
                if _running.get(cid) == job:
                    _running.pop(cid, None)

    threading.Thread(target=work_thread, daemon=True, name=f"pro-engine-{job}").start()
    _emit(loop, cid, rid, "موتور تدوین استودیو شروع به کار کرد")
    return {"job_id": job, "state": "queued", "output": current["output"],
            "note": "Wait with job_wait (it waits on the server up to 240 s per call). When done, look at a few stills of the output, then deliver, or "
                    "read the plan file, edit it and call talking_revise."}


def _emit(loop, cid: str, rid: str, text: str) -> None:
    """A progress line in the chat's activity, sent on the app's loop and not waited for (never blocks the engine)."""
    if loop is None or loop.is_closed():
        return
    try:
        import asyncio
        from app.studio_store import repo
        asyncio.run_coroutine_threadsafe(repo.emit(cid, "tool.progress", {"tool": "pro_engine", "stage": "pro", "message": str(text)[:200],
                                                                          "agent_mode": "pro", "run_id": rid}), loop)
    except Exception:
        log.debug("pro engine progress event not sent", exc_info=True)


async def wait(cid: str, job: str, seconds: float) -> dict:
    """Wait on the server for an engine job or a cloud render to end (up to 240 s), so the agent does not spend a model call per poll."""
    import asyncio
    deadline = time.monotonic() + max(5.0, min(float(seconds or 240), 240.0))
    while True:
        data = state(cid, job)
        if data.get("state") not in ACTIVE or time.monotonic() >= deadline:
            data["waited_until_end"] = data.get("state") not in ACTIVE
            return data
        await asyncio.sleep(3)
