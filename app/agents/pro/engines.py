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
        resume = bool(args.get("resume")) and (work / "checkpoint.json").is_file() and context_file.is_file()
        if (work / "checkpoint.json").is_file() and not args.get("fresh") and not resume:
            raise ValueError("this video was already edited with this engine: after a failed or stopped job call talking_edit with resume=true (it goes on "
                             "from the engine's checkpoint: the plan, the written graphics, the cut, grade and cut-outs are reused, nothing is made again); "
                             "for a correction edit its plan file and call talking_revise. Only if the person wants a completely new edit, fresh=true.")
        if args.get("fresh") and not resume:
            (work / "checkpoint.json").unlink(missing_ok=True)      # a completely new edit: the engine plans, cuts and designs again
        if resume:
            context = context_file.read_text()                       # the same direction: the checkpoint belongs to it
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
        picture = None
        if step == "review" and not shown.get("review") and (work / "qa" / "sheet.jpg").is_file():     # the stills the engine checks, on its row
            shown["review"] = True
            picture = work / "qa" / "sheet.jpg"
        _emit(loop, claims, text, step=f"{job}-{step}", done=state_ == "done", detail=detail or "", image=picture)

    shown: dict = {}
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

    last = {"label": "", "percent": -10}

    def progress(percent: int, message: str) -> None:
        save(state="rendering" if "رندر" in message else "running", progress=int(percent), stage=str(message)[:200])
        label = str(message).split("(")[0].split("…")[0].strip()[:70]
        if label != last["label"] or int(percent) - last["percent"] >= 5:        # the engine's overall progress: one row that moves, not an event a second
            last.update(label=label, percent=int(percent))
            _emit(loop, claims, f"موتور تدوین · {int(percent)}٪ · {label}", step=f"{job}-progress", progress=int(percent), quiet=True)
            _card(loop, claims, path)

    def music(_feel: str, _total: float):
        pick = str(args.get("music") or "").strip()
        if pick == "none":
            return None
        if pick:
            chosen = pro.inside(cid, pick)
            if chosen.is_file():
                return chosen
        return engine.KIT / "music.mp3"

    cloud_seen = {"at": 0.0}

    def cloud_report(**values) -> None:
        """What the render cloud says (worker stage, its own percent, its detail line), on the render card like Lite's."""
        data = json.loads(path.read_text())
        report = {**(data.get("cloud") or {}), **{k: v for k, v in values.items() if v is not None}}
        save(cloud=report, state="rendering")
        if time.time() - cloud_seen["at"] > 3 or values.get("progress") in (0, 100):
            cloud_seen["at"] = time.time()
            _card(loop, claims, path)
            cloud_step(loop, claims, f"{job}-cloud", report, cloud_seen)

    def cloud(project: Path, target: Path) -> bool:
        from app.render_cloud import hooks
        return bool(hooks.claude_motion(project, target, timeout=5400, user=user, project_id="pro" + rid, owned_roots=(pro.workdir(cid),),
                                        on_progress=lambda p: cloud_report(progress=int(p)), on_stage=lambda st: cloud_report(stage=str(st)[:120]),
                                        on_detail=lambda text: cloud_report(detail=str(text)[:240])))

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
            _emit(loop, claims, "موتور تدوین · ویدیو آماده شد", step=f"{job}-progress", done=True, progress=100)
            if cloud_seen.get("opened"):
                cloud_step(loop, claims, f"{job}-cloud", {"stage": "done", "progress": 100}, cloud_seen, final=True)
            save(state="done", progress=100, duration=round(float(result.get("duration") or 0), 2),
                 plan=str(_plan_file(work).relative_to(pro.workdir(cid))) if _plan_file(work).is_file() else None,
                 size_bytes=out.stat().st_size if out.is_file() else 0)
            _card(loop, claims, path, video=out if out.is_file() else None)
        except Exception as exc:
            _keep_plan(work)
            stopped = type(exc).__name__ == "Cancelled"
            if not stopped:
                log.warning("pro engine job %s failed", job, exc_info=True)
            _emit(loop, claims, "موتور تدوین متوقف شد" if stopped else "موتور تدوین به خطا خورد", step=f"{job}-progress", done=True)
            save(state="failed", error="stopped" if stopped else f"{type(exc).__name__}: {str(exc)[:400]}")
            _card(loop, claims, path)
        finally:
            with _lock:
                if _running.get(cid) == job:
                    _running.pop(cid, None)

    threading.Thread(target=work_thread, daemon=True, name=f"pro-engine-{job}").start()
    _emit(loop, claims, "موتور تدوین استودیو شروع به کار کرد", step=f"{job}-start", done=True)
    _card(loop, claims, path)
    return {"job_id": job, "state": "queued", "output": current["output"],
            "note": "Wait with job_wait (it waits on the server up to 240 s per call). When done, look at a few stills of the output, then deliver, or "
                    "read the plan file, edit it and call talking_revise."}


