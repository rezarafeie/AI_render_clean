"""Visual editor entry points. All media, plans and render jobs belong to Studio."""
import asyncio
import fcntl
from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.routers import studio


router = APIRouter(prefix="/panel", tags=["manual-editor"])
repo = studio.repo
Modes = Literal["manual", "assisted", "auto"]
Engines = Literal["talking", "localize", "motion", "vox", "story", "product", "clips"]


class ProjectSetup(BaseModel):
    title: str = Field(default="پروژهٔ جدید", max_length=100)
    engine: Engines = "talking"
    mode: Modes = "manual"
    style: str = Field(default="", max_length=50)
    topic: str = Field(default="", max_length=1000)
    seconds: Literal[15, 30, 45, 60] = 30
    aspect: Literal["source", "vertical", "square", "landscape"] = "source"
    source_url: str = Field(default="", max_length=2000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=16)


@contextmanager
def _lock(user: str, conversation: str):
    from app.studio_flags import conversation_dir

    directory = conversation_dir(user, conversation)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".manual-editor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HTTPException(409, "تغییر دیگری در حال ثبت است. دوباره امتحان کنید.") from exc
        yield


async def _owned(request: Request, conversation: str):
    user = studio._user(request)
    try:
        return user, await repo.get_conversation(conversation, user, message_limit=1)
    except KeyError as exc:
        raise HTTPException(404, "پروژه پیدا نشد.") from exc


def _motion_enabled():
    from creative import claude_motion
    return claude_motion.enabled()


@router.get("/capabilities")
async def capabilities():
    from engine.talking_reel import style_list
    return {"talking_styles": style_list(), "claude_motion": _motion_enabled()}


@router.post("/draft", status_code=201)
async def draft(request: Request):
    chat = await studio.create_conversation(request, studio.ConversationCreate(title="پروژهٔ دستی جدید"))
    state = {**chat["state"], "panel": {"setup": ProjectSetup().model_dump()}}
    return studio._public_conversation(await repo.set_conversation(chat["id"], studio._user(request), state=state))


@router.put("/{conversation}/setup")
async def save_setup(request: Request, conversation: str, setup: ProjectSetup):
    user, chat = await _owned(request, conversation)
    with _lock(user, conversation):
        _, chat = await _owned(request, conversation)
        panel = chat["state"].get("panel")
        if panel is None or chat["projects"] or chat["state"].get("motion"):
            raise HTTPException(409, "پیکربندی منبع فقط برای پیش‌نویس جدید قابل تغییر است.")
        try:
            await repo.get_attachments(setup.attachment_ids, conversation, user)
        except KeyError as exc:
            raise HTTPException(404, "یکی از فایل‌ها در همین پروژه پیدا نشد.") from exc
        state = {**chat["state"], "panel": {**panel, "setup": setup.model_dump()}}
        return studio._public_conversation(await repo.set_conversation(
            conversation, user, state=state, title=setup.title.strip() or "پروژهٔ دستی جدید"))


@router.get("/{conversation}/media")
async def draft_media(request: Request, conversation: str):
    user, chat = await _owned(request, conversation)
    ids = ((chat["state"].get("panel") or {}).get("setup") or {}).get("attachment_ids") or []
    try:
        attachments = await repo.get_attachments(ids, conversation, user)
    except KeyError as exc:
        raise HTTPException(409, "یک فایل انتخاب‌شده دیگر در دسترس نیست.") from exc
    return [{key: item[key] for key in ("id", "filename", "kind", "mime_type", "size_bytes")} for item in attachments]


class MotionAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


@router.post("/{conversation}/motion/answer")
async def answer_motion(request: Request, conversation: str, body: MotionAnswer):
    from app import credits, motion_graphic
    user, _ = await _owned(request, conversation)
    with _lock(user, conversation):
        _, chat = await _owned(request, conversation)
        motion_id = (chat["state"].get("motion") or {}).get("motion_id")
        if not motion_id:
            raise HTTPException(404, "موشن پروژه پیدا نشد.")
        directory = studio._motion_dir(request, motion_id)
        record = await asyncio.to_thread(motion_graphic.load, directory)
        if record["status"] != "needs_input":
            raise HTTPException(409, "موتور دیگر منتظر پاسخ نیست.")
        if not body.answer.strip():
            raise HTTPException(422, "پاسخ را وارد کنید.")
        await credits.gate(user)
        await asyncio.to_thread(motion_graphic.answer, directory, body.answer)
    return {"ok": True}


