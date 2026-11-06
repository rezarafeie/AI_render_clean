"""Long-video content discovery: transcribe (live), understand, find every standalone piece, and open a child chat for each.

State lives in files next to the uploaded video (``<studio>/<user>/<conversation>/discovery/<analysis>/``) and a small pointer in the
conversation state; the parent chat shows the analysis and its cards, a child conversation edits one card as a normal Talking Reel.

  analysis.json   the LongVideoAnalysis record (status, progress, language, transcript/analysis versions, candidates)
  raw.json        raw Whisper transcript (timing authority)         enhanced/  per-chunk AI-corrected text (raw is never replaced)
  chunks/         per-chunk Whisper results (resume)                windows/   per-window candidate results (resume)
  outline.json    topic map of the whole video                       clips/ previews/ thumbs/   media made on demand
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

from app import lowpriority
from app.studio_store import ROOT

log = logging.getLogger(__name__)
_LOCKS: dict[str, threading.RLock] = {}
_RUNNING: dict[str, threading.Thread] = {}
_STOP: set[str] = set()
STATUSES = ("discovered", "selected", "editing", "rendering", "completed", "failed")
MIN_DISCOVERY_SECONDS = 240.0
LONG_DEFAULT_SECONDS = 480.0


def _safe(user_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", user_key)


def folder(user_key: str, conversation_id: str, analysis_id: str) -> Path:
    return ROOT / _safe(user_key) / conversation_id / "discovery" / analysis_id


def _lock(analysis_id: str) -> threading.RLock:
    return _LOCKS.setdefault(analysis_id, threading.RLock())


def load(directory: Path) -> dict:
    return json.loads((directory / "analysis.json").read_text())


def save(directory: Path, analysis: dict) -> dict:
    with _lock(analysis["id"]):
        analysis["updated_at"] = time.time()
        temporary = directory / f"analysis.{threading.get_ident()}.part"
        temporary.write_text(json.dumps(analysis, ensure_ascii=False))
        temporary.replace(directory / "analysis.json")
    return analysis


def locate(analysis_id: str, user_key: str) -> Path:
    """The folder of an analysis owned by ``user_key`` (KeyError otherwise)."""
    if not re.fullmatch(r"[a-f0-9]{12}", analysis_id):
        raise KeyError(analysis_id)
    base = ROOT / _safe(user_key)
    for path in base.glob(f"*/discovery/{analysis_id}"):
        if (path / "analysis.json").is_file():
            return path
    raise KeyError(analysis_id)


def _emit(conversation_id: str, kind: str, **data: Any) -> None:
    try:
        from app.studio_orchestrator import _emit as emit
        emit(conversation_id, kind, **data)
    except Exception:
        log.warning("discovery event %s could not be published", kind, exc_info=True)


def _assistant(conversation_id: str, user_key: str, text: str) -> None:
    try:
        from app.studio_orchestrator import _assistant as say
        say(conversation_id, user_key, text)
    except Exception:
        log.warning("discovery message could not be posted", exc_info=True)


# ── intake ──────────────────────────────────────────────────────────────────────────────────────────

def probe_media(path: Path) -> dict:
    from engine.probe import probe
    info = probe(path)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    return {"duration": round(float(info.get("format", {}).get("duration") or 0), 2), "width": video.get("width"), "height": video.get("height"),
            "has_audio": audio is not None, "size_bytes": path.stat().st_size, "audio_codec": (audio or {}).get("codec_name")}


def estimate(duration: float) -> dict:
    """What this machine will need, before it starts (shown to the user)."""
    from engine import long_transcribe as lt
    model = lt.choose_model(duration)
    seconds = lt.estimate_seconds(duration, model)
    return {"model": model, "transcription_s": round(seconds), "total_s": round(seconds * 1.5 + 120)}


def create(conversation_id: str, user_key: str, attachment: dict, request: str = "") -> dict:
    """Register the analysis for an uploaded long video (the attachment file is the shared source asset: it is never copied or re-uploaded)."""
    source = Path(attachment["path"])
    media = probe_media(source)
    analysis_id = uuid.uuid4().hex[:12]
    directory = folder(user_key, conversation_id, analysis_id)
    directory.mkdir(parents=True, exist_ok=True)
    analysis = {"id": analysis_id, "conversation_id": conversation_id, "user_key": user_key, "source_attachment_id": attachment["id"],
                "source_path": str(source), "filename": attachment["filename"], "request": request[:2000], "duration": media["duration"], "media": media,
                "language": None, "transcription_status": "queued", "discovery_status": "queued", "stage": "queued", "message": "",
                "progress": {"processed_s": 0, "duration_s": media["duration"], "percent": 0, "eta_s": None},
                "transcript_version": None, "analysis_version": 1, "estimate": estimate(media["duration"]) if media["has_audio"] else None,
                "candidates": [], "created_at": time.time(), "error": None}
    save(directory, analysis)
    return analysis


# ── the worker ──────────────────────────────────────────────────────────────────────────────────────

def _flag(directory: Path) -> Path:
    return directory / "stop.flag"


def _stopped(key: str, directory: Path) -> bool:
    """Stop was pressed: in this process (the set) or in another one (a file next to the analysis: the API process and the worker are different processes)."""
    return key in _STOP or _flag(directory).exists()


def start(directory: Path) -> None:
    analysis = load(directory)
    key = analysis["id"]
    with _lock(key):
        if key in _RUNNING and _RUNNING[key].is_alive():
            return
        _STOP.discard(key)
        _flag(directory).unlink(missing_ok=True)
        thread = threading.Thread(target=lowpriority.wrap(_guard), args=(directory,), daemon=True, name=f"discovery-{key}")
        _RUNNING[key] = thread
        thread.start()


MAX_AUTO_RESUMES = 2
FINDER_VERSION = "v2"            # raise it when the finder's prompt changes: its saved answers per window are then searched again


def recover(user_key: str, analysis_id: str) -> bool:
    """An analysis that says it is working but has been silent for a minute (its worker was restarted) continues by itself from the pieces already
    heard, at most twice; after that the person's «ادامه» button is the way."""
    try:
        directory = locate(analysis_id, user_key)
        analysis = load(directory)
    except (KeyError, OSError, ValueError):
        return False
    busy = analysis.get("transcription_status") in {"running", "queued"} or analysis.get("discovery_status") in {"running", "queued"}
    if not busy or is_alive(analysis) or _flag(directory).exists() or analysis.get("auto_resumes", 0) >= MAX_AUTO_RESUMES:       # a Stop the person pressed is never undone
        return False
    _set(directory, auto_resumes=analysis.get("auto_resumes", 0) + 1, message="پردازش بعد از قطعی دوباره شروع شد؛ از همین‌جا ادامه می‌یابد.")
    start(directory)
    return True


