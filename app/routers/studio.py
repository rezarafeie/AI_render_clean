"""Authenticated API for the chat-first Video Studio."""
from __future__ import annotations

import asyncio
import copy
import json
import re
import shutil
from typing import Literal, Optional
from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app import jobs as jobstore
from app.studio_orchestrator import cancel_project, confirm_action, dispatch_message, resume_project, sync_conversation
from app.studio_store import ROOT, repo
from app.studio_tools import list_tools
from app.job_access import get_job_for_request, is_local_auth_bypass

router = APIRouter(prefix="/studio", tags=["studio"])


@router.post('/media-session')
async def media_session(request: Request):
    from app.media_session import COOKIE
    from app.auth_routes import _cookie_secure
    response = JSONResponse({'ok': True}, headers={'Cache-Control': 'no-store'})
    bearer = request.headers.get('authorization', '')
    if bearer.startswith('Bearer '):
        response.set_cookie(COOKIE, bearer[7:], max_age=900, httponly=True,
                            secure=_cookie_secure(request), samesite='lax', path='/')
    return response

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
MAX_BYTES = {"video": 2 * 1024**3, "image": 25 * 1024**2, "audio": 100 * 1024**2}


def _user(request: Request) -> str:
    return str(request.state.user.id)


def _kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_EXTENSIONS: return "video"
    if suffix in IMAGE_EXTENSIONS: return "image"
    if suffix in AUDIO_EXTENSIONS: return "audio"
    raise HTTPException(422, "Only supported video, image and audio files can be attached")


def _public_project(project: dict) -> dict:
    """Remove server-only file paths while preserving asset indices for the UI."""
    result = copy.deepcopy(project)
    state = result.get("state") or {}
    assets = state.get("source_assets") or []
    state["source_assets"] = [{"index": index, "name": Path(str(item)).name} for index, item in enumerate(assets)]
    inspection = state.get("url_inspection")
    if isinstance(inspection, dict):
        for image in (inspection.get("images") or []) + (inspection.get("screenshots") or []):
            if isinstance(image, dict):
                image.pop("file", None)
    result["state"] = state
    return result


def _public_conversation(conversation: dict) -> dict:
    result = copy.deepcopy(conversation)
    result["projects"] = [_public_project(item) for item in result.get("projects") or []]
    from app.studio_manual import question
    session = result.get('state', {}).get('manual_session')
    result['state']['manual_question'] = question(session) if session and session.get('question_id') else None
    return result


def _public_event(event: dict) -> dict:
    """Scrub legacy and current event payloads before they cross the API boundary."""
    result = copy.deepcopy(event)

    def scrub(value):
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()
                    if key not in {"file", "path", "source_path"}}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    result["data"] = scrub(result.get("data") or {})
    return result


class ConversationCreate(BaseModel):
    title: str = Field(default="گفتگوی جدید", max_length=255)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    status_voice_enabled: bool | None = None
    execution_mode: Literal["auto", "manual"] | None = None
    agent_mode: Literal["lite", "medium"] | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12_000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=20)
    execution_mode: Literal["auto", "manual"] | None = None
    manual_question_id: str | None = Field(default=None, max_length=64)
    render_target: Literal["server", "browser"] | None = None
    agent_mode: Literal["lite", "medium"] = "lite"  # old API clients remain Lite


class StoryboardUpdate(BaseModel):
    scenes: list[dict] = Field(min_length=1, max_length=20)


class LegacyProjectOpen(BaseModel):
    engine: str = Field(pattern="^(motion|talking|localize)$")
    external_ref: str = Field(min_length=4, max_length=64, pattern="^[A-Za-z0-9_-]+$")
    title: str = Field(default="Video project", max_length=255)


@router.post("/conversations", status_code=201)
async def create_conversation(request: Request, body: ConversationCreate):
    from app.agents.store import preference
    value = await repo.create_conversation(_user(request), body.title.strip() or "گفتگوی جدید")
    return await repo.set_conversation(value["id"], _user(request), state={"agent_mode": await preference(_user(request))})


class AgentPreference(BaseModel):
    default_agent_mode: Literal["lite", "medium"]


@router.get("/agent-preferences")
async def get_agent_preference(request: Request):
    from app.agents.store import preference
    return {"default_agent_mode": await preference(_user(request))}


@router.put("/agent-preferences")
async def put_agent_preference(request: Request, body: AgentPreference):
    from app.agents.store import preference
    return {"default_agent_mode": await preference(_user(request), body.default_agent_mode)}


class AgentResume(BaseModel):
    decision: Literal["approve", "retry", "cancel"]


@router.post("/agent-runs/{run_id}/resume")
async def resume_agent(request: Request, run_id: str, body: AgentResume):
    from app.agents import store
    from app.agents.dispatcher import dispatch, ensure_available
    user = _user(request)
    try:
        record = await store.get_run(run_id, user)
        if record["agent_mode"] != "medium": raise HTTPException(409, "This run is not Medium")
        if body.decision == "cancel":
            claimed = await store.update(run_id, user, status="cancelled", claim={"waiting_approval", "waiting_job", "failed"})
        else:
            ensure_available("medium")
            if body.decision == "approve":
                claimed = await store.update(run_id, user, status="queued", claim={"waiting_approval"}, patch={"resume": {"approve": True}})
            else:
                # Retry resumes the persisted graph; the operation ledger forbids uncertain writes.
                from app.studio_flags import generation
                claimed = await store.update(run_id, user, status="queued", claim={"failed"},
                    patch={"stop_generation": generation(user, record["conversation_id"])})
            if claimed: await dispatch(run_id, user)
        if not claimed: raise HTTPException(409, "This run has already advanced; refresh the conversation")
        await repo.emit(record["conversation_id"], "agent.run.updated", {"run_id": run_id,
                        "agent_mode": "medium", "status": claimed["status"]})
        return {"id": run_id, "status": claimed["status"]}
    except KeyError: raise HTTPException(404, "execution not found")
    except ValueError as exc: raise HTTPException(409, str(exc))


@router.get("/conversations")
async def list_conversations(request: Request):
    return await repo.list_conversations(_user(request))