_MOTION_BRIEFS = {
    "motion": "یک موشن‌گرافیک توضیحی بساز.",
    "vox": "یک ویدیوی توضیحی مستند به سبک ووکس بساز.",
    "story": "ویدیوی معرفی به سبک قصه بساز.",
    "product": "ویدیوی معرفی محصول به شکل شوریل بساز.",
}


def _create_clip_job(user: str, source: dict, aspect: str):
    """Seed a plain native EditPlan from a validated Studio source."""
    from fractions import Fraction
    from pathlib import Path

    from app import jobs
    from engine.probe import probe

    path = Path(source["path"])
    metadata = probe(path)
    stream = next((row for row in metadata.get("streams", []) if row.get("codec_type") == "video"), None)
    duration = float(metadata.get("format", {}).get("duration") or 0)
    if not stream or duration <= 0:
        raise ValueError("فایل ویدیوی قابل برش ندارد.")
    try:
        fps = round(float(Fraction(stream.get("avg_frame_rate") or "30")))
    except (ZeroDivisionError, ValueError):
        fps = 30
    fps = max(1, min(120, fps or 30))
    if duration < 1 / fps:
        raise ValueError("ویدیو از یک فریم کوتاه‌تر است.")
    width, height = int(stream["width"]), int(stream["height"])
    side_data = stream.get("side_data_list") or []
    rotations = [row.get("rotation") for row in side_data if "rotation" in row]
    rotation = int(rotations[0]) if rotations else int((stream.get("tags") or {}).get("rotate", 0))
    if abs(rotation) % 180 == 90:
        width, height = height, width
    presets = {"vertical": (1080, 1920), "square": (1080, 1080), "landscape": (1920, 1080)}
    width, height = presets.get(aspect, (width // 2 * 2, height // 2 * 2))
    if min(width, height) < 2 or max(width, height) > 4096:
        raise ValueError("برای این ویدیو یکی از ابعاد استاندارد را انتخاب کنید.")
    job = jobs.create_job(user_id=user)
    try:
        with path.open("rb") as media:
            raw = jobs.save_raw(job, source["filename"], media, expected_size=source["size_bytes"])
        plan = {"source": raw.relative_to(job.dir).as_posix(),
                "canvas": {"width": width, "height": height, "fps": fps},
                "segments": [{"id": "clip-1", "in": 0.0, "out": duration}],
                "export": {"file": "manual-edit.mp4"}}
        _, errors = jobs.save_plan(job, plan)
        if errors:
            raise ValueError("برنامهٔ اولیه با فرمت این ویدیو سازگار نیست.")
    except Exception:
        jobs.delete_job(job.id)
        raise
    return job.id


@router.post("/{conversation}/start", status_code=202)
async def start(request: Request, conversation: str):
    from app import credits
    from app.studio_tools import execute
    from brain.lm_gateway import work_scope

    user, _ = await _owned(request, conversation)
    with _lock(user, conversation):
        _, chat = await _owned(request, conversation)
        if chat["projects"] or chat["state"].get("motion"):
            return {"id": conversation, "started": True}
        panel = chat["state"].get("panel")
        if not panel:
            raise HTTPException(409, "این پروژه از صفحهٔ ادیتور دستی ساخته نشده است.")
        setup = ProjectSetup.model_validate(panel["setup"])
        try:
            attachments = await repo.get_attachments(setup.attachment_ids, conversation, user)
        except KeyError as exc:
            raise HTTPException(404, "یکی از فایل‌ها پیدا نشد.") from exc
        source = next((item for item in attachments if item["kind"] == "video"), None)
        if setup.engine in ("talking", "localize", "clips") and not source:
            raise HTTPException(422, "یک فایل ویدیو انتخاب کنید.")
        if setup.engine in ("vox", "story", "product") and not _motion_enabled():
            raise HTTPException(409, "موتور طراحی این سبک روی سرور فعال نیست.")
        if setup.engine in _MOTION_BRIEFS and not (
            setup.topic.strip() or setup.source_url or any(media["kind"] in ("image", "audio") for media in attachments)
        ):
            raise HTTPException(422, "موضوع، لینک منبع یا فایل مرتبط را وارد کنید.")
        if setup.source_url:
            from urllib.parse import urlsplit
            try:
                url = urlsplit(setup.source_url)
                if url.scheme not in ("http", "https") or not url.hostname or url.username is not None:
                    raise ValueError
            except ValueError as exc:
                raise HTTPException(422, "آدرس وب معتبر نیست.") from exc

        from engine.talking_reel import style_list
        style = setup.style or None
        if setup.engine == "talking" and style not in {None, "premium", *(item["id"] for item in style_list())}:
            raise HTTPException(422, "سبک انتخاب‌شده برای پروژهٔ جدید در دسترس نیست.")

        if setup.engine != "clips":
            await credits.gate(user)
        with work_scope("manual_editor", conversation, user=user, conversation=conversation):
            if setup.engine in _MOTION_BRIEFS:
                from app.studio_orchestrator import _start_motion_graphic
                brief = "\n".join(filter(None, [_MOTION_BRIEFS[setup.engine], setup.topic.strip(),
                                               f"مدت حدود {setup.seconds} ثانیه", setup.source_url]))
                await asyncio.to_thread(_start_motion_graphic, conversation, user, chat, brief, attachments)
                _, updated = await _owned(request, conversation)
                if not updated["state"].get("motion"):
                    raise HTTPException(422, "منبع برای ساخت موشن قابل استفاده نبود.")
            elif setup.engine == "clips":
                from app import jobs
                try:
                    ref = await asyncio.to_thread(_create_clip_job, user, source, setup.aspect)
                except (ValueError, OSError) as exc:
                    raise HTTPException(422, "آماده‌سازی ویدیو برای برش انجام نشد.") from exc
                state = {"attachment_ids": [source["id"]], "panel_native": True, "confirmed": False,
                         "render_target": "server", "last_observed": {}}
                try:
                    project = await repo.create_project(conversation, user, "motion",
                        setup.title.strip() or source["filename"], state, ref)
                except Exception:
                    await asyncio.to_thread(jobs.delete_job, ref)
                    raise
                await repo.update_project(project["id"], user, status="awaiting_confirmation")
            else:
                payload = {"source_path": source["path"], "filename": source["filename"], "user_key": user}
                ordered = [source["id"], *(row["id"] for row in attachments if row["id"] != source["id"])]
                state = {"attachment_ids": ordered, "auto_render": False,
                         "last_observed": {}, "render_target": "server", "panel_created": True}
                if setup.engine == "talking":
                    payload.update(style=None if style == "premium" else style,
                                   variant="premium" if style == "premium" else None)
                    state.update(workflow="analyzing", selected_style=None if style == "premium" else style)
                result = await asyncio.to_thread(execute, "analyze_talking_reel" if setup.engine == "talking" else "localize_video", payload)
                project = await repo.create_project(conversation, user, setup.engine,
                    setup.title.strip() or source["filename"], state, result["external_ref"])
                await repo.update_project(project["id"], user, status="running")
                await repo.emit(conversation, "tool.started", {"project_id": project["id"], "message": "تحلیل ویدیو شروع شد."})
    return {"id": conversation, "started": True}


async def _transcript_job(request, project_id):
    from app import jobs
    user = studio._user(request)
    try:
        project = await repo.get_project(project_id, user)
    except KeyError as exc:
        raise HTTPException(404, "پروژه پیدا نشد.") from exc
    job = jobs.get(project.get("external_ref")) if project["engine"] == "talking" and project.get("external_ref") else None
    if not job or not (job.dir / "transcript.json").is_file():
        raise HTTPException(409, "متن گفتار پس از تحلیل ویدیوی صحبتی در دسترس است.")
    return user, project, job


@router.get("/projects/{project_id}/transcript")
async def transcript(request: Request, project_id: str):
    from app import talking_reel
    from app.creative_plan import current

    _, project, job = await _transcript_job(request, project_id)
    raw = await asyncio.to_thread(talking_reel.transcript_for, job.dir, job.dir / "raw" / job.raw_name)
    engine = talking_reel.load(job.dir)
    settings = engine.get("render_settings") or {}
    dropped = set(settings.get("dropped_sentences") or [])
    version = current(project["state"])
    words = raw.get("words") or []
    from bisect import bisect_left
    starts = [word["start"] for word in words]
    return {
        "source_job": job.id, "version_id": (version or {}).get("id"),
        "editable": engine.get("style") == "talking_1" and engine.get("variant") != "premium"
                    and not settings.get("captions_only") and bool(version)
                    and project["state"].get("workflow") not in {"analyzing", "production"},
        "sentences": [{"id": index, "start": row["start"], "end": row["end"], "text": row["text"],
                       "dropped": index in dropped,
                       "words": [{"text": word.get("w", word.get("text", "")), "start": word["start"], "end": word["end"]}
                                 for word in words[bisect_left(starts, row["start"]):bisect_left(starts, row["end"])]]}
                      for index, row in enumerate(raw.get("sentences") or [])],
    }


class SentenceCut(BaseModel):
    version_id: str = Field(min_length=8, max_length=64)
    sentence: int = Field(ge=0, lt=10000)
    remove: bool


@router.patch("/projects/{project_id}/transcript")
async def cut_sentence(request: Request, project_id: str, edit: SentenceCut):
    from app import creative_plan, talking_reel
    from app.studio_orchestrator import _refresh_plan
    from creative.revise import RevisionOp, apply_to_talking

    user, project, _ = await _transcript_job(request, project_id)
    with _lock(user, project["conversation_id"]):
        _, project, job = await _transcript_job(request, project_id)
        version = creative_plan.current(project["state"])
        state = talking_reel.load(job.dir)
        if not version or version["id"] != edit.version_id:
            raise HTTPException(409, "برنامه تغییر کرده است. دوباره بارگذاری کنید.")
        if (project["state"].get("workflow") in {"analyzing", "production"}
            or state.get("style") != "talking_1" or state.get("variant") == "premium"
            or (state.get("render_settings") or {}).get("captions_only")):
            raise HTTPException(409, "برش جمله در این سبک یا هنگام رندر در دسترس نیست.")
        raw = await asyncio.to_thread(talking_reel.transcript_for, job.dir, job.dir / "raw" / job.raw_name)
        count = len(raw.get("sentences") or [])
        if edit.sentence >= count:
            raise HTTPException(422, "جمله پیدا نشد.")
        settings = state.get("render_settings") or {}
        dropped = set(settings.get("dropped_sentences") or [])
        if (edit.sentence in dropped) == edit.remove:
            return {"ok": True}
        if edit.remove:
            if len(dropped | {edit.sentence}) >= count:
                raise HTTPException(422, "حداقل یک جمله باید در تدوین باقی بماند.")
            change = apply_to_talking(talking_reel.public(state), [RevisionOp(op="remove_sentence", sentence=edit.sentence)], count)
            changes = change.changes
        else:
            changes = {"render_settings": {**settings, "dropped_sentences": sorted(dropped - {edit.sentence})}}
        if not changes:
            raise HTTPException(409, "موتور این تغییر را نپذیرفت.")
        await asyncio.to_thread(talking_reel.update, job.dir, changes)
        try:
            await asyncio.to_thread(talking_reel.plan_render, job.dir, job.dir / "raw" / job.raw_name,
                                    prepare_media=False)
        except ValueError as exc:
            await asyncio.to_thread(talking_reel.update, job.dir, {"render_settings": settings})
            raise HTTPException(422, "این برش محتوای قابل رندر باقی نمی‌گذارد.") from exc
        try:
            refreshed, _ = await _refresh_plan(project["conversation_id"], user, project, job, source="manual",
                                               note="برش گفتار از ادیتور دستی", announce=False, after_analysis=True)
            latest = creative_plan.current(refreshed["state"])
            content = {**latest["content"], "speech_cuts": changes["render_settings"]["dropped_sentences"]}
            next_state, created = creative_plan.add_version(refreshed["state"], content, source="manual", note="برش گفتار از ادیتور دستی")
            if created:
                await repo.update_project(project_id, user, state=next_state, status="awaiting_confirmation", source="manual")
        except Exception:
            await asyncio.to_thread(talking_reel.update, job.dir, {"render_settings": settings})
            raise
    return {"ok": True}


async def _native_job(request, project_id):
    from app import jobs

    user = studio._user(request)
    try:
        project = await repo.get_project(project_id, user)
    except KeyError as exc:
        raise HTTPException(404, "پروژه پیدا نشد.") from exc
    ref = project.get("external_ref")
    job = jobs.get(ref) if project["engine"] == "motion" and ref else None
    if not job or (job.user_id is not None and str(job.user_id) != user):
        raise HTTPException(409, "این پروژه برنامهٔ تدوین بومی ندارد.")
    try:
        plan = await asyncio.to_thread(jobs.load_plan, job)
    except FileNotFoundError as exc:
        raise HTTPException(409, "برنامهٔ تدوین هنوز آماده نیست.") from exc
    if (plan.get("generation_meta") or {}).get("remotion") or not plan.get("segments"):
        raise HTTPException(409, "این خروجی از یک کامپوزیشن تولید شده و برش بومی برایش در دسترس نیست.")
    return job, plan


@router.get("/projects/{project_id}/segments")
async def native_segments(request: Request, project_id: str):
    from app import plan_versions
    from engine.operations import segment_spans

    job, plan = await _native_job(request, project_id)
    spans = segment_spans(plan)
    versions = await asyncio.to_thread(plan_versions.list_versions, job)
    def span_payload(span):
        return {"id": span.id, "start": span.start, "end": span.end,
                "source_in": span.source_in, "source_out": span.source_out}
    from pathlib import Path
    layers = []
    for kind, key in _LAYER_KEYS.items():
        rows = [plan[key]] if kind == "music" and plan.get(key) else plan.get(key) or []
        for index, row in enumerate(rows):
            start = row.get("start", row.get("at", 0))
            end = row.get("end", start + row.get("duration", 0))
            layers.append({"kind": kind, "index": index, "start": start,
                           "end": spans[-1].end if kind == "music" else end,
                           "label": row.get("text") or Path(row.get("file") or "").name,
                           "position": row.get("position", "bottom"), "volume_db": row.get("volume_db", -14)})
    return {"segments": [span_payload(span) for span in spans], "duration": spans[-1].end,
            "layers": layers,
            "arrange": _can_arrange(plan),
            "fps": plan["canvas"]["fps"], "job_id": job.id,
            "version": versions[-1]["version"] if versions else None,
            "versions": [{"version": row["version"], "source": row.get("source", "")} for row in versions],
            "busy": job.render.status in {"queued", "running"}}


class SegmentChange(BaseModel):
    model_config = {"extra": "forbid"}
    version: int | None = None
    operation: Literal["trim", "remove_range", "restore", "split", "duplicate", "move"]
    segment_id: str | None = Field(default=None, max_length=80)
    start: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    restore_version: int | None = Field(default=None, ge=1)
    target_id: str | None = Field(default=None, max_length=80)
    after: bool = False


def _can_arrange(plan: dict) -> bool:
    # Current EditPlan geometry cannot remap every overlay through a reorder.
    return not any(plan.get(key) for key in (
        "captions", "broll", "music", "sfx", "visual_effects", "transitions", "poster", "cover", "denoise", "generation_meta",
    ))


def _arrange_segments(plan: dict, body: SegmentChange) -> dict:
    from copy import deepcopy
    from uuid import uuid4

    if not _can_arrange(plan):
        raise HTTPException(409, "این برنامه لایه‌هایی دارد که با جابه‌جایی قطعه همگام نمی‌شوند.")
    result = deepcopy(plan)
    clips = result["segments"]
    index = next((i for i, row in enumerate(clips) if row["id"] == body.segment_id), None)
    if index is None:
        raise HTTPException(422, "قطعه پیدا نشد.")
    clip = clips[index]
    if body.operation in {"duplicate", "split"} and len(clips) >= 500:
        raise HTTPException(422, "سقف تعداد قطعه‌های این برنامه رسیده است.")
    if body.operation == "duplicate":
        clips.insert(index + 1, {**clip, "id": "clip-" + uuid4().hex[:12]})
    elif body.operation == "split":
        if body.start is None:
            raise HTTPException(422, "زمان برش را انتخاب کنید.")
        frame = 1 / plan["canvas"]["fps"]
        start, end = clip["in"], clip["out"]
        cut = round(body.start / frame) * frame
        if cut - start < frame or end - cut < frame:
            raise HTTPException(422, "در هر طرف برش دست‌کم یک فریم لازم است.")
        zoom = clip.get("zoom") or {"from": 1.0, "to": 1.0}
        middle = zoom["from"] + (zoom["to"] - zoom["from"]) * (cut - start) / (end - start)
        left = {**clip, "out": cut, "zoom": {**zoom, "to": middle}}
        right = {**clip, "id": "clip-" + uuid4().hex[:12], "in": cut, "zoom": {**zoom, "from": middle}}
        clips[index:index + 1] = [left, right]
    else:
        if body.target_id == body.segment_id:
            return plan
        clips.pop(index)
        target = next((i for i, row in enumerate(clips) if row["id"] == body.target_id), None)
        if target is None:
            raise HTTPException(422, "مقصد جابه‌جایی پیدا نشد.")
        clips.insert(target + int(body.after), clip)
    return result


@router.patch("/projects/{project_id}/segments")
async def change_segment(request: Request, project_id: str, body: SegmentChange):
    from app import jobs, plan_versions

    if body.operation == "trim":
        operation = {"op": "trim_segment", "segment_id": body.segment_id,
                     "source_in": body.start, "source_out": body.end}
    else:
        operation = {"op": "remove_range", "t_start": body.start, "t_end": body.end}
    if body.operation in {"trim", "remove_range"} and (body.start is None or body.end is None or body.start >= body.end):
        raise HTTPException(422, "ابتدا یک بازهٔ زمانی معتبر انتخاب کنید.")
    user = studio._user(request)
    await _native_job(request, project_id)
    with _lock(user, project_id):
        job, plan = await _native_job(request, project_id)
        try:
            latest = await asyncio.to_thread(plan_versions.latest_version, job)
            if (latest["version"] if latest else None) != body.version or job.render.status in {"queued", "running"}:
                raise HTTPException(409, "برنامه تغییر کرده یا در حال رندر است.")
            if body.operation == "restore":
                if body.restore_version is None:
                    raise HTTPException(422, "نسخهٔ برنامه را انتخاب کنید.")
                prior = await asyncio.to_thread(plan_versions.get_version, job, body.restore_version)
                if not prior:
                    raise HTTPException(404, "این نسخهٔ برنامه پیدا نشد.")
                _, errors = await asyncio.to_thread(jobs.save_plan, job, prior["plan"], source="user_ui",
                    operations=[{"op": "restore", "from_version": body.restore_version}])
                if errors:
                    raise HTTPException(422, "بعضی از رسانه‌های این نسخه در دسترس نیستند.")
            elif body.operation in {"split", "duplicate", "move"}:
                candidate = _arrange_segments(plan, body)
                if candidate != plan:
                    _, errors = await asyncio.to_thread(jobs.save_plan, job, candidate, source="user_ui",
                        operations=[{"op": body.operation, "segment_id": body.segment_id}])
                    if errors:
                        raise HTTPException(422, "تغییر قطعه با برنامهٔ رندر سازگار نیست.")
            else:
                await asyncio.to_thread(jobs.apply_plan_operations, job, [operation],
                                        base_version=body.version, base_plan=plan)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return await native_segments(request, project_id)


class NativeRender(BaseModel):
    version: int | None = None
    preview: bool = False


@router.post("/projects/{project_id}/segments/render", status_code=202)
async def render_segments(request: Request, project_id: str, body: NativeRender):
    from app import jobs, plan_versions

    user = studio._user(request)
    await _native_job(request, project_id)
    with _lock(user, project_id):
        job, plan = await _native_job(request, project_id)
        project = await repo.get_project(project_id, user)
        if project["state"].get("render_target") == "browser":
            raise HTTPException(409, "این پروژه برای رندر مرورگر تنظیم شده است.")
        latest = await asyncio.to_thread(plan_versions.latest_version, job)
        if (latest["version"] if latest else None) != body.version:
            raise HTTPException(409, "از آخرین نسخهٔ برنامه رندر بگیرید.")
        try:
            await asyncio.to_thread(jobs.start_render, job, preview=body.preview, loudnorm=not body.preview, expected_plan=plan)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(409, str(exc)) from exc
        if project["state"].get("panel_native"):
            state = {**project["state"], "confirmed": True, "last_observed": {}}
            await repo.update_project(project_id, user, state=state, status="running")
    return {"status": job.render.status}


class LayerChange(BaseModel):
    model_config = {"extra": "forbid"}
    version: int | None = None
    kind: Literal["caption", "broll", "music", "sfx"]
    operation: Literal["add", "remove", "replace"]
    index: int | None = Field(default=None, ge=0, lt=1000)
    text: str = Field(default="", max_length=400)
    filename: str = Field(default="", max_length=255)
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float = Field(default=0, ge=0, allow_inf_nan=False)
    volume_db: float = Field(default=-14, ge=-80, le=12, allow_inf_nan=False)
    position: Literal["top", "bottom"] = "bottom"


_LAYER_KEYS = {"caption": "captions", "broll": "broll", "music": "music", "sfx": "sfx"}


def _library_file(kind: str, filename: str):
    from pathlib import Path
    from engine.library import LIBRARY_ROOT, load_index

    if not filename or Path(filename).name != filename:
        raise HTTPException(422, "یک فایل کتابخانه انتخاب کنید.")
    indexed = next((row for row in load_index().assets if row.category == kind and row.filename == filename), None)
    directory = (LIBRARY_ROOT / kind).resolve()
    path = (directory / filename).resolve()
    if not indexed or not path.is_relative_to(directory) or not path.is_file():
        raise HTTPException(404, "فایل در فهرست کتابخانه پیدا نشد.")
    return str(path)


def _apply_layer(plan: dict, change: LayerChange) -> dict:
    from copy import deepcopy
    from engine.operations import segment_spans

    key = _LAYER_KEYS[change.kind]
    result = deepcopy(plan)
    if change.kind == "music":
        result[key] = None if change.operation == "remove" else {
            **(result.get(key) or {}), "file": _library_file(change.kind, change.filename), "volume_db": change.volume_db,
        }
        return result
    rows = result.setdefault(key, [])
    if change.operation in {"remove", "replace"} and (change.index is None or change.index >= len(rows)):
        raise HTTPException(404, "لایه پیدا نشد.")
    if change.operation == "remove":
        rows.pop(change.index)
        return result

    duration = segment_spans(plan)[-1].end
    if change.start >= duration:
        raise HTTPException(422, "زمان آغاز باید داخل خروجی باشد.")
    if change.kind in {"caption", "broll"} and not change.start < change.end <= duration:
        raise HTTPException(422, "یک بازهٔ کامل داخل خروجی انتخاب کنید.")
    if change.kind == "caption":
        if not change.text.strip():
            raise HTTPException(422, "متن را وارد کنید.")
        item = {"start": change.start, "end": change.end, "text": change.text.strip(), "position": change.position}
    else:
        item = {"at": change.start, "file": _library_file(change.kind, change.filename)}
        if change.kind == "sfx":
            item["volume_db"] = change.volume_db
        else:
            item.update(duration=change.end - change.start, **{"in": 0})
    if change.operation == "replace":
        updated = {**rows[change.index], **item}
        if change.kind == "caption" and (updated.get("highlighted_word") or "") not in updated["text"]:
            updated.pop("highlighted_word", None)
        rows[change.index] = updated
    elif len(rows) < 200:
        rows.append(item)
    else:
        raise HTTPException(422, "حداکثر تعداد لایه‌های این نوع ثبت شده است.")
    return result


@router.patch("/projects/{project_id}/layers")
async def change_layer(request: Request, project_id: str, body: LayerChange):
    from app import jobs, plan_versions

    user = studio._user(request)
    await _native_job(request, project_id)
    with _lock(user, project_id):
        job, plan = await _native_job(request, project_id)
        latest = await asyncio.to_thread(plan_versions.latest_version, job)
        if (latest["version"] if latest else None) != body.version or job.render.status in {"queued", "running"}:
            raise HTTPException(409, "برنامه تغییر کرده یا در حال رندر است.")
        candidate = await asyncio.to_thread(_apply_layer, plan, body)
        if candidate != plan:
            _, errors = await asyncio.to_thread(jobs.save_plan, job, candidate, source="user_ui",
                                               operations=[{"op": body.operation, "kind": body.kind}])
            if errors:
                raise HTTPException(422, "این لایه با رسانه یا قالب رندر فعلی سازگار نیست.")
    return await native_segments(request, project_id)