def stop(analysis_id: str) -> None:
    """Ask the worker to stop and say so at once. A worker that is alive notices within a few seconds (between two segments of speech); when nobody is
    working any more (a restart left the analysis marked as running) it is simply marked stopped."""
    _STOP.add(analysis_id)
    for directory in ROOT.glob(f"*/*/discovery/{analysis_id}"):
        try:
            _flag(directory).write_text(str(time.time()))
        except OSError:
            pass
        try:
            analysis = load(directory)
        except (OSError, ValueError):
            continue
        busy = analysis.get("transcription_status") in {"running", "queued"} or analysis.get("discovery_status") in {"running", "queued"}
        if not busy:
            continue
        if is_alive(analysis):
            _set(directory, stage="stopping", message="در حال توقف… چند ثانیه صبر کنید.")
        else:
            changes = {"stage": "stopped", "message": "پردازش متوقف شد؛ از همین‌جا ادامه می‌یابد."}
            for field in ("transcription_status", "discovery_status"):
                if analysis.get(field) in {"running", "queued"}:
                    changes[field] = "stopped"
            _set(directory, **changes)
            _emit(analysis["conversation_id"], "job.failed", analysis_id=analysis_id, message=changes["message"], resumable=True, stopped=True)


def is_running(analysis_id: str) -> bool:
    return analysis_id in _RUNNING and _RUNNING[analysis_id].is_alive()


def is_alive(analysis: dict) -> bool:
    """Working now, in this process or another: the worker runs in the Celery process on the server, whose threads this process cannot see, but whose
    progress it saves into the analysis file every few seconds."""
    busy = analysis.get("transcription_status") in {"running", "queued"} or analysis.get("discovery_status") in {"running", "queued"}
    last = analysis.get("updated_at", 0)
    try:
        last = max(last, (folder(analysis["user_key"], analysis["conversation_id"], analysis["id"]) / ".alive").stat().st_mtime)
    except (OSError, KeyError):
        pass
    return is_running(analysis["id"]) or (busy and time.time() - last <= 45)


def _heartbeat(directory: Path, key: str, done: threading.Event) -> None:
    """While the worker thread lives, say so every 10 s. Progress is only written when a 5-minute piece finishes, and loading the model or hearing the
    first piece of a long video takes longer than the 45 s after which the page decides that nobody is working."""
    beat = directory / ".alive"                      # its own file: the heartbeat never rewrites the analysis record, so it cannot overwrite what the worker saves
    while True:
        try:
            beat.write_text(str(time.time()))
        except OSError:
            log.debug("discovery heartbeat skipped", exc_info=True)
        if done.wait(10):
            return


def _guard(directory: Path) -> None:
    analysis = load(directory)
    finished = threading.Event()
    threading.Thread(target=_heartbeat, args=(directory, analysis["id"], finished), daemon=True, name=f"discovery-beat-{analysis['id']}").start()
    try:
        _run(directory)
    except Exception as exc:
        from engine.long_transcribe import Stopped
        analysis = load(directory)
        stopped = isinstance(exc, Stopped)
        log.exception("long-video analysis %s %s", analysis["id"], "stopped" if stopped else "failed")
        message = "پردازش متوقف شد؛ از همین‌جا ادامه می‌یابد." if stopped else str(exc)[:400] or "خطا در تحلیل ویدیو"
        analysis.update(error=None if stopped else message, stage="stopped" if stopped else "failed", message=message)
        if analysis["transcription_status"] == "running":
            analysis["transcription_status"] = "stopped" if stopped else "failed"
        if analysis["discovery_status"] == "running":
            analysis["discovery_status"] = "stopped" if stopped else "failed"
        save(directory, analysis)
        _emit(analysis["conversation_id"], "job.failed", analysis_id=analysis["id"], message=message, resumable=True, stopped=stopped)
    finally:
        finished.set()
        try:                                           # the page shows Stop from the last work.state; say that this worker is no longer working
            from app.studio_orchestrator import conversation_busy
            from app.studio_store import repo, run
            analysis = load(directory)
            _emit(analysis["conversation_id"], "work.state", busy=conversation_busy(run(repo.get_conversation(analysis["conversation_id"], analysis["user_key"])), analysis["user_key"]))
        except Exception:
            log.debug("work.state after the analysis could not be published", exc_info=True)


def _set(directory: Path, **changes: Any) -> dict:
    analysis = load(directory)
    analysis.update(changes)
    return save(directory, analysis)


def _hear_with_elevenlabs(directory: Path, source: Path, analysis: dict, on_event, enhancer) -> dict:
    """The person chose ElevenLabs: it hears the whole video (in pieces, minutes, billed by the hour of audio), and the result is shaped like local pieces."""
    from brain.transcribe import file_hash
    from brain.transcribe_elevenlabs import transcribe_elevenlabs
    from engine import long_transcribe as lt
    on_event("transcription.started", {"duration_s": analysis["duration"], "chunks": 1, "model": "elevenlabs", "resumed": False})
    transcript, cost = transcribe_elevenlabs(source, directory, language="fa", file_digest=file_hash(source))
    raw = lt.from_transcript(transcript, directory)
    enhancer.skip = True
    on_event("transcription.progress", {"processed_s": raw["duration"], "duration_s": raw["duration"], "percent": 100, "eta_s": 0, "language": raw["language"]})
    _set(directory, transcription_cost_usd=cost)
    return raw