@router.post("/legacy/open")
async def open_legacy_project(request: Request, body: LegacyProjectOpen):
    """Attach an existing owned job to Studio without duplicating the engine job."""
    user_key = _user(request)
    for summary in await repo.list_conversations(user_key):
        conversation = await repo.get_conversation(summary["id"], user_key)
        if any(project.get("external_ref") == body.external_ref for project in conversation.get("projects", [])):
            return _public_conversation(conversation)

    if body.engine == "localize":
        from app import localize
        try:
            legacy = localize.load(body.external_ref)
        except KeyError as exc:
            raise HTTPException(404, "project not found") from exc
        if not is_local_auth_bypass(request) and str(legacy.get("user_id")) != user_key:
            raise HTTPException(403, "You do not have access to this project")
        title = str(legacy.get("title") or legacy.get("name") or body.title)
    else:
        job = get_job_for_request(request, body.external_ref)
        title = str(job.raw_name or (job.plan_data or {}).get("title") or body.title)

    conversation = await repo.create_conversation(user_key, title)
    project = await repo.create_project(conversation["id"], user_key, body.engine, title,
        {"last_observed": {}, "imported_legacy": True}, body.external_ref)
    await repo.add_message(conversation["id"], user_key, "assistant",
        "این پروژه به Studio اضافه شد. می‌توانید ادامهٔ تدوین و تغییرات بعدی را همین‌جا درخواست کنید.")
    await sync_conversation(conversation["id"], user_key)
    return _public_conversation(await repo.get_conversation(conversation["id"], user_key))


@router.get('/conversations/{conversation_id}/event-history')
async def event_history(request: Request, conversation_id: str, after: int = Query(0, ge=0)):
    try:
        events = await repo.events(conversation_id, _user(request), after, limit=500)
        return [_public_event(event) for event in events]
    except KeyError:
        raise HTTPException(404, 'conversation not found')


