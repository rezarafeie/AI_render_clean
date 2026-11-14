"""Talking-head reel API for a job (see ``app.talking_reel``)."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import talking_reel as store
from app.job_access import get_job_for_request, is_local_auth_bypass

router = APIRouter(prefix="/jobs/{job_id}/talking-reel", tags=["talking-reel"])


class ReelEdit(BaseModel):
    hook: Optional[str] = None
    hook_highlight: Optional[list[str]] = None
    name: Optional[str] = None
    title: Optional[str] = None
    music: Optional[str] = None
    cta: Optional[str] = None
    style: Optional[str] = None
    hook2: Optional[str] = None
    captions: Optional[list[dict]] = None
    storyboard: Optional[list[dict]] = None
    render_settings: Optional[dict] = None
    key_moments: Optional[list[dict]] = None


class EffectPreview(BaseModel):
    item: dict
    t: float


_preview_lock = threading.Lock()


@router.get("/effects")
def effects_catalog(request: Request, job_id: str):
    """The effects that can be added (Persian names and options), whether this server can render them, and the ones this reel already has."""
    job = _job(request, job_id)
    from engine import face_effects as effects
    settings = (store.load(job.dir).get("render_settings") or {})
    return {"catalog": effects.CATALOG, "available": effects.available(), "plan": settings.get("effects") or [],
            "error": store.load(job.dir).get("effects_error") or ""}


@router.post("/effects/preview")
def effects_preview(request: Request, job_id: str, body: EffectPreview):
    """One frame of the video with one effect on it (the finished video when there is one, else the upload): check text, timing and position."""
    job = _job(request, job_id)
    from engine import face_effects as effects
    state = store.load(job.dir)
    output = job.dir / str(state.get("output") or "")
    source = output if state.get("output") and output.is_file() else job.dir / "raw" / job.raw_name
    if not _preview_lock.acquire(blocking=False):
        raise HTTPException(429, "یک پیش‌نمایش دیگر در حال ساخت است؛ چند ثانیه بعد دوباره امتحان کنید.")
    try:
        png = job.dir / "talking_reel_work" / "effects" / "preview.png"
        png.unlink(missing_ok=True)
        effects.preview(source, body.item, body.t, png, work=job.dir / "talking_reel_work" / "effects")
    except effects.EffectsError as exc:
        raise HTTPException(422, str(exc))
    finally:
        _preview_lock.release()
    return FileResponse(png, media_type="image/png", headers={"Cache-Control": "no-store"})


def _job(request: Request, job_id: str):
    job = get_job_for_request(request, job_id)
    if not job.raw_name or not (job.dir / "raw" / job.raw_name).is_file():
        raise HTTPException(409, "this job has no source video")
    return job


@router.get("")
def status(request: Request, job_id: str):
    job = _job(request, job_id)
    result = store.public(store.load(job.dir))
    result["logo_uploaded"] = store.custom_logo(job.dir) is not None
    return result


@router.patch("")
def edit(request: Request, job_id: str, body: ReelEdit):
    job = _job(request, job_id)
    try:
        return store.public(store.update(job.dir, body.model_dump(exclude_unset=True)))
    except ValueError as exc:
        raise HTTPException(409 if "busy" in str(exc) else 422, str(exc))


@router.post("/render")
def render(request: Request, job_id: str, regenerate: bool = False):
    job = _job(request, job_id)
    from app import credits
    credits.gate_sync(request.state.user.id)
    try:
        return store.public(store.start(job.dir, job.dir / "raw" / job.raw_name, regenerate=regenerate))
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/analyze")
def analyze(request: Request, job_id: str, style: Optional[str] = None):
    job = _job(request, job_id)
    from app import credits
    credits.gate_sync(request.state.user.id)
    try:
        return store.public(store.analyze(
            job.dir, job.dir / "raw" / job.raw_name, style=style,
        ))
    except ValueError as exc:
        raise HTTPException(409, str(exc))

@router.post("/pause")
def pause(request: Request, job_id: str):
    job = _job(request, job_id)
    try: return store.public(store.pause(job.dir))
    except ValueError as exc: raise HTTPException(409, str(exc))

@router.post("/resume")
def resume(request: Request, job_id: str):
    job = _job(request, job_id)
    try: return store.public(store.resume(job.dir))
    except ValueError as exc: raise HTTPException(409, str(exc))

@router.post("/cancel")
def cancel(request: Request, job_id: str):
    job = _job(request, job_id)
    try: return store.public(store.cancel(job.dir))
    except ValueError as exc: raise HTTPException(409, str(exc))


@router.get("/media")
def list_media(request: Request, job_id: str):
    job = _job(request, job_id)
    return [p.name for p in store.user_media(job.dir)]


@router.post("/media")
async def upload_media(request: Request, job_id: str, files: list[UploadFile] = File(...)):
    """The creator's own pictures for the top half of "صحبتی ۲" (matched to sentences by the AI)."""
    import re
    import shutil

    job = _job(request, job_id)
    folder = job.dir / store.MEDIA_DIR
    folder.mkdir(exist_ok=True)
    saved = []
    for upload in files:
        name = re.sub(r"[^\w.\- ]", "_", Path(upload.filename or "image").name)[:120] or "image.png"
        if Path(name).suffix.lower() not in store.IMAGE_EXTENSIONS:
            raise HTTPException(422, f"{name}: only images (png, jpg, webp) are supported")
        with open(folder / name, "wb") as out:
            shutil.copyfileobj(upload.file, out, 1024 * 1024)
        saved.append(name)
    return {"saved": saved, "media": [p.name for p in store.user_media(job.dir)]}