def _run(directory: Path) -> None:
    from engine import long_transcribe as lt
    analysis = load(directory)
    conversation_id, key = analysis["conversation_id"], analysis["id"]
    source = Path(analysis["source_path"])
    if not source.is_file():
        raise RuntimeError("فایل ویدیوی اصلی پیدا نشد")
    if not analysis["media"]["has_audio"]:
        raise RuntimeError("این ویدیو صدا ندارد؛ بدون گفتار نمی‌توان محتوا را پیدا کرد.")
    stopper = lambda: _stopped(key, directory)

    # 1. live transcription; finished chunks are corrected by the model while the next one is still being heard
    enhancer = _Enhancer(directory)
    raw_path = directory / "raw.json"
    if analysis["transcription_status"] != "completed" or not raw_path.is_file():
        _set(directory, transcription_status="running", stage="transcribing", message="در حال گوش دادن به ویدیو", error=None)

        def on_event(kind: str, data: dict) -> None:
            _emit(conversation_id, kind, analysis_id=key, **data)
            if kind == "transcription.progress":
                _set(directory, progress={k: data[k] for k in ("processed_s", "duration_s", "percent", "eta_s")}, language=data.get("language"))
            if kind == "transcription.chunk.completed":
                enhancer.submit(data["index"])

        from app import transcribe_prefs
        prefs = transcribe_prefs.get(analysis.get("user_key"))
        if prefs["engine"] == "elevenlabs":
            raw = _hear_with_elevenlabs(directory, source, analysis, on_event, enhancer)
        else:
            raw = lt.transcribe_long(source, directory, model_name=prefs["whisper_model"] or None, on_event=on_event, should_stop=stopper)
        version = raw["version"]
        _set(directory, transcription_status="completed", language=raw["language"], transcript_version=version,
             progress={"processed_s": raw["duration"], "duration_s": raw["duration"], "percent": 100, "eta_s": 0})
    else:
        raw = json.loads(raw_path.read_text())
        enhancer.skip = raw.get("model") == "elevenlabs"
        for index in range(len(list((directory / "chunks").glob("*.json")))):
            enhancer.submit(index)

    # 2. wait for the corrected text, then keep both versions side by side
    _set(directory, stage="enhancing", message="در حال اصلاح و بهبود متن")
    enhancer.finish(stopper)
    segments = enhancer.assemble(raw)
    (directory / "transcript.json").write_text(json.dumps({"version": raw["version"], "language": raw["language"], "segments": segments}, ensure_ascii=False))
    _emit(conversation_id, "transcription.enhancement.completed", analysis_id=key, changed=sum(1 for s in segments if s.get("changed")), segments=len(segments))
    if stopper():
        raise lt.Stopped("stopped")
    if not segments:
        raise RuntimeError("در این ویدیو گفتاری شناسایی نشد.")

    # 3. discovery
    _discover(directory, segments, stopper)


class _Enhancer:
    """Corrects each finished chunk in a background thread (the LLM is waiting time, not CPU) and caches the result per chunk."""

    def __init__(self, directory: Path):
        import queue
        self.directory, self.queue, self.done, self.errors = directory, queue.Queue(), set(), []
        (directory / "enhanced").mkdir(exist_ok=True)
        self.started = time.monotonic()
        self.budget = max(240.0, 0.6 * load(directory)["duration"])        # the correction never holds up discovery for longer than this
        self.thread = threading.Thread(target=self._work, daemon=True, name="discovery-enhance")
        self.thread.start()
        self.seen: set[int] = set()
        self.skip = False                  # ElevenLabs' text is already accurate: a model rereading all of it only costs minutes

    def deadline(self) -> float:
        return self.started + self.budget

    def submit(self, index: int) -> None:
        if not self.skip and index not in self.seen:
            self.seen.add(index)
            self.queue.put(index)

    def _work(self) -> None:
        from creative import discovery
        while True:
            index = self.queue.get()
            if index is None:
                return
            path = self.directory / "enhanced" / f"{index:04d}.json"
            try:
                if not path.is_file():
                    chunk = json.loads((self.directory / "chunks" / f"{index:04d}.json").read_text())
                    context = self._tail(index)
                    enhanced = discovery.enhance_segments(chunk["segments"], context, deadline=self.deadline())
                    path.write_text(json.dumps(enhanced, ensure_ascii=False))
                self.done.add(index)
                total = len(list((self.directory / "chunks").glob("*.json")))
                _set(self.directory, message=f"در حال اصلاح و بهبود متن ({len(self.done)} از {total})")
            except Exception as exc:
                log.warning("enhancement of chunk %s failed: %s", index, exc)
                self.errors.append(index)

    def _tail(self, index: int) -> list[dict]:
        previous = self.directory / "enhanced" / f"{index - 1:04d}.json"
        return json.loads(previous.read_text())[-3:] if index and previous.is_file() else []

    def finish(self, stopper) -> None:
        self.queue.put(None)
        while self.thread.is_alive():
            self.thread.join(timeout=1.0)
            if stopper():
                raise_stopped()

    def assemble(self, raw: dict) -> list[dict]:
        """All segments in time order, raw text untouched. Segments the model could not correct the first time are tried again once."""
        from creative import discovery
        merged = []
        chunks = sorted((self.directory / "chunks").glob("*.json"))
        for position, chunk_path in enumerate(chunks):
            enhanced_path = self.directory / "enhanced" / f"{position:04d}.json"
            if enhanced_path.is_file():
                items = json.loads(enhanced_path.read_text())
                missing = [i for i, s in enumerate(items) if "not_enhanced" in s.get("flags", [])]
                if missing:                                   # a provider error the first time is not a reason to ship uncorrected text
                    retried = discovery.enhance_segments([{k: v for k, v in items[i].items() if k not in {"enhanced_text", "flags", "uncertain", "changed"}} for i in missing],
                                                         items[:1] if not missing[0] else [items[missing[0] - 1]], deadline=self.deadline() + 120)
                    for i, fixed in zip(missing, retried):
                        items[i] = fixed
                    enhanced_path.write_text(json.dumps(items, ensure_ascii=False))
                merged.extend(items)
            elif self.skip:
                merged.extend({**seg, "enhanced_text": seg["text"], "flags": [], "uncertain": [], "changed": False} for seg in json.loads(chunk_path.read_text())["segments"])
            else:
                merged.extend(discovery.enhance_segments(json.loads(chunk_path.read_text())["segments"]))
        merged.sort(key=lambda s: s["start"])
        return merged