@router.get("/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str):
    try:
        await sync_conversation(conversation_id, _user(request))
        conversation = await repo.get_conversation(conversation_id, _user(request))
        from app.studio_orchestrator import conversation_busy
        payload = _public_conversation(conversation)
        from app.agents.store import runs
        payload["agent_runs"] = [{"id": r["id"], "message_id": r["message_id"], "agent_mode": r["agent_mode"],
                                  "status": r["status"], "plan": r["data"].get("plan"), "error": r["data"].get("error")}
                                 for r in await runs(conversation_id, _user(request))]
        payload["busy"] = await asyncio.to_thread(conversation_busy, conversation, _user(request))      # the server's own word, whichever process is working
        return payload
    except KeyError:
        raise HTTPException(404, "conversation not found")


@router.patch("/conversations/{conversation_id}")
async def update_conversation(request: Request, conversation_id: str, body: ConversationUpdate):
    try:
        changes = body.model_dump(exclude_unset=True)
        mode = changes.pop("execution_mode", None)
        agent_mode = changes.pop("agent_mode", None)
        if mode or agent_mode:
            old = await repo.get_conversation(conversation_id, _user(request))
            changes["state"] = {**old.get("state", {})}
            if mode: changes["state"]["execution_mode"] = mode
            if agent_mode: changes["state"]["agent_mode"] = agent_mode
            if mode == 'auto': changes['state']['manual_session'] = None
        return await repo.set_conversation(conversation_id, _user(request), **changes)
    except KeyError:
        raise HTTPException(404, "conversation not found")


@router.post("/conversations/{conversation_id}/attachments", status_code=201)
async def upload_attachment(request: Request, conversation_id: str, file: UploadFile = File(...)):
    user_key = _user(request)
    try:
        await repo.get_conversation(conversation_id, user_key)
    except KeyError:
        raise HTTPException(404, "conversation not found")
    original = Path(file.filename or "attachment").name
    kind = _kind(original); suffix = Path(original).suffix.lower()
    folder = ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", user_key) / conversation_id / "attachments"
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f"uploading_{id(file)}{suffix}"
    size = 0
    try:
        with open(temporary, "wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES[kind]: raise HTTPException(413, f"{kind} attachment is too large")
                target.write(chunk)
        if size == 0: raise HTTPException(422, "attachment is empty")
        # Decode/probe uploads now, before any engine sees them.
        if kind == "image":
            from PIL import Image
            with Image.open(temporary) as image:
                image.verify()
        else:
            from engine.probe import probe
            info = await asyncio.to_thread(probe, temporary)
            streams = info.get("streams", [])
            if kind == "video" and not any(item.get("codec_type") == "video" for item in streams):
                raise ValueError("file has no video stream")
            if kind == "audio" and not any(item.get("codec_type") == "audio" for item in streams):
                raise ValueError("file has no audio stream")
        attachment = await repo.create_attachment(conversation_id, user_key, kind=kind,
            filename=original[:255], path=str(temporary), mime_type=(file.content_type or "application/octet-stream")[:100],
            size_bytes=size, metadata={})
        target = folder / f"{attachment['id']}{suffix}"
        temporary.replace(target)
        if settings.DATABASE_URL:
            from app.database import AsyncSessionLocal
            from app.models import StudioAttachment
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = await db.get(StudioAttachment, attachment["id"]); row.path = str(target); await db.commit()
        else:
            from app import studio_store
            with studio_store._lock:
                data = studio_store._read(); data["attachments"][attachment["id"]]["path"] = str(target); studio_store._write(data)
        attachment["path"] = str(target)
        return {key: attachment[key] for key in ("id", "kind", "filename", "mime_type", "size_bytes")}
    except HTTPException:
        temporary.unlink(missing_ok=True); raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(422, "The attachment could not be validated") from exc


@router.get("/conversations/{conversation_id}/attachments/{attachment_id}")
async def get_attachment(request: Request, conversation_id: str, attachment_id: str):
    try:
        item = (await repo.get_attachments([attachment_id], conversation_id, _user(request)))[0]
    except (KeyError, IndexError):
        raise HTTPException(404, "attachment not found")
    path = Path(item["path"])
    if not path.is_file(): raise HTTPException(404, "attachment file is missing")
    return FileResponse(path, media_type=item.get("mime_type"), filename=item["filename"])


@router.post("/conversations/{conversation_id}/messages", status_code=202)
async def send_message(request: Request, conversation_id: str, body: MessageCreate):
    user_key = _user(request)
    try:
        conversation = await repo.get_conversation(conversation_id, user_key)
        from app.agents.dispatcher import ensure_available
        from app.agents import store as agent_store
        try: ensure_available(body.agent_mode)
        except ValueError as exc: raise HTTPException(503, str(exc))
        if body.agent_mode == "medium":
            active = await agent_store.runs(conversation_id, user_key)
            if any(r["agent_mode"] == "medium" and r["status"] in {"queued", "running", "waiting_approval", "waiting_job"} for r in active):
                raise HTTPException(409, "Medium در همین گفتگو یک اجرای فعال دارد؛ آن را ادامه دهید یا متوقف کنید. انتخاب موتور پیام جدید محفوظ است.")
        if body.render_target == "browser":
            current_id = conversation.get("state", {}).get("current_project_id")
            if current_id and not any(p.get("id") == current_id and p.get("state", {}).get("render_target_override") for p in conversation.get("projects", [])):
                current = await repo.get_project(current_id, user_key)
                active_job = jobstore.get(current.get("external_ref")) if current["engine"] != "localize" else None
                if (current["state"].get("render_started") and current["status"] == "running") or (active_job and active_job.render.status in {"queued", "running"}):
                    raise HTTPException(409, "A backend render is active. Stop it explicitly before switching to this device.")
                await repo.update_project(current_id, user_key, state={**current["state"], "render_target": "browser"})
        preferences = {"agent_mode": body.agent_mode}
        if body.execution_mode: preferences["execution_mode"] = body.execution_mode
        if body.render_target: preferences["render_target"] = body.render_target
        if preferences:
            await repo.set_conversation(conversation_id, user_key, state={**conversation.get("state", {}), **preferences})
        await repo.get_attachments(body.attachment_ids, conversation_id, user_key)
        display = body.content.strip()
        session = conversation.get('state', {}).get('manual_session')
        if session and session.get('question_id') and session['question_id'] == body.manual_question_id:
            from app.studio_manual import question
            spec = question(session)
            selected = next((c for c in spec['choices'] if c['value'] == display), None)
            if selected: display = spec['title'] + ': ' + selected['label']
        message = await repo.add_message(conversation_id, user_key, "user", display, body.attachment_ids, agent_mode=body.agent_mode)
        from app.studio_flags import generation
        record = await agent_store.create_run(conversation_id, user_key, message["id"], body.agent_mode,
            {"text": body.content.strip(), "attachment_ids": body.attachment_ids, "manual_question_id": body.manual_question_id,
             "initial_project_id": conversation.get("state", {}).get("current_project_id")})
        await agent_store.update(record["id"], user_key, patch={"stop_generation": generation(user_key, conversation_id)})
    except KeyError:
        raise HTTPException(404, "conversation or attachment not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    from app.agents.dispatcher import dispatch
    await dispatch(record["id"], user_key, lite_dispatch=dispatch_message)
    message["agent_run_id"] = record["id"]
    return message


@router.get("/conversations/{conversation_id}/events")
async def stream_events(request: Request, conversation_id: str,
                        after: int = Query(0, ge=0), last_event_id: str | None = Header(None, alias="Last-Event-ID")):
    user_key = _user(request)
    try: await repo.get_conversation(conversation_id, user_key)
    except KeyError: raise HTTPException(404, "conversation not found")
    try: cursor = max(after, int(last_event_id or 0))
    except ValueError: cursor = after

    async def generate():
        nonlocal cursor
        idle = 0
        while not await request.is_disconnected():
            await sync_conversation(conversation_id, user_key)
            events = await repo.events(conversation_id, user_key, cursor)
            if events:
                idle = 0
                for event in events:
                    cursor = event["seq"]
                    public_event = _public_event(event)
                    yield f"id: {cursor}\nevent: {event['type']}\ndata: {json.dumps(public_event, ensure_ascii=False)}\n\n"
            else:
                idle += 1
                if idle % 15 == 0: yield ": keep-alive\n\n"
            # Two seconds is responsive enough for user-facing progress while
            # avoiding a database poll storm across several open browser tabs.
            await asyncio.sleep(2)
    return StreamingResponse(generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations/{conversation_id}/events/{event_seq}/audio")
async def event_audio(request: Request, conversation_id: str, event_seq: int):
    try: await repo.get_conversation(conversation_id, _user(request))
    except KeyError: raise HTTPException(404, "conversation not found")
    folder = Path(settings.JOBS_DIR).expanduser() / "studio" / "status_audio" / conversation_id / str(event_seq)
    path = next((item for item in folder.glob("status.*") if item.is_file()), None) if folder.is_dir() else None
    if path is None: raise HTTPException(404, "status narration is not ready")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/conversations/{conversation_id}/projects")
async def conversation_projects(request: Request, conversation_id: str):
    try: return [_public_project(item) for item in (await repo.get_conversation(conversation_id, _user(request)))["projects"]]
    except KeyError: raise HTTPException(404, "conversation not found")


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    try:
        project = await repo.get_project(project_id, _user(request))
        await sync_conversation(project["conversation_id"], _user(request))
        return _public_project(await repo.get_project(project_id, _user(request)))
    except KeyError: raise HTTPException(404, "project not found")


@router.patch("/projects/{project_id}/storyboard")
async def update_storyboard(request: Request, project_id: str, body: StoryboardUpdate):
    user_key = _user(request)
    try: project = await repo.get_project(project_id, user_key)
    except KeyError: raise HTTPException(404, "project not found")
    if project["engine"] != "motion" or not project.get("external_ref"):
        raise HTTPException(409, "project has no editable storyboard")
    job = jobstore.get(project["external_ref"])
    if not job: raise HTTPException(404, "render job not found")
    from brain.content_creator import update_storyboard
    try: storyboard = update_storyboard(job, body.scenes)
    except ValueError as exc: raise HTTPException(422, str(exc))
    state = {**project["state"], "storyboard": storyboard}
    return _public_project(await repo.update_project(project_id, user_key, state=state, source="user_ui"))


@router.post("/actions/{action_id}/confirm")
async def confirm(request: Request, action_id: str):
    try: return await asyncio.to_thread(confirm_action, action_id, _user(request))
    except KeyError: raise HTTPException(404, "action not found")
    except ValueError as exc: raise HTTPException(409, str(exc))


@router.post("/actions/{action_id}/cancel")
async def cancel_action(request: Request, action_id: str):
    try:
        action = await repo.get_action(action_id, _user(request))
        if action["status"] != "pending": raise HTTPException(409, "action is already running or finished")
        return await repo.update_action(action_id, "canceled")
    except KeyError: raise HTTPException(404, "action not found")


@router.post("/projects/{project_id}/cancel")
async def cancel_running_project(request: Request, project_id: str):
    try: return await asyncio.to_thread(cancel_project, project_id, _user(request))
    except KeyError: raise HTTPException(404, "project not found")
    except ValueError as exc: raise HTTPException(409, str(exc))


class ResumeRequest(BaseModel):
    retry_confirmed: bool = Field(default=False,strict=True)


class RenderTargetRequest(BaseModel):
    target: str = Field(pattern="^(server|browser)$")


@router.get('/render-capabilities')
async def render_capabilities(request: Request):
    _user(request)
    return {"device_render_hold": True, "device_compositions": ["remotion-product-v1"],
            "native_engines": ["talking", "localize", "motion"], "companion_required_for_ai": False}


async def _browser_job(request: Request, project_id: str):
    try:
        project = await repo.get_project(project_id, _user(request))
    except KeyError:
        raise HTTPException(404, "project not found")
    job = jobstore.get(project.get("external_ref"))
    if project["engine"] != "motion" or not job:
        raise HTTPException(409, "This engine currently requires server rendering")
    return project, job


@router.patch('/projects/{project_id}/render-target')
async def set_render_target(request: Request, project_id: str, body: RenderTargetRequest):
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, "project not found")
    job = jobstore.get(project.get("external_ref")) if project["engine"] != "localize" else None
    if (project["state"].get("render_started") and project["status"] == "running") or (job and job.render.status in {"queued", "running"}):
        raise HTTPException(409, "A server render is already active; it has not been interrupted")
    state = {**project["state"], "render_target": body.target, "render_target_override": True}
    return _public_project(await repo.update_project(project_id, _user(request), state=state))


@router.get('/projects/{project_id}/browser-render')
async def browser_render_manifest(request: Request, project_id: str):
    _, job = await _browser_job(request, project_id)
    from app.browser_render import bundle
    try:
        manifest, _ = await asyncio.to_thread(bundle, job)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return manifest


@router.get('/projects/{project_id}/browser-render/assets/{asset_id}')
async def browser_render_asset(request: Request, project_id: str, asset_id: str, revision: str):
    _, job = await _browser_job(request, project_id)
    from app.browser_render import bundle
    try:
        manifest, files = await asyncio.to_thread(bundle, job)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if revision != manifest['revision']:
        raise HTTPException(409, "Project changed; prepare a fresh render")
    if asset_id not in files:
        raise HTTPException(404, "asset not found")
    return FileResponse(files[asset_id])


@router.post('/projects/{project_id}/browser-render/output')
async def browser_render_output(request: Request, project_id: str, revision: str, file: UploadFile = File(...)):
    project, job = await _browser_job(request, project_id)
    if project['state'].get('render_target') != 'browser' or job.render.status in {'running', 'queued'}:
        raise HTTPException(409, 'Browser rendering is not selected, or a server render is active')
    from app.browser_render import bundle
    from engine.probe import probe
    import os
    import uuid
    try:
        manifest, _ = await asyncio.to_thread(bundle, job)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if revision != manifest['revision']:
        raise HTTPException(409, 'Project changed; output was not installed')
    exports = job.dir / 'exports'
    exports.mkdir(exist_ok=True)
    output = exports / f'browser_{revision[:20]}.mp4'
    if output.is_file():
        return {'output': output.name, 'reused': True}
    temporary = exports / f'.browser-{uuid.uuid4().hex}.mp4'
    try:
        total = 0
        with temporary.open('wb') as sink:
            while chunk := await file.read(1024**2):
                total += len(chunk)
                if total > 256 * 1024**2:
                    raise HTTPException(413, 'Browser output exceeds 256 MB')
                sink.write(chunk)
        info = await asyncio.to_thread(probe, temporary)
        videos = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
        audio = any(s.get('codec_type') == 'audio' for s in info.get('streams', []))
        expected_audio = bool(manifest['props'].get('music') or any(s.get('narration') for s in manifest['props']['scenes']))
        duration = float(info.get('format', {}).get('duration', 0))
        if not videos or (videos[0].get('width'), videos[0].get('height')) not in {(1080, 1920), (720, 1280)} or abs(duration - manifest['durationInFrames']/30) > .25 or (expected_audio and not audio):
            raise HTTPException(422, 'Output validation failed: dimensions, duration or audio differ from the plan')
        # Recheck the revision after upload, not only before it.
        latest, _ = await asyncio.to_thread(bundle, job)
        if latest['revision'] != revision:
            raise HTTPException(409, 'Project changed during upload')
        os.replace(temporary, output)
        job.render.status = 'done'
        job.render.progress = 100
        job.render.output = output.name
        job.render.preview = False
        job.render.message = 'Rendered on user device; media structure validated'
        if output.name not in job.versions:
            job.versions.append(output.name)
        jobstore._write_status(job)
        await repo.emit(project['conversation_id'], 'tool.completed', {'project_id': project_id, 'tool': 'browser_render', 'message': 'رندر دستگاه دریافت شد؛ مدت، ابعاد و وجود صدا بررسی شد.'})
        return {'output': output.name, 'reused': False}
    finally:
        temporary.unlink(missing_ok=True)
        await file.close()


@router.post('/projects/{project_id}/resume')
async def resume_stopped_project(request: Request, project_id: str, body: ResumeRequest | None = None):
    confirmed=bool(body and body.retry_confirmed)
    try: return await asyncio.to_thread(resume_project, project_id, _user(request),retry_confirmed=confirmed)
    except KeyError: raise HTTPException(404, 'project not found')
    except ValueError as exc: raise HTTPException(409, str(exc))


class AcceptOutputRequest(BaseModel):
    candidate: str


@router.post('/projects/{project_id}/accept-output')
async def accept_output(request: Request, project_id: str, body: AcceptOutputRequest):
    user = _user(request)
    try:
        project = await repo.get_project(project_id, user)
    except KeyError:
        raise HTTPException(404, 'project not found')
    if project['engine'] != 'talking':
        raise HTTPException(409, 'No reviewable talking output')
    from app import talking_reel
    job = jobstore.get(project.get('external_ref'))
    state = talking_reel.load(job.dir) if job else {}
    candidate = state.get('candidate_output')
    if not candidate or candidate != body.candidate or state.get('status') not in {'error', 'done', 'awaiting_confirmation', 'needs_review'}:
        raise HTTPException(409, 'Output changed or rendering is still active')
    path = (job.dir / candidate).resolve()
    if not path.is_relative_to((job.dir / 'exports').resolve()) or not path.is_file():
        raise HTTPException(404, 'output not found')
    report = state.get('creative_review') or {}
    if not report:
        raise HTTPException(409, 'No quality review to override')
    # Preserve the reviewer verdict. User acceptance is not a fabricated QC pass.
    state['published_outputs'] = [*talking_reel.published_outputs(state), candidate]
    state.update(output=candidate, status='done', stage='', message='', progress=100,
                 quality_accepted_by_user=True)
    talking_reel.save(job.dir, state)
    await sync_conversation(project['conversation_id'], user)
    await repo.add_message(project['conversation_id'], user, 'assistant',
        'خروجی موجود با تأیید شما تحویل شد؛ نتیجهٔ بازبینی کیفیت حفظ شده و رندر مجدد انجام نشد.')
    return {'accepted': True}


@router.get("/projects/{project_id}/output")
async def project_output(request: Request, project_id: str, candidate: bool = False, file: str | None = None):
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, "project not found")
    ref = project.get("external_ref")
    path = None
    if project["engine"] == "localize" and ref:
        from app import localize
        state = localize.load(ref)
        path = localize.LOCALIZE_ROOT / ref / state.get("output", "")
    elif project["engine"] == "talking" and ref:
        from app import talking_reel
        job = jobstore.get(ref); state = talking_reel.load(job.dir) if job else {}
        relative = state.get('candidate_output') if candidate else state.get('output')
        if file:
            if not re.fullmatch(r'talking_reel_v[0-9]+\.mp4', file):
                raise HTTPException(404, 'version not found')
            if 'exports/' + file not in talking_reel.published_outputs(state):
                raise HTTPException(404, 'version is held for review')
            relative = 'exports/' + file
        path = (job.dir / relative).resolve() if job and relative else None
        if path and not path.is_relative_to((job.dir / 'exports').resolve()):
            raise HTTPException(404, 'output not found')
    elif project["engine"] == "motion" and ref:
        job = jobstore.get(ref)
        name = job.render.candidate_output if job and candidate else job.render.output if job else None
        path = job.dir / "exports" / name if job and name else None
    if not path or not path.is_file(): raise HTTPException(404, "output is not ready")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get('/projects/{project_id}/outputs')
async def project_outputs(request: Request, project_id: str):
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    job = jobstore.get(project.get('external_ref')) if project['engine'] == 'talking' else None
    if not job: return []
    from app import talking_reel
    published = talking_reel.published_outputs(talking_reel.load(job.dir))
    files = [p for p in (job.dir/'exports').glob('talking_reel_v*.mp4')
             if 'exports/' + p.name in published and re.fullmatch(r'talking_reel_v[0-9]+\.mp4', p.name) and p.is_file()
             and p.resolve().is_relative_to((job.dir/'exports').resolve())]
    return [{'file': p.name, 'version': int(re.search(r'_v([0-9]+)', p.name)[1])}
            for p in sorted(files, key=lambda p: int(re.search(r'_v([0-9]+)', p.name)[1]))]


@router.get("/projects/{project_id}/assets/{index}")
async def project_asset(request: Request, project_id: str, index: int):
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, "project not found")
    assets = project.get("state", {}).get("source_assets") or []
    if index < 0 or index >= len(assets): raise HTTPException(404, "asset not found")
    path = Path(assets[index]).resolve()
    allowed = [
        (ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", _user(request))).resolve(),
        (Path(settings.JOBS_DIR).expanduser()).resolve(),
    ]
    if not any(path.is_relative_to(root) for root in allowed) or not path.is_file():
        raise HTTPException(404, "asset not found")
    return FileResponse(path)


@router.get("/tools")
def tools(): return list_tools()


@router.get("/capabilities")
def capabilities():
    from brain.media_provider import list_providers
    from engine.talking_reel import style_list
    return {"engines": ["localize", "talking", "motion"], "talking_styles": style_list(),
            "media_providers": list_providers(), "aspect_ratios": {"localize": ["source"], "talking": ["9:16"], "motion": ["9:16"]},
            "live_events": "sse", "status_voice": True, "cancel": {"localize": True, "talking": True, "motion": False}}


@router.get('/projects/{project_id}/outputs')
async def project_outputs(request: Request, project_id: str):
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    job = jobstore.get(project.get('external_ref')) if project['engine'] == 'talking' else None
    if not job: return []
    from app import talking_reel
    published = talking_reel.published_outputs(talking_reel.load(job.dir))
    files = [p for p in (job.dir/'exports').glob('talking_reel_v*.mp4')
             if 'exports/' + p.name in published and re.fullmatch(r'talking_reel_v[0-9]+\.mp4', p.name) and p.is_file()
             and p.resolve().is_relative_to((job.dir/'exports').resolve())]
    return [{'file': p.name, 'version': int(re.search(r'_v([0-9]+)', p.name)[1])}
            for p in sorted(files, key=lambda p: int(re.search(r'_v([0-9]+)', p.name)[1]))]



# -- Creative Plan ---------------------------------------------------------------------------------

class PlanApproval(BaseModel):
    version_id: str = Field(min_length=8, max_length=64)


class PlanEdit(BaseModel):
    version_id: str = Field(min_length=8, max_length=64)
    edits: dict = Field(min_length=1, max_length=20)


@router.post('/projects/{project_id}/plan/approve')
async def approve_project_plan(request: Request, project_id: str, body: PlanApproval):
    from app.creative_plan import PlanError
    from app.studio_orchestrator import approve_plan
    try:
        return _public_project(await approve_plan(project_id, _user(request), body.version_id))
    except KeyError: raise HTTPException(404, 'project not found')
    except (PlanError, ValueError) as exc: raise HTTPException(409, str(exc))


@router.patch('/projects/{project_id}/plan')
async def edit_project_plan(request: Request, project_id: str, body: PlanEdit):
    from app.creative_plan import PlanError
    from app.studio_orchestrator import edit_plan
    try:
        return _public_project(await edit_plan(project_id, _user(request), body.version_id, body.edits))
    except KeyError: raise HTTPException(404, 'project not found')
    except PlanError as exc: raise HTTPException(422, str(exc))
    except ValueError as exc: raise HTTPException(409, str(exc))


@router.get('/projects/{project_id}/plan/frames/{folder}/{name}')
async def plan_frame(request: Request, project_id: str, folder: str, name: str):
    """Concept mockups for the plan; only files under the owned job's plan_frames folder are served."""
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    if not re.fullmatch(r'[0-9a-f]{16}', folder) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}\.jpg', name):
        raise HTTPException(404, 'frame not found')
    job = jobstore.get(project.get('external_ref')) if project['engine'] == 'talking' else None
    if not job: raise HTTPException(404, 'frame not found')
    root = (job.dir / 'plan_frames').resolve()
    path = (root / folder / name).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise HTTPException(404, 'frame not found')
    return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=86400'})


# -- Brand profile ---------------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    tagline: str | None = Field(default=None, max_length=200)
    cta: str | None = Field(default=None, max_length=200)
    accent_color: str | None = Field(default=None, pattern=r'^#[0-9A-Fa-f]{6}$')
    caption_font: Literal['default', 'Vazirmatn'] | None = None
    logo_motion: Literal['pop', 'fade', 'slide', 'none'] | None = None


@router.get('/profile')
async def get_profile(request: Request):
    from app import brand_profile
    return brand_profile.load(_user(request))


@router.put('/profile')
async def put_profile(request: Request, body: ProfileUpdate):
    from app import brand_profile
    return brand_profile.update(_user(request), body.model_dump(exclude_none=True))


@router.post('/profile/logo')
async def put_profile_logo(request: Request, file: UploadFile = File(...)):
    from tempfile import NamedTemporaryFile
    from PIL import Image, UnidentifiedImageError
    from app import brand_profile
    if Path(file.filename or '').suffix.lower() not in IMAGE_EXTENSIONS:
        raise HTTPException(422, 'Upload a PNG, JPG or WebP logo')
    data = await file.read(MAX_BYTES['image'] + 1)
    if len(data) > MAX_BYTES['image']: raise HTTPException(413, 'Logo is too large')
    with NamedTemporaryFile(suffix=Path(file.filename).suffix.lower()) as tmp:
        tmp.write(data); tmp.flush()
        try:
            with Image.open(tmp.name) as image: image.verify()
            return brand_profile.save_logo(_user(request), Path(tmp.name))
        except (UnidentifiedImageError, OSError): raise HTTPException(422, 'The file is not a valid image')


@router.get('/profile/logo')
async def get_profile_logo(request: Request):
    from app import brand_profile
    path = brand_profile.logo_path(_user(request))
    if not path: raise HTTPException(404, 'no logo')
    return FileResponse(path, media_type='image/png')


# -- Project Document (timeline) -------------------------------------------------------------------

@router.get('/projects/{project_id}/document')
async def project_document(request: Request, project_id: str):
    """The project's timeline, built from the exact render plan of its engine; read-only except captions (talking)."""
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    from app import project_document as documents
    engine, ref = project['engine'], project.get('external_ref')
    if not ref: raise HTTPException(409, 'The timeline appears once the project has started')
    try:
        if engine == 'talking':
            job = jobstore.get(ref)
            if not job: raise HTTPException(404, 'render job not found')
            from app import talking_reel
            if not talking_reel.load(job.dir).get('analysis_ready'):
                raise HTTPException(409, 'The timeline appears once the video has been analysed')
            document = await asyncio.to_thread(documents.talking_document, job.dir, job.dir / 'raw' / job.raw_name)
            plan = project['state'].get('plan') or {}
            versions = plan.get('versions') or []
            latest = versions[-1]['n'] if versions else None
            document['basis'] = {'plan_version': latest, 'rendered_version': plan.get('last_approved_n'),
                                 'workflow': project['state'].get('workflow'),
                                 'synced': latest is not None and latest == plan.get('last_approved_n')}
        elif engine == 'localize':
            document = await asyncio.to_thread(documents.localize_document, ref)
        elif engine == 'motion':
            job = jobstore.get(ref)
            if not job: raise HTTPException(404, 'render job not found')
            document = await asyncio.to_thread(documents.motion_document, job)
        else:
            raise HTTPException(409, 'No timeline for this kind of project')
    except FileNotFoundError:
        raise HTTPException(404, 'project files not found')
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return document


class TimelineOp(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(min_length=3, max_length=40)
    text: str | None = Field(default=None, max_length=400)
    start: float | None = None
    end: float | None = None
    deleted: bool | None = None
    reset: bool | None = None
    x: float | None = None
    y: float | None = None
    scale: float | None = None
    color: str | None = Field(default=None, max_length=7)


class TimelineEdit(BaseModel):
    version_id: str = Field(min_length=8, max_length=64)
    ops: list[TimelineOp] = Field(min_length=1, max_length=50)


@router.patch('/projects/{project_id}/timeline')
async def edit_project_timeline(request: Request, project_id: str, body: TimelineEdit):
    from app.creative_plan import PlanError
    from app.studio_orchestrator import edit_timeline
    try:
        return _public_project(await edit_timeline(project_id, _user(request), body.version_id,
                                                    [op.model_dump(exclude_none=True) for op in body.ops]))
    except KeyError: raise HTTPException(404, 'project not found')
    except PlanError as exc: raise HTTPException(422, str(exc))
    except ValueError as exc: raise HTTPException(409, str(exc))


# -- Upper-panel pictures (styles 2 and 3) -----------------------------------------------------------

class PictureOp(BaseModel):
    model_config = {"extra": "forbid"}
    slot: int = Field(ge=0, le=9999)
    source: Literal["upload", "library", "ai", "hidden"] | None = None
    media: str | None = Field(default=None, max_length=80)
    library: str | None = Field(default=None, max_length=220)
    visual: str | None = Field(default=None, max_length=700)
    label: str | None = Field(default=None, max_length=80)
    reset: bool | None = None


class PictureEdit(BaseModel):
    version_id: str = Field(min_length=8, max_length=64)
    ops: list[PictureOp] = Field(min_length=1, max_length=20)


@router.patch('/projects/{project_id}/pictures')
async def edit_project_pictures(request: Request, project_id: str, body: PictureEdit):
    from app.creative_plan import PlanError
    from app.studio_orchestrator import edit_pictures
    try:
        return _public_project(await edit_pictures(project_id, _user(request), body.version_id,
                                                    [op.model_dump(exclude_none=True) for op in body.ops]))
    except KeyError: raise HTTPException(404, 'project not found')
    except PlanError as exc: raise HTTPException(422, str(exc))
    except ValueError as exc: raise HTTPException(409, str(exc))


@router.post('/projects/{project_id}/media', status_code=201)
async def upload_project_picture(request: Request, project_id: str, file: UploadFile = File(...)):
    """Add a picture of the user's own to a talking project (the folder styles 2 and 3 already read uploads from)."""
    import hashlib
    from PIL import Image, UnidentifiedImageError
    from app import talking_reel
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    job = jobstore.get(project.get('external_ref')) if project['engine'] == 'talking' else None
    if not job: raise HTTPException(404, 'project not found')
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.png', '.jpg', '.jpeg', '.webp'}: raise HTTPException(422, 'Upload a PNG, JPG or WebP picture')
    data = await file.read(MAX_BYTES['image'] + 1)
    if not data or len(data) > MAX_BYTES['image']: raise HTTPException(413 if data else 422, 'Picture is empty or too large')
    name = f"upload_{hashlib.sha256(data).hexdigest()[:16]}{suffix}"
    folder = job.dir / talking_reel.MEDIA_DIR
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if not target.is_file():
        temporary = folder / f".{name}.part"
        temporary.write_bytes(data)
        try:
            with Image.open(temporary) as image: image.verify()
        except (UnidentifiedImageError, OSError):
            temporary.unlink(missing_ok=True); raise HTTPException(422, 'The file is not a valid image')
        temporary.replace(target)
    return {'name': name, 'size': len(data)}


@router.get('/projects/{project_id}/pictures/{slot}')
async def project_picture(request: Request, project_id: str, slot: int):
    """The picture the renderer will use for a slot (404 while it is still to be generated)."""
    from app import talking_reel
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    job = jobstore.get(project.get('external_ref')) if project['engine'] == 'talking' else None
    if not job: raise HTTPException(404, 'picture not found')
    try:
        planned = await asyncio.to_thread(talking_reel.plan_render, job.dir, job.dir / 'raw' / job.raw_name, prepare_media=False)
    except ValueError:
        raise HTTPException(404, 'picture not found')
    item = next((s for s in planned.slots if int(s['i']) == slot), None)
    path = Path(item['file']).resolve() if item and item.get('file') else None
    allowed = [job.dir.resolve(), (talking_reel.PROJECT_ROOT / 'assets').resolve()]
    if not path or not path.is_file() or not any(path.is_relative_to(root) for root in allowed):
        raise HTTPException(404, 'picture not found')
    return FileResponse(path, headers={'Cache-Control': 'private, max-age=300'})


@router.get('/library/pictures')
async def library_pictures(request: Request):
    from app import talking_reel
    return [{'path': item['path'], 'name': item.get('filename') or Path(item['path']).name, 'tags': (item.get('tags') or [])[:6]}
            for item in talking_reel._library_pictures()][:200]


# -- Editing preview (the plan rendered without captions) -------------------------------------------

async def _talking_job(request: Request, project_id: str):
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    job = jobstore.get(project.get('external_ref')) if project['engine'] == 'talking' else None
    if not job: raise HTTPException(404, 'talking project not found')
    return job


async def _clean_base_target(request: Request, project_id: str):
    """("talking", job) or ("localize", project id): the project whose caption-free preview is asked for."""
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    if project['engine'] == 'localize' and project.get('external_ref'):
        return 'localize', project['external_ref']
    job = jobstore.get(project.get('external_ref')) if project['engine'] == 'talking' else None
    if not job: raise HTTPException(404, 'talking project not found')
    return 'talking', job


@router.post('/projects/{project_id}/clean-base')
async def start_clean_base(request: Request, project_id: str):
    """Start (once) the caption-free render the timeline edits captions on; returns its status.
    Localize builds it from voice clips already made and never asks the voice service for anything."""
    import asyncio
    kind, target = await _clean_base_target(request, project_id)
    if kind == 'localize':
        from app import localize_clean_base
        return await asyncio.to_thread(localize_clean_base.ensure, target)
    from app import clean_base
    return await asyncio.to_thread(clean_base.ensure, target.dir, target.dir / 'raw' / target.raw_name)


@router.get('/projects/{project_id}/clean-base')
async def clean_base_status(request: Request, project_id: str, key: str | None = None):
    """Status as JSON; with ``key`` the video file itself."""
    import asyncio
    kind, target = await _clean_base_target(request, project_id)
    if kind == 'localize':
        from app import localize_clean_base as module
        if key:
            path = module.path_for(target, key)
            if not path: raise HTTPException(404, 'preview is not ready')
            return FileResponse(path, media_type='video/mp4')
        return await asyncio.to_thread(module.status, target)
    from app import clean_base
    if key:
        path = clean_base.path_for(target.dir, key)
        if not path: raise HTTPException(404, 'preview is not ready')
        return FileResponse(path, media_type='video/mp4')
    return await asyncio.to_thread(clean_base.status, target.dir, target.dir / 'raw' / target.raw_name)


class CaptionLookOp(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(min_length=3, max_length=40, pattern=r'^caption:l\d{1,4}:\d{1,3}$')
    reset: bool | None = None
    x: float | None = None
    y: float | None = None
    scale: float | None = None
    color: str | None = Field(default=None, max_length=7)


class CaptionLookEdit(BaseModel):
    ops: list[CaptionLookOp] = Field(min_length=1, max_length=50)


@router.patch('/projects/{project_id}/localize-captions')
async def edit_localize_captions(request: Request, project_id: str, body: CaptionLookEdit):
    """Where Localize captions sit on the frame (position, size, colour). Saved on the project; it starts no render
    and no voice generation, and the video is marked as needing a re-render."""
    import asyncio
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    if project['engine'] != 'localize' or not project.get('external_ref'):
        raise HTTPException(404, 'localize project not found')
    from app import localize as store
    try:
        await asyncio.to_thread(store.set_caption_looks, project['external_ref'], [op.model_dump(exclude_none=True) for op in body.ops])
    except KeyError: raise HTTPException(404, 'project not found')
    except ValueError as exc: raise HTTPException(409 if 'busy' in str(exc) else 422, str(exc))
    return {'ok': True}


@router.get('/fonts/{name}')
async def caption_font_file(name: str):
    """A caption font the renders use, so the timeline draws captions with the same letters."""
    from app import fonts
    path = fonts.path_for(name)
    if not path: raise HTTPException(404, 'font not found')
    return FileResponse(path, media_type='font/ttf' if path.suffix.lower() == '.ttf' else 'font/otf',
                        headers={'Cache-Control': 'public, max-age=86400'})


@router.get('/music')
async def music_library():
    """The bundled music beds a talking project can choose from."""
    from app import talking_reel
    return talking_reel.music_library()


@router.get('/music/{name}')
async def music_file(name: str):
    from app import talking_reel
    entry = next((m for m in talking_reel.music_library() if m['path'].rsplit('/', 1)[-1] == name), None)
    path = talking_reel.resolve_music(entry['path']) if entry else None
    if not path: raise HTTPException(404, 'music not found')
    return FileResponse(path, headers={'Cache-Control': 'public, max-age=86400'})


# -- Long-video content discovery ---------------------------------------------------------------------

def _discovery_dir(request: Request, analysis_id: str):
    from app import long_video
    try:
        return long_video.locate(analysis_id, _user(request))
    except KeyError:
        raise HTTPException(404, "analysis not found")


@router.get("/conversations/{conversation_id}/discovery")
async def conversation_discovery(request: Request, conversation_id: str):
    from app import long_video
    try:
        conversation = await repo.get_conversation(conversation_id, _user(request))
    except KeyError:
        raise HTTPException(404, "conversation not found")
    pointer = (conversation.get("state") or {}).get("discovery")
    if not pointer:
        return {"analysis": None}
    directory = _discovery_dir(request, pointer["analysis_id"])
    return {"analysis": await asyncio.to_thread(long_video.view, directory)}


@router.get("/discovery/{analysis_id}")
async def discovery_view(request: Request, analysis_id: str):
    from app import long_video
    return await asyncio.to_thread(long_video.view, _discovery_dir(request, analysis_id))


@router.get("/discovery/{analysis_id}/transcript")
async def discovery_transcript(request: Request, analysis_id: str, offset: int = 0, limit: int = 200, kind: str = "enhanced"):
    directory = _discovery_dir(request, analysis_id)
    source = directory / ("transcript.json" if kind == "enhanced" else "raw.json")
    if not source.is_file():
        return {"version": None, "total": 0, "segments": []}
    data = json.loads(source.read_text())
    segments = data["segments"][max(0, offset):max(0, offset) + max(1, min(limit, 500))]
    keep = ("id", "start", "end", "text", "enhanced_text", "flags", "uncertain", "confidence", "language", "speaker")
    return {"version": data.get("version"), "kind": kind, "total": len(data["segments"]), "segments": [{k: s.get(k) for k in keep if k in s} for s in segments]}


@router.post("/discovery/{analysis_id}/resume")
async def discovery_resume(request: Request, analysis_id: str):
    from app import long_video
    directory = _discovery_dir(request, analysis_id)
    long_video.start(directory)
    return {"resumed": True}


@router.post("/discovery/{analysis_id}/stop")
async def discovery_stop(request: Request, analysis_id: str):
    from app import long_video
    _discovery_dir(request, analysis_id)
    long_video.stop(analysis_id)
    return {"stopping": True}


class CandidateEdit(BaseModel):
    model_config = {"extra": "forbid"}
    title: str | None = Field(default=None, max_length=300)
    hook: str | None = Field(default=None, max_length=500)
    summary: str | None = Field(default=None, max_length=600)
    category: str | None = Field(default=None, max_length=40)
    hidden: bool | None = None
    ranges: list[list[float]] | None = Field(default=None, max_length=6)


@router.patch("/discovery/{analysis_id}/candidates/{candidate_id}")
async def discovery_edit(request: Request, analysis_id: str, candidate_id: str, body: CandidateEdit):
    from app import long_video
    directory = _discovery_dir(request, analysis_id)
    try:
        return await asyncio.to_thread(long_video.edit_candidate, directory, candidate_id, body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "candidate not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/discovery/{analysis_id}/candidates/{candidate_id}/start")
async def discovery_start_candidate(request: Request, analysis_id: str, candidate_id: str):
    from app import long_video
    directory = _discovery_dir(request, analysis_id)
    try:
        return await asyncio.to_thread(long_video.start_candidate, directory, candidate_id)
    except KeyError:
        raise HTTPException(404, "candidate not found")
    except Exception as exc:
        raise HTTPException(500, f"ساخت چت تدوین انجام نشد: {str(exc)[:200]}")


class MoreRequest(BaseModel):
    model_config = {"extra": "forbid"}
    focus: str = Field(default="", max_length=300)


@router.post("/discovery/{analysis_id}/more")
async def discovery_more(request: Request, analysis_id: str, body: MoreRequest):
    from app import long_video
    directory = _discovery_dir(request, analysis_id)
    try:
        long_video.request_more(directory, body.focus or "محتوای مستقل دیگری که قبلاً پیشنهاد نشده")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"started": True}


def _candidate(directory, candidate_id: str):
    from app import long_video
    analysis = long_video.load(directory)
    cand = next((c for c in analysis["candidates"] if c["id"] == candidate_id), None)
    if cand is None:
        raise HTTPException(404, "candidate not found")
    return analysis, cand


@router.get("/discovery/{analysis_id}/candidates/{candidate_id}/thumb")
async def discovery_thumb(request: Request, analysis_id: str, candidate_id: str):
    from app import long_video
    directory = _discovery_dir(request, analysis_id)
    analysis, cand = _candidate(directory, candidate_id)
    path = await asyncio.to_thread(long_video.thumbnail, directory, cand, Path(analysis["source_path"]))
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/discovery/{analysis_id}/candidates/{candidate_id}/preview")
async def discovery_preview(request: Request, analysis_id: str, candidate_id: str):
    from app import long_video
    directory = _discovery_dir(request, analysis_id)
    analysis, cand = _candidate(directory, candidate_id)
    path = await asyncio.to_thread(long_video.preview, directory, cand, Path(analysis["source_path"]))
    return FileResponse(path, media_type="video/mp4")


# -- Motion graphics -----------------------------------------------------------------------------------

def _motion_dir(request: Request, motion_id: str):
    from app import motion_graphic
    try:
        return motion_graphic.locate(motion_id, _user(request))
    except KeyError:
        raise HTTPException(404, "motion graphic not found")


class MotionChange(BaseModel):
    change: str = Field(min_length=2, max_length=3000)


@router.post("/conversations/{conversation_id}/stop")
async def stop_conversation(request: Request, conversation_id: str):
    """The Stop button: cancel whatever this chat is working on."""
    from app.studio_orchestrator import request_stop
    try:
        return await asyncio.to_thread(request_stop, conversation_id, _user(request))
    except KeyError:
        raise HTTPException(404, "conversation not found")


@router.get("/conversations/{conversation_id}/motion")
async def conversation_motion(request: Request, conversation_id: str):
    from app import motion_graphic
    try:
        conversation = await repo.get_conversation(conversation_id, _user(request))
    except KeyError:
        raise HTTPException(404, "conversation not found")
    pointer = (conversation.get("state") or {}).get("motion")
    if not pointer:
        return {"motion": None}
    return {"motion": await asyncio.to_thread(motion_graphic.view, _motion_dir(request, pointer["motion_id"]))}


@router.get("/motion/{motion_id}")
async def motion_view(request: Request, motion_id: str):
    from app import motion_graphic
    return await asyncio.to_thread(motion_graphic.view, _motion_dir(request, motion_id))


@router.get("/motion/{motion_id}/{kind}")
async def motion_media(request: Request, motion_id: str, kind: str, v: Optional[int] = None):
    from app import motion_graphic
    if kind not in {"video", "thumb", "source"}:
        raise HTTPException(404, "unknown file")
    try:
        path = await asyncio.to_thread(motion_graphic.media_path, _motion_dir(request, motion_id), kind, v)
    except KeyError:
        raise HTTPException(404, "file not ready")
    media_type = {"video": "video/mp4", "thumb": "image/jpeg", "source": "text/html"}[kind]
    headers = {"Cache-Control": "private, max-age=3600"}
    if kind in {"video", "source"}:
        headers["Content-Disposition"] = f'inline; filename="motion-graphic.{"mp4" if kind == "video" else "html"}"'
    return FileResponse(path, media_type=media_type, headers=headers)


@router.post("/motion/{motion_id}/stop")
async def motion_stop(request: Request, motion_id: str):
    from app import motion_graphic
    motion_graphic.stop(_motion_dir(request, motion_id))
    return {"ok": True}


@router.post("/motion/{motion_id}/retry")
async def motion_retry(request: Request, motion_id: str):
    from app import motion_graphic
    directory = _motion_dir(request, motion_id)
    record = await asyncio.to_thread(motion_graphic.load, directory)
    if record["status"] in motion_graphic.ACTIVE:
        raise HTTPException(409, "already running")
    await asyncio.to_thread(motion_graphic.start, directory, change=record.get("pending_change") or "")
    return {"ok": True}


@router.post("/motion/{motion_id}/revise")
async def motion_revise(request: Request, motion_id: str, body: MotionChange):
    from app import motion_graphic
    directory = _motion_dir(request, motion_id)
    record = await asyncio.to_thread(motion_graphic.load, directory)
    if record["status"] in motion_graphic.ACTIVE:
        raise HTTPException(409, "already running")
    await asyncio.to_thread(motion_graphic.revise, directory, body.change)
    return {"ok": True}