def _emit(loop, claims: dict, text: str, *, step: str = "", done: bool = False, detail: str = "", progress: int | None = None,
          quiet: bool = False, image: Path | None = None) -> None:
    """One row of the chat's timeline per engine step (the plan, each graphic, the cut and grade, the face, the cut-outs, review, render, mix):
    tool.started while it runs, tool.completed when the engine says it is done; `quiet` rows only move (tool.progress); `image` (the engine's
    stills) is shown on the row. Sent on the app's loop and not waited for, so it never blocks the engine."""
    if loop is None or loop.is_closed():
        return
    kind = "tool.progress" if quiet else ("tool.completed" if done else "tool.started")
    import re
    full = str(text).strip()
    # The row's title must be short (the timeline shows a generic word for a long one): the engine's first clause; the whole line and the
    # engine's material stay in the row's detail, like Lite's own steps.
    title = re.split(r"[:؛،.]\s", full, maxsplit=1)[0].strip()
    if len(title) > 64:
        title = title[:62].rsplit(" ", 1)[0] + "…"
    data = {"tool": "pro_engine", "stage": "pro", "message": title or full[:64], "agent_mode": "pro", "run_id": claims["run"],
            "activity_id": "engine-" + (step or "work")[:80]}
    if full != title or detail:
        data["response"] = (full + ("\n\n" + str(detail) if detail else ""))[:3000]
    if progress is not None:
        data["progress"] = int(progress)

    async def send():
        from app.studio_store import repo
        if image is not None and image.is_file():
            try:
                from app.routers.agent_proxy import _attach
                data["image"] = (await _attach(claims, image))["id"]
            except Exception:
                log.debug("engine still not attached", exc_info=True)
        await repo.emit(claims["cid"], kind, data)
    _send(loop, send)


def _card(loop, claims: dict, path: Path, *, video: Path | None = None) -> None:
    """The render card of an engine job (`pro.job`): stage, percent, the render cloud's own report, and the finished video, like Lite's card."""
    if loop is None or loop.is_closed():
        return
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return
    card = {k: data.get(k) for k in ("job_id", "style", "state", "progress", "stage", "error", "duration", "cloud", "with_audio")}
    card.update(agent_mode="pro", run_id=claims["run"])

    async def send():
        from app.studio_store import repo
        if video is not None:
            try:
                from app.routers.agent_proxy import _attach
                card["attachment_id"] = (await _attach(claims, video))["id"]
            except Exception:
                log.warning("engine video not attached to its card", exc_info=True)
        await repo.emit(claims["cid"], "pro.job", card)
    _send(loop, send)


def _send(loop, make) -> None:
    try:
        import asyncio
        asyncio.run_coroutine_threadsafe(make(), loop)
    except Exception:
        log.debug("pro engine event not sent", exc_info=True)


async def wait(cid: str, job: str, seconds: float, user: str = "") -> dict:
    """Wait on the server for an engine job, a film or a cloud render to end (up to 14 min), so the agent does not spend a model call per poll."""
    import asyncio
    deadline = time.monotonic() + max(5.0, min(float(seconds or 840), 840.0))          # under the agent's 15-minute tool timeout
    film = not _state_file(cid, job).is_file() and bool(user)
    while True:
        data = await asyncio.to_thread(film_state, cid, user, job) if film else state(cid, job)
        running = data.get("state") in ACTIVE or (film and data.get("state") in ("writing", "checking"))
        if not running or time.monotonic() >= deadline:
            data["waited_until_end"] = not running
            return data
        await asyncio.sleep(4)


# ── films: the studio's motion, Vox and intro engines (app.motion_graphic), Pro-only entry points ───────────────────────────────────────────────