def raise_stopped():
    from engine.long_transcribe import Stopped
    raise Stopped("stopped")


def _discover(directory: Path, segments: list[dict], stopper, focus: str = "") -> None:
    from creative import discovery
    from engine import long_transcribe as lt
    analysis = load(directory)
    conversation_id, key = analysis["conversation_id"], analysis["id"]
    _set(directory, discovery_status="running", stage="understanding", message="در حال فهمیدن ساختار کل ویدیو")
    _emit(conversation_id, "content.discovery.started", analysis_id=key, segments=len(segments))
    index = {s["id"]: i for i, s in enumerate(segments)}

    outline_path = directory / "outline.json"
    if outline_path.is_file():
        outline = discovery.Outline.model_validate_json(outline_path.read_text())
    else:
        outline = discovery.build_outline(segments, on_progress=lambda n: _set(directory, message=f"ساختار موضوعی ویدیو: بخش {n}"))
        outline_path.write_text(outline.model_dump_json())
    _emit(conversation_id, "content.outline.completed", analysis_id=key, topics=[{"title": t.title, "start": t.start, "end": t.end} for t in outline.topics][:60])

    (directory / "windows").mkdir(exist_ok=True)
    tag = FINDER_VERSION + ("-more-" + re.sub(r"\W+", "", focus)[:12] if focus else "-w")          # answers of an older prompt are not reused
    accepted = list(analysis["candidates"])
    before = len(accepted)
    wins = discovery.windows(segments)
    for number, window in enumerate(wins):
        if stopper():
            raise lt.Stopped("stopped")
        _set(directory, stage="finding", message=f"جست‌وجوی محتوای مستقل: بخش {number + 1} از {len(wins)}")
        cache = directory / "windows" / f"{tag}-{number:03d}.json"
        if cache.is_file():
            raws = [discovery.RawCandidate.model_validate(r) for r in json.loads(cache.read_text())]
        else:
            try:
                raws = discovery.find_in_window(window, index, outline, focus=focus) if focus else discovery.find_in_window(window, index, outline)
            except Exception as exc:
                log.warning("candidate search failed on window %s: %s", number, exc)
                raws = []
            cache.write_text(json.dumps([r.model_dump(by_alias=False) for r in raws], ensure_ascii=False, default=str))
        fresh = _prepare(raws, segments, index, key)
        if not fresh:
            continue
        _set(directory, stage="validating", message=f"بازبینی {len(fresh)} پیشنهاد با دید کل ویدیو")
        for cand in _validated(fresh, segments, outline):
            if any(discovery.same_content(cand, other) for other in accepted):
                continue
            accepted.append(cand)
            accepted.sort(key=lambda c: c["ranges"][0][0])
            analysis = load(directory)
            analysis["candidates"] = accepted
            save(directory, analysis)
            _emit(conversation_id, "content.candidate.found", analysis_id=key, candidate=public_candidate(cand))
            prepare_media_in_background(directory, cand, Path(analysis["source_path"]))
    analysis = load(directory)
    analysis.update(discovery_status="completed", stage="done", message=f"{len(accepted)} محتوای مستقل پیدا شد", candidates=accepted)
    save(directory, analysis)
    _emit(conversation_id, "content.discovery.completed", analysis_id=key, count=len(accepted))
    new = len(accepted) - before
    if focus and before:
        _assistant(conversation_id, analysis["user_key"], (f"{new} محتوای تازه پیدا شد و به کارت‌ها اضافه شد؛ در مجموع {len(accepted)} کارت دارید." if new
                                                           else "محتوای تازه‌ای که قبلاً پیشنهاد نشده باشد پیدا نشد."))
    else:
        _assistant(conversation_id, analysis["user_key"], _completion_message(analysis))


def _prepare(raws, segments: list[dict], index: dict[str, int], analysis_id: str) -> list[dict]:
    from creative import discovery
    out = []
    for raw in raws:
        spans = []
        for span in raw.ranges:
            a, b = sorted((min(span.start_seg, len(segments) - 1), min(span.end_seg, len(segments) - 1)))
            spans.append((discovery.trim_filler(a, b, segments), b))
        if not spans:
            continue
        times = [discovery.snap_range(a, b, segments) for a, b in spans]
        seconds = discovery.total_seconds(times)
        if not discovery.MIN_CLIP_S * 0.8 <= seconds <= discovery.MAX_CLIP_S * 1.2:
            continue
        out.append({"id": discovery.candidate_id(analysis_id, times[0][0]), "title": raw.title, "summary": raw.summary, "hook": raw.hook,
                    "hook_source": raw.hook_source, "category": raw.category, "rationale": raw.rationale, "scores": raw.scores,
                    "seg_ranges": [list(s) for s in spans], "seg_from": spans[0][0], "seg_to": spans[-1][1], "ranges": [list(t) for t in times],
                    "estimated_duration": seconds, "needs_context": raw.needs_context, "raw": raw})
    return out


