"""Localization API: English reel -> Persian voice-over, captions and CTA."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import localize as store
from app.job_access import is_local_auth_bypass

router = APIRouter(prefix="/localize", tags=["localize"])

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def _owned(request: Request, project_id: str) -> dict:
    try:
        state = store.load(project_id)
    except KeyError:
        raise HTTPException(404, "project not found")
    if not is_local_auth_bypass(request) and str(state.get("user_id")) != str(request.state.user.id):
        raise HTTPException(403, "You do not have access to this project")
    return state


@router.get("")
def list_projects(request: Request):
    user_id = None if is_local_auth_bypass(request) else str(request.state.user.id)
    return store.list_projects(user_id)


@router.post("", status_code=201)
def create_project(
    request: Request,
    video: UploadFile = File(...),
    cta_number: str = Form(""),
    music: Optional[str] = Form(None),
):
    name = video.filename or "source.mp4"
    if not any(name.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        raise HTTPException(422, "Upload an mp4, mov, m4v, webm or mkv video")
    if music and store.resolve_music(music) is None:
        raise HTTPException(422, "music file not found in the library")
    state = store.create(str(request.state.user.id), name, video.file, cta_number, music)
    store.start_analyze(state["id"])
    return store.public(store.load(state["id"]))


@router.get("/voices")
def narrator_options(request: Request):
    from brain import voice_clone
    from brain.localize import NARRATORS, VOICE_STYLES
    user = None if is_local_auth_bypass(request) else str(request.state.user.id)
    mine = [{"id": r["id"], "name": r["name"], "note": "صدای کلون‌شدهٔ شما", "clone": True} for r in voice_clone.list_clones(user)]
    return {"voices": [{"id": i, "name": n, "note": d} for i, n, d in NARRATORS] + mine,
            "styles": [{"id": k, "label": v[0]} for k, v in VOICE_STYLES.items()]}


CLONE_UPLOAD_LIMIT = 1_500_000_000
CLONE_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".webm", ".mp4", ".mov", ".m4v", ".mkv"}


@router.post("/voices/clone", status_code=202)
async def clone_voice(request: Request, file: UploadFile = File(...), name: str = Form(""), kind: str = Form("file"), consent: str = Form("")):
    """Start cloning a voice from a recording made in the app or from an audio/video file (30 s to 2 h). The person must confirm the voice is theirs or used with permission."""
    from pathlib import Path
    import uuid
    from brain import voice_clone
    if consent.lower() not in ("1", "true", "yes", "on"):
        raise HTTPException(422, "باید تأیید کنید که این صدا مال خودتان است یا اجازهٔ استفاده از آن را دارید")
    suffix = Path(file.filename or "voice.webm").suffix.lower() or ".webm"
    if suffix not in CLONE_EXTENSIONS:
        raise HTTPException(422, "فایل باید صدا یا ویدیو باشد (mp3، wav، m4a، mp4، mov، webm…)")
    folder = voice_clone.root() / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    with target.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > CLONE_UPLOAD_LIMIT:
                handle.close(); target.unlink(missing_ok=True)
                raise HTTPException(413, "حجم فایل از حد مجاز بیشتر است")
            handle.write(chunk)
    try:
        seconds = voice_clone.probe_seconds(target)
    except ValueError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(422, str(exc))
    if seconds < voice_clone.MIN_SECONDS:
        target.unlink(missing_ok=True)
        raise HTTPException(422, f"نمونه خیلی کوتاه است ({seconds:.0f} ثانیه)؛ دست‌کم {voice_clone.MIN_SECONDS:.0f} ثانیه صحبت لازم است")
    if seconds > voice_clone.MAX_SOURCE_SECONDS:
        target.unlink(missing_ok=True)
        raise HTTPException(422, "فایل از ۲ ساعت بیشتر است")
    user = "local" if is_local_auth_bypass(request) else str(request.state.user.id)
    return {"job": voice_clone.start(user, name, target, "recording" if kind == "recording" else "file")}


@router.get("/voices/clone/{job}")
def clone_status(request: Request, job: str):
    from brain import voice_clone
    user = "local" if is_local_auth_bypass(request) else str(request.state.user.id)
    state = voice_clone.job_state(job, user)
    if state is None:
        raise HTTPException(404, "job not found")
    return state


class VoiceRename(BaseModel):
    name: str


@router.patch("/voices/{voice_id}")
def rename_voice(request: Request, voice_id: str, body: VoiceRename):
    from brain import voice_clone
    user = "local" if is_local_auth_bypass(request) else str(request.state.user.id)
    row = voice_clone.rename(user, voice_id, body.name)
    if not row:
        raise HTTPException(404, "voice not found")
    return {"id": row["id"], "name": row["name"]}


class VoicePreview(BaseModel):
    text: str
    style: str = ""


@router.post("/voices/{voice_id}/preview")
def preview_voice(request: Request, voice_id: str, body: VoicePreview):
    """A short reading of the person's own text by a narrator (the studio's ElevenLabs and Gemini narrators, or their own cloned voice) in a delivery style,
    to hear it before choosing. The text is limited (it spends the provider's characters)."""
    from fastapi.responses import Response
    from brain import localize as speech, voice_clone
    user = "local" if is_local_auth_bypass(request) else str(request.state.user.id)
    stock = {voice for voice, _, _ in speech.NARRATORS if voice}
    if voice_id not in stock and not voice_clone.owns(user, voice_id):
        raise HTTPException(404, "voice not found")
    text = " ".join(body.text.split())
    if len(text) < 3:
        raise HTTPException(422, "متنی برای خواندن بنویسید")
    if len(text) > 400:
        raise HTTPException(422, "متن آزمایشی حداکثر ۴۰۰ نویسه باشد")
    try:
        from brain import lm_gateway
        if user != "local":
            lm_gateway.user_context.set(user)                 # the test reading is charged to the person like any narration
        script, _ = speech.narration_script([text], body.style if body.style in speech.VOICE_STYLES else "")
        audio, _ = speech._elevenlabs_with_timestamps(script, voice_id)
    except Exception as exc:
        provider = "Gemini" if voice_id.startswith("gemini:") else "ElevenLabs"
        reason = f"اعتبار {provider} کافی نیست" if "quota" in str(exc).lower() else f"{provider} پاسخ نداد"
        raise HTTPException(502, f"ساخت صدای آزمایشی ناموفق بود: {reason} ({str(exc)[:120]})")
    return Response(content=audio, media_type="audio/mpeg", headers={"cache-control": "private, no-store"})


@router.delete("/voices/{voice_id}")
def delete_voice(request: Request, voice_id: str):
    from brain import voice_clone
    user = "local" if is_local_auth_bypass(request) else str(request.state.user.id)
    try:
        removed = voice_clone.remove(user, voice_id)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    if not removed:
        raise HTTPException(404, "voice not found")
    return {"ok": True}


@router.get("/{project_id}")
def get_project(request: Request, project_id: str):
    return store.public(_owned(request, project_id))


class LineEdit(BaseModel):
    i: int
    fa: Optional[str] = None
    kind: Optional[str] = None


class ProjectEdit(BaseModel):
    title: Optional[str] = None
    title_emojis: Optional[str] = None
    cta_number: Optional[str] = None
    music: Optional[str] = None
    voice_provider: Optional[str] = None
    voice_id: Optional[str] = None
    voice_style: Optional[str] = None
    caption_box: Optional[str] = None
    title_box: Optional[str] = None
    end_card: Optional[bool] = None
    end_card_seconds: Optional[float] = None
    lines: Optional[list[LineEdit]] = None


@router.patch("/{project_id}")
def edit_project(request: Request, project_id: str, body: ProjectEdit):
    _owned(request, project_id)
    changes = body.model_dump(exclude_unset=True)
    if "lines" in changes:
        changes["lines"] = [{k: v for k, v in line.items() if v is not None} for line in changes["lines"]]
    try:
        return store.public(store.update(project_id, changes))
    except ValueError as exc:
        raise HTTPException(409 if "busy" in str(exc) else 422, str(exc))


@router.post("/{project_id}/analyze")
def analyze(request: Request, project_id: str):
    _owned(request, project_id)
    try:
        store.start_analyze(project_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return store.public(store.load(project_id))


@router.post("/{project_id}/render")
def render(request: Request, project_id: str):
    _owned(request, project_id)
    try:
        store.start_render(project_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return store.public(store.load(project_id))


@router.post("/{project_id}/pause")
def pause(request: Request, project_id: str):
    _owned(request, project_id)
    try:
        return store.public(store.pause(project_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/{project_id}/resume")
def resume(request: Request, project_id: str):
    _owned(request, project_id)
    try:
        return store.public(store.resume(project_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/{project_id}/cancel")
def cancel(request: Request, project_id: str):
    _owned(request, project_id)
    try:
        return store.public(store.cancel(project_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get("/{project_id}/output")
def output(request: Request, project_id: str):
    state = _owned(request, project_id)
    if not state.get("output"):
        raise HTTPException(404, "not rendered yet")
    path = (store.LOCALIZE_ROOT / project_id / state["output"]).resolve()
    if not path.is_file():
        raise HTTPException(404, "render file missing")
    return FileResponse(path, media_type="video/mp4", filename=f"{project_id}_{path.name}")


@router.get("/{project_id}/source")
def source(request: Request, project_id: str):
    state = _owned(request, project_id)
    path = (store.LOCALIZE_ROOT / project_id / state["source"]).resolve()
    if not path.is_file():
        raise HTTPException(404, "source missing")
    return FileResponse(path)


@router.delete("/{project_id}", status_code=204)
def delete_project(request: Request, project_id: str):
    _owned(request, project_id)
    try:
        store.delete(project_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