FILM_KINDS = {"motion", "vox", "intro-story", "intro-reel", "intro-presenter", "intro-film3d"}


async def film_start(claims: dict, args: dict) -> dict:
    """A film made by the studio's own film engines, exactly as Lite makes it (the same record, the same motion card in the chat with its frames,
    log and video), only started by the Pro agent: motion = the Claude motion film from text; vox = the Vox-style documentary; intro-* = the intro
    engines (story / reel / presenter needs the presenter's video / film3d). Nothing in app.motion_graphic is changed: create(), then the engine
    choice the agent made is written into the record, then start()."""
    import asyncio
    from app import motion_graphic as mg
    from app.studio_store import repo
    cid, user = claims["cid"], str(claims["user"])
    kind = str(args.get("kind") or "motion").strip().lower()
    if kind not in FILM_KINDS:
        raise ValueError(f"kind must be one of {', '.join(sorted(FILM_KINDS))}")
    request = str(args.get("request") or "").strip()
    if len(request) < 4:
        raise ValueError("request is empty: say what the film is about and what it must say")
    conversation = await repo.get_conversation(cid, user)
    state_ = conversation.get("state") or {}
    pointer = state_.get("motion")
    if pointer:
        try:
            if mg.load(mg.locate(pointer["motion_id"], user))["status"] in mg.ACTIVE:
                raise ValueError(f"film {pointer['motion_id']} is still being made in this chat: wait for it with job_wait")
        except (KeyError, OSError):
            pass
    ids = [str(i) for i in (args.get("asset_ids") or [])][:8]
    rows = await repo.get_attachments(ids, cid, user) if ids else []
    if kind == "intro-presenter" and not any(r["kind"] == "video" for r in rows):
        raise ValueError("the presenter intro needs the presenter's video: pass its asset id in asset_ids")
    attachments = [{"kind": r["kind"], "path": r["path"], "filename": r["filename"], "id": r["id"]} for r in rows] or None
    context = str(args.get("context") or "")[:9000]
    style = str(args.get("style") or "")[:2000]
    record = await asyncio.to_thread(mg.create, cid, user, request, context, style, state_.get("voice_id", ""), state_.get("voice_style", ""),
                                     attachments=attachments)
    if record.get("engine") != "claude":
        raise ValueError("the studio's film engines are switched off on this server; build the film by hand")
    directory = mg.folder(user, cid, record["id"])
    record.pop("vox", None)
    record.pop("intro", None)
    if kind == "vox":
        record["vox"] = True
    elif kind.startswith("intro-"):
        record["intro"] = kind.split("-", 1)[1]
        footage = next((r for r in rows if r["kind"] == "video"), None)
        if footage:
            record["intro_footage"] = str(footage["path"])
    mg.save(directory, record)
    await repo.set_conversation(cid, user, state={**state_, "motion": {"motion_id": record["id"]}})
    await repo.emit(cid, "motion.created", {"motion_id": record["id"]})
    await asyncio.to_thread(mg.start, directory)
    return {"film_id": record["id"], "kind": kind, "state": "queued",
            "note": "The film card in the chat shows its frames and log. Wait with job_wait(job_id=film_id). If it asks questions, ask the person and "
                    "pass the answer with film_revise(answer=...). When it is done the video is copied into out/."}


async def film_revise(claims: dict, args: dict) -> dict:
    """A change to the chat's film (a new version of the SAME film, the engine keeps what did not change), or the answer to a question it asked:
    Lite's own follow-up path (narrator and music words, pronunciation fixes, answers)."""
    import asyncio
    from app import motion_graphic as mg
    from app import studio_orchestrator as so
    from app.studio_store import repo
    cid, user = claims["cid"], str(claims["user"])
    film = str(args.get("film_id") or "")
    text = str(args.get("change") or args.get("answer") or "").strip()
    if not text:
        raise ValueError("say the change (change) or the answer (answer)")
    directory = mg.locate(film, user)
    record = mg.load(directory)
    if record["status"] in mg.ACTIVE and not args.get("answer"):
        raise ValueError("the film is still being made: wait for it with job_wait, then ask for the change")
    conversation = await repo.get_conversation(cid, user)
    state_ = conversation.get("state") or {}
    if (state_.get("motion") or {}).get("motion_id") != film:
        await repo.set_conversation(cid, user, state={**state_, "motion": {"motion_id": film}})
        conversation = await repo.get_conversation(cid, user)
    await repo.emit(cid, "motion.created", {"motion_id": film})
    handled = await asyncio.to_thread(so._continue_motion_graphic, cid, user, conversation, text, answering=bool(args.get("answer")))
    if not handled:
        raise ValueError("the film could not be continued")
    return {"film_id": film, "state": "queued", "note": "A new version is being made on the same film: wait with job_wait(job_id=film_id)."}