def _validated(prepared: list[dict], segments: list[dict], outline) -> list[dict]:
    from creative import discovery
    verdicts = discovery.validate_candidates(prepared, segments, outline)
    result = []
    for cand, verdict in zip(prepared, verdicts):
        if not verdict.keep or (verdict.standalone and verdict.standalone < 5.5):
            continue
        spans = [tuple(s) for s in cand["seg_ranges"]]
        if verdict.trim_from is not None and spans[0][0] <= verdict.trim_from <= spans[0][1]:
            spans[0] = (verdict.trim_from, spans[0][1])
        if verdict.trim_to is not None and spans[-1][0] <= verdict.trim_to <= spans[-1][1]:
            spans[-1] = (spans[-1][0], verdict.trim_to)
        if verdict.context_from is not None and 0 <= verdict.context_from < spans[0][0] and segments[spans[0][0]]["start"] - segments[verdict.context_from]["start"] < 40:
            spans[0] = (verdict.context_from, spans[0][1])          # one earlier sentence makes the clip understandable
        times = [discovery.snap_range(a, b, segments) for a, b in spans]
        seconds = discovery.total_seconds(times)
        if not discovery.MIN_CLIP_S <= seconds <= discovery.MAX_CLIP_S * 1.2:
            continue
        raw = cand.pop("raw")
        result.append({**cand, "title": verdict.title or cand["title"], "hook": verdict.hook or cand["hook"], "summary": verdict.summary or cand["summary"],
                       "category": verdict.category if verdict.category in discovery.CATEGORIES else cand["category"],
                       "seg_ranges": [list(s) for s in spans], "ranges": [list(t) for t in times], "estimated_duration": seconds,
                       "rationale": verdict.reason or cand["rationale"], "standalone": verdict.standalone, "problems": verdict.problems,
                       "score": discovery.score_of(raw, verdict), "status": "discovered", "hidden": False, "child_conversation_id": None,
                       "child_project_id": None, "revisions": [], "created_at": time.time()})
    return result


def public_candidate(cand: dict) -> dict:
    return {k: v for k, v in cand.items() if k not in {"raw", "seg_from", "seg_to"}}


def _completion_message(analysis: dict) -> str:
    cands = [c for c in analysis["candidates"] if not c.get("hidden")]
    if not cands:
        return ("کل ویدیو را شنیدم و بررسی کردم، اما بخشی که به‌تنهایی ارزش انتشار داشته باشد پیدا نکردم. "
                "برای پیدا کردن چیز دیگری می‌توانید بگویید دنبال چه نوع محتوایی بگردم.")
    total = sum(c["estimated_duration"] for c in cands)
    best = sorted(cands, key=lambda c: -c["score"])[:3]
    lines = "\n".join(f"- «{c['title']}» ({c['score']:g}/10)" for c in best)
    return (f"**{len(cands)} محتوای مستقل** از این ویدیوی {round(analysis['duration'] / 60):g} دقیقه‌ای پیدا شد (روی هم حدود {round(total / 60, 1):g} دقیقه).\n\n"
            f"بهترین‌ها:\n{lines}\n\n"
            "هر کارت را پیش‌نمایش کنید و با «شروع تدوین» در یک چت جدا بسازید. اگر نوع دیگری از محتوا می‌خواهید، پایین کارت‌ها بنویسید دنبال چه بگردم.")


# ── thumbnails / previews (made on demand from the original file; never re-encoded up front) ─────────────

def _ffmpeg(args: list[str], timeout: int = 600, *, nice: bool = False) -> None:
    """``nice`` makes the encode yield to everything else on the machine (previews are made in the background); the timeout is long because a busy server is slow, not stuck."""
    subprocess.run([*(["nice", "-n", "10"] if nice else []), "ffmpeg", "-v", "error", "-y", *args], check=True, capture_output=True, timeout=timeout)


def thumbnail(directory: Path, cand: dict, source: Path) -> Path:
    target = directory / "thumbs" / f"{cand['id']}.jpg"
    if not target.is_file():
        target.parent.mkdir(exist_ok=True)
        at = cand["ranges"][0][0] + min(1.5, (cand["ranges"][0][1] - cand["ranges"][0][0]) / 3)
        _ffmpeg(["-ss", f"{at:.2f}", "-i", str(source), "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", str(target)], 120)
    return target