@router.delete("/media/{name}", status_code=204)
def delete_media(request: Request, job_id: str, name: str):
    job = _job(request, job_id)
    path = (job.dir / store.MEDIA_DIR / name).resolve()
    if not path.is_relative_to((job.dir / store.MEDIA_DIR).resolve()) or not path.is_file():
        raise HTTPException(404, "file not found")
    path.unlink()


@router.post("/logo")
async def upload_logo(request: Request, job_id: str, file: UploadFile = File(...)):
    """Store a per-job transparent PNG for the talking-reel outro."""
    from PIL import Image

    job = _job(request, job_id)
    if Path(file.filename or "").suffix.lower() != ".png":
        raise HTTPException(422, "the outro logo must be a PNG file")
    data = await file.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(422, "the logo PNG must be smaller than 8 MB")
    path = job.dir / "talking_reel_logo.png"
    path.write_bytes(data)
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "invalid PNG image")
    return {"logo_uploaded": True}


@router.get("/logo")
def get_logo(request: Request, job_id: str):
    path = store.custom_logo(_job(request, job_id).dir)
    if not path:
        raise HTTPException(404, "custom logo not uploaded")
    return FileResponse(path, media_type="image/png")


@router.delete("/logo", status_code=204)
def delete_logo(request: Request, job_id: str):
    path = store.custom_logo(_job(request, job_id).dir)
    if path:
        path.unlink()


@router.get("/output")
def output(request: Request, job_id: str):
    job = _job(request, job_id)
    state = store.load(job.dir)
    path = (job.dir / state["output"]).resolve() if state.get("output") else None
    if not path or not path.is_file() or not path.is_relative_to(job.dir.resolve()):
        raise HTTPException(404, "not rendered yet")
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}_{path.name}")


list_router = APIRouter(prefix="/talking-reels", tags=["talking-reel"])


@list_router.get("/styles")
def styles():
    from engine.talking_reel import style_list

    return style_list()


@list_router.get("")
def list_reels(request: Request):
    """The user's jobs that have a talking reel, newest first."""
    from app import jobs as jobstore

    user_id = str(request.state.user.id)
    show_all_local = is_local_auth_bypass(request)
    items = []
    for job in jobstore.list_jobs():
        if not show_all_local and job.user_id is not None and str(job.user_id) != user_id:
            continue
        if not (job.dir / "talking_reel.json").is_file():
            continue
        state = store.load(job.dir)
        items.append({"job_id": job.id, "name": job.raw_name, "status": state.get("status"),
                      "stage": state.get("stage"), "hook": state.get("hook"), "output": state.get("output"),
                      "updated_at": state.get("updated_at") or 0})
    return sorted(items, key=lambda i: i["updated_at"], reverse=True)