def film_state(cid: str, user: str, film: str) -> dict:
    """The film's state for the agent: done / failed / asking / still running, its progress and last log lines; a finished version is copied into
    out/ so the agent can look at it."""
    from app import motion_graphic as mg
    directory = mg.locate(film, user)
    view = mg.view(directory)
    out = {"film_id": film, "state": {"completed": "done", "needs_input": "asking"}.get(view["status"], view["status"]),
           "progress": view["progress"], "message": view["message"], "error": view["error"], "questions": view["questions"],
           "log": [f"{e.get('key', '')}: {e.get('text', '')}"[:200] for e in (view.get("log") or [])[-8:] if isinstance(e, dict)]}
    if view["status"] == "completed" and view.get("current"):
        try:
            source = mg.media_path(directory, "video", int(view["current"]))
            target = pro.inside(cid, f"out/film-{film}-v{view['current']}.mp4")
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(source, target)
            out["output"] = str(target.relative_to(pro.workdir(cid)))
            out["version"] = view["current"]
        except (KeyError, OSError):
            pass
    return out


# ── which engine can make the look the person wants: one vision call outside the agent's conversation ─────────────────────────────────────────

LOOKS = {"premium": "talking engine, premium full frame", "split": "talking engine, split in two", "motion": "film engine, motion graphics",
         "vox": "film engine, Vox-style documentary", "intro-story": "film engine, brand intro (story)", "intro-reel": "film engine, brand intro (reel)"}
JOB_DATA = Path("/app/job_data")


def _look_videos(kind: str, limit: int = 2) -> list[Path]:
    """Real outputs this server's engines made (the newest first): what each engine's look really is."""
    import glob
    import os
    found: list[Path] = []
    if kind in ("premium", "split"):
        want = "claude_premium" if kind == "premium" else "claude_talking"
        for f in sorted(glob.glob(str(JOB_DATA / "*" / "talking_reel.json")), key=os.path.getmtime, reverse=True):
            try:
                d = json.loads(Path(f).read_text())
            except (OSError, ValueError):
                continue
            if d.get("engine") == want and d.get("status") == "done" and d.get("output") and (Path(f).parent / d["output"]).is_file():
                found.append(Path(f).parent / d["output"])
            if len(found) >= limit:
                break
        return found
    from app import motion_graphic as mg
    for f in sorted(glob.glob(str(JOB_DATA / "studio" / "*" / "*" / "motion" / "*" / "motion.json")), key=os.path.getmtime, reverse=True):
        try:
            d = json.loads(Path(f).read_text())
        except (OSError, ValueError):
            continue
        k = ("intro-" + d["intro"]) if d.get("intro") else "vox" if d.get("vox") else "motion" if d.get("engine") == "claude" else None
        if k != kind or d.get("status") != "completed" or not d.get("current"):
            continue
        try:
            found.append(mg.media_path(Path(f).parent, "video", int(d["current"])))
        except (KeyError, OSError, ValueError):
            continue
        if len(found) >= limit:
            break
    return found


def _label(path: Path, text: str) -> Path:
    """The sheet's label written on it (SAMPLE / ENGINE: key), so a vision model never mixes the images up."""
    from PIL import Image, ImageDraw, ImageFont
    image = Image.open(path).convert("RGB")
    band = 54
    out = Image.new("RGB", (image.width, image.height + band), (255, 255, 255))
    out.paste(image, (0, band))
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    draw.text((14, 9), text, fill=(0, 0, 0), font=font)
    target = path.with_name(path.stem + "-labelled.jpg")
    out.save(target, quality=82)
    return target


