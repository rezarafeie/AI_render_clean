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
def narrator_options():
    from brain.localize import NARRATORS, VOICE_STYLES
    return {"voices": [{"id": i, "name": n, "note": d} for i, n, d in NARRATORS],
            "styles": [{"id": k, "label": v[0]} for k, v in VOICE_STYLES.items()]}


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