def render_clip(source: Path, ranges: list[list[float]], target: Path, *, small: bool) -> Path:
    """The clip for the given source ranges (several ranges are joined). ``small`` makes a light 360p preview."""
    target.parent.mkdir(parents=True, exist_ok=True)
    scale = ["-vf", "scale=-2:360"] if small else []
    quality = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "32", "-r", "24", "-threads", "2", "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart"] if small
               else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", "3", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"])
    run_ffmpeg = lambda args: _ffmpeg(args, 1800 if small else 3600, nice=small)
    temporary = target.with_suffix(".part.mp4")
    if len(ranges) == 1:
        a, b = ranges[0]
        run_ffmpeg(["-ss", f"{a:.3f}", "-i", str(source), "-t", f"{b - a:.3f}", *scale, *quality, str(temporary)])
    else:
        inputs, parts = [], []
        for i, (a, b) in enumerate(ranges):
            inputs += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(source)]
            video = f"[{i}:v]setpts=PTS-STARTPTS" + (",scale=-2:360" if small else "") + f"[v{i}]"
            parts.append(video + f";[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
        joined = "".join(f"[v{i}][a{i}]" for i in range(len(ranges)))
        run_ffmpeg([*inputs, "-filter_complex", ";".join(parts) + f";{joined}concat=n={len(ranges)}:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]", *quality, str(temporary)])
    temporary.replace(target)
    return target


_MAKING: dict[str, threading.Lock] = {}


def _preview_target(directory: Path, cand: dict) -> Path:
    import hashlib
    digest = hashlib.sha1(json.dumps(cand["ranges"]).encode()).hexdigest()[:8]            # stable: Python's hash() changes with every restart, which made every preview start over
    return directory / "previews" / f"{cand['id']}-{digest}.mp4"


def preview(directory: Path, cand: dict, source: Path) -> Path:
    target = _preview_target(directory, cand)
    if target.is_file():
        return target
    with _MAKING.setdefault(str(target), threading.Lock()):         # a preview being prepared in the background is waited for, not started a second time
        if not target.is_file():
            for old in (directory / "previews").glob(f"{cand['id']}-*.mp4") if (directory / "previews").is_dir() else []:
                old.unlink(missing_ok=True)
            render_clip(source, cand["ranges"], target, small=True)
    return target


def prepare_media_in_background(directory: Path, cand: dict, source: Path) -> None:
    """Make the thumbnail and the light preview of a card as soon as it is found, one card at a time and at low priority, so that pressing play finds them ready
    (on a busy server the first request used to wait minutes for an encode)."""
    def work() -> None:
        with _PREPARE:
            try:
                os.nice(10)
            except (AttributeError, OSError):
                pass
            for step in (lambda: thumbnail(directory, cand, source), lambda: preview(directory, cand, source)):
                try:
                    started = time.monotonic()
                    step()
                    log.info("card media for %s ready in %.0f s", cand.get("id"), time.monotonic() - started)
                except Exception:
                    log.warning("card media could not be prepared for %s", cand.get("id"), exc_info=True)
    threading.Thread(target=work, daemon=True, name=f"discovery-media-{cand.get('id')}").start()


_PREPARE = threading.Semaphore(1)


# ── editing a card, child chats, status ─────────────────────────────────────────────────────────────

def edit_candidate(directory: Path, candidate_id: str, changes: dict) -> dict:
    """Change title/hook/summary/category, trim a range, or hide the card. Every change is kept as a numbered revision."""
    analysis = load(directory)
    cand = next((c for c in analysis["candidates"] if c["id"] == candidate_id), None)
    if cand is None:
        raise KeyError(candidate_id)
    before = {k: cand.get(k) for k in ("title", "hook", "summary", "category", "ranges", "hidden")}
    for key in ("title", "hook", "summary", "category"):
        if key in changes and isinstance(changes[key], str) and changes[key].strip():
            cand[key] = " ".join(changes[key].split())[:500]
    if "hidden" in changes:
        cand["hidden"] = bool(changes["hidden"])
    if "ranges" in changes:
        duration = analysis["duration"]
        ranges = []
        for pair in changes["ranges"]:
            a, b = float(pair[0]), float(pair[1])
            if not 0 <= a < b <= duration + 0.5 or b - a < 2:
                raise ValueError("بازهٔ زمانی معتبر نیست.")
            ranges.append([round(a, 2), round(b, 2)])
        if not ranges or sum(b - a for a, b in ranges) > 300:
            raise ValueError("کلیپ باید بین چند ثانیه تا ۵ دقیقه باشد.")
        cand["ranges"], cand["estimated_duration"] = ranges, round(sum(b - a for a, b in ranges), 2)
        # a new time range means a new preview and thumbnail
        for sub in ("previews", "thumbs"):
            for old in (directory / sub).glob(f"{candidate_id}*") if (directory / sub).is_dir() else []:
                old.unlink(missing_ok=True)
    if cand.get("child_conversation_id") and any(k in changes for k in ("ranges", "title", "hook")):
        cand["child_stale"] = True          # the editing chat was made from the earlier version
    after = {k: cand.get(k) for k in before}
    if after != before:
        cand["revisions"].append({"revision": len(cand["revisions"]) + 1, "changes": {k: [before[k], after[k]] for k in before if before[k] != after[k]}, "created_at": time.time()})
    save(directory, analysis)
    return public_candidate(cand)


def _ordinal(text: str) -> Optional[int]:
    words = {"اول": 1, "یکم": 1, "دوم": 2, "سوم": 3, "چهارم": 4, "پنجم": 5, "ششم": 6, "هفتم": 7, "هشتم": 8, "نهم": 9, "دهم": 10,
             "یازدهم": 11, "دوازدهم": 12}
    clean = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    for word, number in words.items():
        if re.search(rf"(?<!\w){word}(?!\w)", clean):
            return number
    match = re.search(r"(?:کلیپ|کارت|ریلز|محتوا|مورد|شماره)\s*(\d{1,3})|(\d{1,3})\s*(?:ام|م)\b", clean)
    return int(match.group(1) or match.group(2)) if match else None


def parse_chat_command(text: str) -> Optional[dict]:
    """"کلیپ سوم را تدوین کن" / "کلیپ پنجم را مثل کلیپ دوم تدوین کن" -> {"index": 3, "like": 2}."""
    if not re.search(r"(کلیپ|کارت|ریلز|محتوا|مورد)", text) or not re.search(r"(تدوین|شروع|بساز|درست کن|ادیت)", text):
        return None
    like = re.search(r"مثل\s+(?:کلیپ|کارت|ریلز|محتوا|مورد)?\s*(\S+)", text)
    like_n = _ordinal(like.group(0)) if like else None
    head = text[:like.start()] if like else text
    index = _ordinal(head)
    return {"index": index, "like": like_n} if index else None


def sorted_visible(analysis: dict) -> list[dict]:
    return [c for c in analysis["candidates"] if not c.get("hidden")]


# ── child chat per candidate ────────────────────────────────────────────────────────────────────────

def child_request(analysis: dict, cand: dict, like: Optional[dict] = None) -> str:
    from creative.discovery import clock
    parts = [f"تدوین ریلز اینستاگرام (صحبتی) از یک بخش ویدیوی بلند «{analysis['filename']}».",
             f"عنوان محتوا: {cand['title']}", f"خلاصه: {cand['summary']}", f"هوک پیشنهادی: {cand['hook']}",
             f"دسته: {cand['category']} · مدت حدود {round(cand['estimated_duration'])} ثانیه · بازه‌های منبع: "
             + "، ".join(f"{clock(a)}–{clock(b)}" for a, b in cand["ranges"])]
    if like:
        parts.append(f"سبک تدوین را مثل کلیپ «{like['title']}» انتخاب کن" + (f" (سبک {like['style']})." if like.get("style") else "."))
    return "\n".join(parts)


def seed_transcript(analysis: dict, directory: Path, cand: dict) -> dict:
    """The part of the parent transcript that the clip contains, re-timed to the clip. The child never transcribes the audio again."""
    transcript = json.loads((directory / "transcript.json").read_text())
    words, sentences, offset = [], [], 0.0
    for a, b in cand["ranges"]:
        for seg in transcript["segments"]:
            if seg["end"] <= a or seg["start"] >= b:
                continue
            kept = [w for w in seg["words"] if a - 0.01 <= w["start"] and w["end"] <= b + 0.01]
            if not kept:
                continue
            shifted = [{"w": w["w"], "start": round(w["start"] - a + offset, 3), "end": round(w["end"] - a + offset, 3), "prob": w.get("prob", 0.9)} for w in kept]
            words.extend(shifted)
            sentences.append({"text": seg.get("enhanced_text") or seg["text"], "start": shifted[0]["start"], "end": shifted[-1]["end"]})
        offset += b - a
    return {"engine": "whisper", "requested_language": "fa", "language": analysis.get("language") or "fa", "duration": round(offset, 3),
            "words": words, "sentences": sentences, "source": "long-video-discovery", "transcript_version": analysis.get("transcript_version")}


_PREPARING: set[str] = set()


def start_candidate(directory: Path, candidate_id: str, *, like_candidate: Optional[str] = None) -> dict:
    """Open (or re-open) the editing chat of a card. The same card never makes a second project. The chat opens at once; the clip is cut from the long video in the
    background (minutes on a busy server) and the edit starts by itself when it is ready."""
    from app.studio_store import repo, run
    analysis = load(directory)
    cand = next((c for c in analysis["candidates"] if c["id"] == candidate_id), None)
    if cand is None:
        raise KeyError(candidate_id)
    user_key = analysis["user_key"]
    with _lock(analysis["id"] + ":start"):
        analysis = load(directory)
        cand = next(c for c in analysis["candidates"] if c["id"] == candidate_id)
        key = f"{analysis['id']}:{candidate_id}"
        if cand.get("child_conversation_id") and not cand.get("child_stale"):
            if cand.get("child_preparing") and key not in _PREPARING and time.time() - cand.get("selected_at", 0) > 90:
                cand["child_conversation_id"], cand["child_preparing"] = None, False             # the worker that was cutting it is gone: cut again
            else:
                try:
                    run(repo.get_conversation(cand["child_conversation_id"], user_key))
                    return {"conversation_id": cand["child_conversation_id"], "created": False}
                except KeyError:
                    cand["child_conversation_id"] = None
        conversation = run(repo.create_conversation(user_key, cand["title"][:80]))
        child_id = conversation["id"]
        state = {"parent": {"conversation_id": analysis["conversation_id"], "analysis_id": analysis["id"], "candidate_id": cand["id"]},
                 "forced_intent": "talking", "candidate": public_candidate(cand)}
        run(repo.set_conversation(child_id, user_key, state=state))
        cand.update(status="selected", child_conversation_id=child_id, child_stale=False, child_preparing=True, selected_at=time.time())
        save(directory, analysis)
        _emit(analysis["conversation_id"], "content.candidate.updated", analysis_id=analysis["id"], candidate=public_candidate(cand))
        _PREPARING.add(key)
    from app.studio_orchestrator import _assistant as say
    say(child_id, user_key, "دارم این بخش را از ویدیوی بلند جدا می‌کنم. روی سرور شلوغ ممکن است چند دقیقه طول بکشد؛ وقتی آماده شد، تدوین خودکار شروع می‌شود و لازم نیست چیزی بفرستید.")
    threading.Thread(target=_prepare_child, args=(directory, candidate_id, child_id, like_candidate), daemon=True, name=f"discovery-clip-{candidate_id}").start()
    return {"conversation_id": child_id, "created": True}


def _prepare_child(directory: Path, candidate_id: str, child_id: str, like_candidate: Optional[str]) -> None:
    """Cut the clip, give it to the editing chat as its video and start the edit; on any failure say so in that chat and free the card to be tried again."""
    from app.studio_orchestrator import _assistant as say, dispatch_message
    from app.studio_store import repo, run
    analysis = load(directory)
    user_key = analysis["user_key"]
    key = f"{analysis['id']}:{candidate_id}"
    try:
        cand = next(c for c in analysis["candidates"] if c["id"] == candidate_id)
        clip = render_clip(Path(analysis["source_path"]), cand["ranges"], directory / "clips" / f"{cand['id']}-{int(time.time())}.mp4", small=False)
        attachment_path = ROOT / _safe(user_key) / child_id / "attachments"
        attachment_path.mkdir(parents=True, exist_ok=True)
        placed = attachment_path / f"{cand['id']}.mp4"
        shutil.copy2(clip, placed)
        attachment = run(repo.create_attachment(child_id, user_key, kind="video", filename=f"{cand['title'][:60]}.mp4", path=str(placed),
                                                mime_type="video/mp4", size_bytes=placed.stat().st_size, metadata={"from_discovery": analysis["id"]}))
        seed_path = attachment_path.parent / "seed_transcript.json"
        seed_path.write_text(json.dumps(seed_transcript(analysis, directory, cand), ensure_ascii=False))
        like = None
        if like_candidate:
            other = next((c for c in analysis["candidates"] if c["id"] == like_candidate), None)
            if other:
                like = {"title": other["title"], "style": (other.get("child_style") or "")}
        child = run(repo.get_conversation(child_id, user_key))
        run(repo.set_conversation(child_id, user_key, state={**(child.get("state") or {}), "seed_transcript_path": str(seed_path)}))
        text = child_request(analysis, cand, like)
        message = run(repo.add_message(child_id, user_key, "user", text, [attachment["id"]]))
        with _lock(analysis["id"] + ":start"):
            fresh = load(directory)
            for c in fresh["candidates"]:
                if c["id"] == candidate_id:
                    c["child_preparing"] = False
            save(directory, fresh)
        dispatch_message(child_id, user_key, message["id"], text, [attachment["id"]])
    except Exception as exc:
        log.exception("clip for %s could not be prepared", candidate_id)
        try:
            say(child_id, user_key, f"جدا کردن این بخش از ویدیوی بلند انجام نشد ({str(exc)[:120] or type(exc).__name__}). به کارت برگردید و «شروع تدوین» را دوباره بزنید.")
            with _lock(analysis["id"] + ":start"):
                fresh = load(directory)
                for c in fresh["candidates"]:
                    if c["id"] == candidate_id:
                        c.update(child_conversation_id=None, child_preparing=False, status="discovered")
                save(directory, fresh)
        except Exception:
            log.exception("the failure of %s could not be recorded", candidate_id)
    finally:
        _PREPARING.discard(key)


def _child_status(user_key: str, cand: dict) -> tuple[str, Optional[dict]]:
    from app.studio_store import repo, run
    try:
        child = run(repo.get_conversation(cand["child_conversation_id"], user_key))
    except KeyError:
        return "selected", None
    project_id = (child.get("state") or {}).get("current_project_id")
    project = next((p for p in child.get("projects", []) if p["id"] == project_id), None) if project_id else None
    if project is None:
        return "selected", None
    state, status = project.get("state") or {}, project.get("status")
    workflow = state.get("workflow")
    info = {"project_id": project["id"], "status": status, "workflow": workflow, "style": state.get("selected_style")}
    if status in {"error", "failed"}:
        return "failed", info
    if status in {"done", "ready"} or workflow == "completed":
        return "completed", info
    if workflow in {"production", "rendering"} or (status == "running" and (state.get("last_observed") or {}).get("status") in {"rendering"}):
        return "rendering", info
    return "editing", info


def refresh_statuses(directory: Path) -> dict:
    """Card statuses follow their child chats; cards without a child, and every other card, are left as they are."""
    analysis = load(directory)
    changed = False
    for cand in analysis["candidates"]:
        if not cand.get("child_conversation_id"):
            continue
        status, info = _child_status(analysis["user_key"], cand)
        if info:
            cand["child_project_id"], cand["child_style"] = info["project_id"], info.get("style")
        if status != cand["status"]:
            cand["status"], changed = status, True
            _emit(analysis["conversation_id"], "content.candidate.updated", analysis_id=analysis["id"], candidate=public_candidate(cand))
    if changed:
        save(directory, analysis)
    return analysis


def view(directory: Path, tail: int = 12) -> dict:
    """What the chat panel shows: progress, the newest transcript lines and every card."""
    analysis = refresh_statuses(directory)
    if is_stale(analysis):
        analysis["stage"], analysis["message"] = "interrupted", "پردازش قطع شده؛ از همین‌جا ادامه می‌یابد."
    segments = []
    enhanced = sorted((directory / "enhanced").glob("*.json")) if (directory / "enhanced").is_dir() else []
    chunks = sorted((directory / "chunks").glob("*.json"))
    if chunks:
        try:
            last = json.loads(chunks[-1].read_text())["segments"][-tail:]
            segments = [{"id": s["id"], "start": s["start"], "end": s["end"], "text": s["text"]} for s in last]
        except (OSError, ValueError):
            pass
    out = {k: v for k, v in analysis.items() if k not in {"candidates", "source_path", "user_key"}}
    ensure_media(directory, analysis)
    out.update(running=is_alive(analysis), interrupted=is_stale(analysis), transcript_tail=segments, enhanced_chunks=len(enhanced), chunks=len(chunks),
               candidates=[{**public_candidate(c), "preview_ready": _preview_target(directory, c).is_file()} for c in analysis["candidates"]])
    return out


_QUEUED: set[str] = set()


def ensure_media(directory: Path, analysis: dict) -> None:
    """Cards found before previews were prepared in the background (or whose range was edited) get theirs made now, once, one at a time."""
    source = Path(analysis.get("source_path", ""))
    if not source.is_file():
        return
    for cand in analysis.get("candidates", []):
        target = _preview_target(directory, cand)
        if cand.get("hidden") or target.is_file() or str(target) in _QUEUED:
            continue
        _QUEUED.add(str(target))
        prepare_media_in_background(directory, cand, source)


def is_stale(analysis: dict) -> bool:
    busy = analysis["transcription_status"] in {"running", "queued"} or analysis["discovery_status"] in {"running", "queued"}
    return busy and not is_alive(analysis) and analysis.get("stage") not in {"queued"} and time.time() - analysis.get("updated_at", 0) > 20


def request_more(directory: Path, focus: str) -> None:
    """Look again for something specific ("only the motivational parts", "stories")."""
    analysis = load(directory)
    if analysis["transcription_status"] != "completed":
        raise ValueError("تا پایان گوش دادن به ویدیو صبر کنید.")
    segments = json.loads((directory / "transcript.json").read_text())["segments"]
    key = analysis["id"]
    _STOP.discard(key)
    _flag(directory).unlink(missing_ok=True)
    def work():
        try:
            _discover(directory, segments, lambda: _stopped(key, directory), focus=focus[:300])
        except Exception as exc:
            log.exception("additional discovery failed")
            _emit(analysis["conversation_id"], "job.failed", analysis_id=key, message=str(exc)[:300], resumable=True)
    thread = threading.Thread(target=work, daemon=True, name=f"discovery-more-{key}")
    _RUNNING[key] = thread
    thread.start()


def recover_interrupted() -> int:
    """After a restart: pick up analyses that were running and continue them where they stopped."""
    count = 0
    for path in ROOT.glob("*/*/discovery/*/analysis.json"):
        try:
            analysis = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        busy = analysis["transcription_status"] == "running" or analysis["discovery_status"] == "running"
        if busy and not is_alive(analysis):                       # a worker in another process that saved progress a moment ago is not "interrupted"
            start(path.parent)
            count += 1
    return count