def _frames_sheet(sources: list[Path], target: Path, per_video: int = 4, height: int = 360, offsets: tuple = ()) -> Path | None:
    """A contact sheet: `per_video` frames spread over each source (a picture counts as one frame), one row per source. `offsets` (0-1, one per
    row) shift where a row's frames are taken, so one video can fill two rows with different moments."""
    import subprocess
    import tempfile
    from PIL import Image
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, source in enumerate(sources):
            frames = []
            if source.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                frames = [Image.open(source).convert("RGB")]
            else:
                try:
                    duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(source)],
                                                    capture_output=True, text=True, timeout=60).stdout.strip() or 0)
                except (ValueError, subprocess.SubprocessError):
                    duration = 0
                shift = offsets[n] if n < len(offsets) else 0.0
                for i in range(per_video):
                    at = duration * ((i + 0.25 + shift * 0.5) / per_video) if duration else i
                    out = Path(tmp) / f"{n}_{i}.jpg"
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(source), "-frames:v", "1", "-vf", f"scale=-2:{height}", str(out)],
                                   capture_output=True, timeout=120)
                    if out.is_file():
                        frames.append(Image.open(out).convert("RGB"))
            if frames:
                frames = [f.resize((max(1, int(f.width * height / f.height)), height)) for f in frames]
                row = Image.new("RGB", (sum(f.width for f in frames) + 8 * (len(frames) - 1), height), (20, 20, 20))
                x = 0
                for f in frames:
                    row.paste(f, (x, 0))
                    x += f.width + 8
                rows.append(row)
    if not rows:
        return None
    sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows) + 8 * (len(rows) - 1)), (20, 20, 20))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 8
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.thumbnail((1600, 1600))
    sheet.save(target, quality=82)
    return target


def look_sheet(kind: str) -> Path | None:
    """The look sheet of one engine, made once from its real outputs and kept (rebuilt after a week)."""
    target = pro.RUNS / ".looks" / f"{kind}.jpg"
    if target.is_file() and time.time() - target.stat().st_mtime < 7 * 86400:
        return target
    videos = _look_videos(kind)
    return _frames_sheet(videos, target) if videos else None


COMPARE = """You decide which video engine of a studio can make the look a person wants, by LOOKING at the images. Every image has its label
written on it: the image labelled SAMPLE is the person's reference (frames of a video or their picture); each image labelled ENGINE: <key> shows
real outputs of that studio engine. An engine has ONE fixed visual language (layout, framing, captions, graphics, colour, motion); a film engine
also accepts a written style direction (colours, type, mood) but not a different layout system or editing grammar. Never describe an engine's
pictures as the sample's. Compare: framing/layout and how it changes between shots, background, typography, colour treatment, graphics, rhythm.

Answer with ONE JSON object and nothing else, with exactly these keys:
closest: the key of the closest engine, or "none"
match: a number 0-100, how close that engine's OWN look is to the sample
same: a list of short strings, what the engine already does like the sample
missing: a list of short strings, what the sample has and the engine does not
decision: one of "engine" (match 70 or more), "engine_with_style" (only for a film engine that gets there with a written style), "build" (no engine makes this look)
style_brief: 4-7 concrete English lines describing the SAMPLE only: framing and layout changes, camera moves (punch-ins, zooms, shakes), cut
rhythm (seconds between cuts, jump cuts on pauses), backgrounds, type, colour, graphics, transitions, and SOUND (music bed and its mood/tempo,
sound effects, how the voice sits in the mix) — the sound and the rhythm are often most of a sample's appeal; use the MEASURED facts
say: one short natural Persian sentence for the person saying what will be done and why"""


def _measure(video: Path) -> dict:
    """What frames cannot show: the sample's cut rhythm and its sound. Cuts from ffmpeg's scene score; a music bed = speech with (almost) no silent
    gaps under it (a voice alone falls silent between phrases); loudness of the quietest moments."""
    import re
    import subprocess
    if video.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        return {}
    out: dict = {}
    try:
        duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                                        capture_output=True, text=True, timeout=60).stdout.strip() or 0)
        out["duration_s"] = round(duration, 1)
        scenes = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vf", "select='gt(scene,0.32)',showinfo", "-an", "-f", "null", "-"],
                                capture_output=True, text=True, timeout=300).stderr
        cuts = len(re.findall(r"pts_time:", scenes))
        out["cuts"] = cuts
        out["average_shot_s"] = round(duration / (cuts + 1), 2) if duration else None
        has_audio = "Audio:" in subprocess.run(["ffprobe", "-hide_banner", str(video)], capture_output=True, text=True, timeout=60).stderr
        if has_audio:
            silent = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af", "silencedetect=n=-42dB:d=0.25", "-f", "null", "-"],
                                    capture_output=True, text=True, timeout=300).stderr
            gaps = len(re.findall(r"silence_start", silent))
            out["silent_gaps"] = gaps
            out["music_bed_likely"] = bool(duration) and gaps <= max(1, int(duration / 20))
            stats = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af", "ebur128", "-f", "null", "-"],
                                   capture_output=True, text=True, timeout=300).stderr
            lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", stats)
            out["loudness_lufs"] = float(lufs[-1]) if lufs else None
        else:
            out["has_audio"] = False
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return out


def compare_style(claims: dict, args: dict) -> dict:
    """Which engine (if any) makes the look the person wants: their sample next to each engine's real outputs, judged by a vision model in ONE call
    outside the agent's conversation (only this short answer enters it)."""
    from brain.llm import chat_vision
    cid = claims["cid"]
    family = str(args.get("for") or "any").strip().lower()
    kinds = [k for k in LOOKS if family == "any" or (family == "talking" and k in ("premium", "split")) or (family == "film" and k not in ("premium", "split"))]
    description = str(args.get("description") or "").strip()[:1500]
    sample = str(args.get("sample") or "").strip()
    measured: dict = {}
    images: list[str] = []
    if sample:
        source = pro.inside(cid, sample)
        if not source.is_file():
            raise ValueError("sample file not found in the working folder")
        sheet = _frames_sheet([source, source], pro.inside(cid, f".looks/sample-{source.stem}.jpg"), per_video=4, height=360, offsets=(0.0, 0.5))
        if not sheet:
            raise ValueError("no frames could be read from the sample")
        images.append(str(_label(sheet, "SAMPLE")))
        measured = _measure(source)
    elif not description:
        raise ValueError("give a sample file or a description of the look")
    listed = []
    for kind in kinds:
        sheet = look_sheet(kind)
        if sheet:
            images.append(str(_label(sheet, f"ENGINE: {kind}")))
            listed.append(kind)
    if not listed:
        return {"closest": "none", "decision": "build", "note": "no engine outputs on this server to compare with"}
    user = (("" if sample else "There is no SAMPLE image; the wanted look, in the person's words: " + description + "\n")
            + (f"The person's words: {description}\n" if sample and description else "")
            + (f"MEASURED on the sample (frames cannot show these): {json.dumps(measured)}. music_bed_likely = music plays under the speech the whole "
               "time; average_shot_s = seconds between cuts.\n" if measured else "")
            + "The engines: " + "; ".join(f"{k} = {LOOKS[k]}" for k in listed) + ".\nAnswer with the JSON object only.")
    raw, _usage = chat_vision(COMPARE, user, images=images, route="visual_qc", return_json=True, max_tokens=1200, timeout_seconds=180)
    if not isinstance(raw, dict):
        raise ValueError("the comparison gave no answer")
    keep = {k: raw.get(k) for k in ("closest", "match", "same", "missing", "decision", "style_brief", "say")}
    keep["engines_compared"] = listed
    if measured:
        keep["measured"] = measured
    return keep


# ── the agent's heavy ffmpeg passes on the render cloud (ffmpeg_job), the server as fallback ─────────────────────────────────────────────────

def start_ffmpeg(claims: dict, args: dict, *, loop=None) -> dict:
    """Heavy ffmpeg work (a jump cut, a grade, a long encode) off this server: `inputs` are files of the folder (their NAMES are used in the
    steps), `steps` are ffmpeg argument lists run in order, the last writes result.mp4, which becomes `output`. Returns a job id at once; the
    render card shows it; wait with job_wait."""
    cid, user, rid = claims["cid"], str(claims["user"]), claims["run"]
    inputs = [pro.inside(cid, str(p)) for p in (args.get("inputs") or [])][:8]
    for path in inputs:
        if not path.is_file():
            raise ValueError(f"input not found: {path.name}")
    names = [p.name for p in inputs]
    if len(set(names)) != len(names):
        raise ValueError("inputs must have different file names")
    steps = args.get("steps") or []
    if not isinstance(steps, list) or not steps or not all(isinstance(s, list) and all(isinstance(a, str) for a in s) for s in steps):
        raise ValueError("steps is a list of ffmpeg argument lists (without the word ffmpeg); the last writes result.mp4")
    if not any("result." in a for a in steps[-1]):
        raise ValueError("the last step must write result.mp4")
    output = pro.inside(cid, str(args.get("output") or "out/heavy.mp4"))
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = int(args.get("width") or 0), int(args.get("height") or 0)
    max_duration = float(args.get("max_duration") or 0)
    if not width or not height or max_duration <= 0:
        raise ValueError("give the output's width, height and max_duration (seconds)")
    job = uuid.uuid4().hex[:12]
    path = _state_file(cid, job)
    path.write_text(json.dumps({"job_id": job, "kind": "ffmpeg", "style": "ffmpeg", "state": "queued", "progress": 0,
                                "output": str(output.relative_to(pro.workdir(cid))), "with_audio": True}, ensure_ascii=False))

    def save(**values):
        data = json.loads(path.read_text())
        data.update(values)
        path.write_text(json.dumps(data, ensure_ascii=False))

    seen: dict = {}

    def report(**values):
        current = json.loads(path.read_text())
        merged = {**(current.get("cloud") or {}), **values}
        save(cloud=merged)
        if time.time() - seen.get("at", 0) > 3:
            seen["at"] = time.time()
            _card(loop, claims, path)
            cloud_step(loop, claims, f"{job}-cloud", merged, seen)

    def work():
        from app.render_cloud import hooks
        from brain.lm_gateway import work_scope
        try:
            save(state="running", stage="ارسال به سرور ابری")
            _card(loop, claims, path)
            with work_scope("pro", rid, user=user, conversation=cid):
                where = hooks.run_ffmpeg_steps(inputs, steps, output, width=width, height=height, max_duration=max_duration, timeout=3600,
                                               user=user, project_id="pro" + rid, owned_roots=(pro.workdir(cid),),
                                               on_progress=lambda p: save(progress=int(p)),
                                               on_stage=lambda st: report(stage=str(st)[:120]),
                                               on_detail=lambda text: report(detail=str(text)[:240]))
            if seen.get("opened"):
                cloud_step(loop, claims, f"{job}-cloud", {"stage": "done", "progress": 100}, seen, final=True)
            save(state="done", progress=100, where=where, size_bytes=output.stat().st_size if output.is_file() else 0)
        except Exception as exc:
            log.warning("pro ffmpeg job %s failed", job, exc_info=True)
            save(state="failed", error=f"{type(exc).__name__}: {str(exc)[-400:]}")
        _card(loop, claims, path)

    threading.Thread(target=work, daemon=True, name=f"pro-ffmpeg-{job}").start()
    return {"job_id": job, "state": "queued", "output": str(output.relative_to(pro.workdir(cid))),
            "note": "Wait with job_wait (it waits on the server until the end). The work runs on the render cloud, or on the server if the cloud does not take it."}


CLOUD_STAGE_FA = {"queued": "در صف سرور ابری", "provisioning": "روشن شدن سرور ابری", "preparing": "آماده‌سازی روی سرور ابری",
                  "uploading": "دریافت خروجی از سرور ابری", "downloading": "ارسال فایل‌ها به سرور ابری", "rendering": "رندر روی سرور ابری",
                  "muxing": "گذاشتن صدا روی ویدیو", "done": "رندر ابری تمام شد", "failed": "رندر ابری متوقف شد"}


def cloud_step(loop, claims: dict, step: str, report: dict, seen: dict, *, final: bool = False) -> None:
    """The render cloud's own report (stage, percent, time left) as one live row of the timeline, in the step where the render happens: it
    opens on the first report, moves with the next ones and closes at the end."""
    detail = str(report.get("detail") or "").strip()
    stage = CLOUD_STAGE_FA.get(str(report.get("stage") or ""), "رندر روی سرور ابری")
    percent = report.get("progress")
    line = detail if detail.startswith("رندر ابری") else (f"{stage} · {int(percent)}٪" if isinstance(percent, (int, float)) else stage)
    if not seen.get("opened"):
        seen["opened"] = True
        _emit(loop, claims, "رندر روی سرور ابری (RunPod)", step=step, detail=line)
    if final:
        _emit(loop, claims, line or "رندر ابری تمام شد", step=step, done=True, progress=100 if not report.get("failed") else None)
    else:
        _emit(loop, claims, line, step=step, progress=int(percent) if isinstance(percent, (int, float)) else None, quiet=True)
