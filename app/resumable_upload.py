"""Chunked, resumable uploads from the device, for media too large for one request (up to 10 GB of video).

The browser sends the file in pieces at a stated offset; the server only accepts the piece that continues
exactly where the last one ended, so a dropped connection resumes from `received` instead of starting over.
Finished files go through the same validation as every other upload (app.studio_ingest.finalize).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.studio_flags import conversation_dir
from app.studio_ingest import MAX_BYTES, attachment_folder, finalize, kind_of
from app.studio_store import repo

CHUNK_SIZE = 8 * 1024**2
MAX_CHUNK = 32 * 1024**2
MAX_RESUMABLE = {**MAX_BYTES, "video": 10 * 1024**3}
DISK_RESERVE = 5 * 1024**3          # never fill the disk: keep room for the render work that follows
MAX_ACTIVE = 2                      # unfinished uploads per user
TTL = 48 * 3600

router = APIRouter(prefix="/studio/conversations/{conversation_id}/uploads", tags=["uploads"])
_locks: dict[str, asyncio.Lock] = {}


def _user(request: Request) -> str:
    return str(request.state.user.id)


def _fail(status: int, code: str, message: str, **extra):
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _dir(user: str, conversation_id: str) -> Path:
    path = conversation_dir(user, conversation_id) / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file(user: str, conversation_id: str, upload_id: str) -> Path:
    if not upload_id.isalnum():
        raise _fail(404, "not_found", "Upload not found.")
    return _dir(user, conversation_id) / f"{upload_id}.json"


def _load(user: str, conversation_id: str, upload_id: str) -> dict:
    try:
        return json.loads(_file(user, conversation_id, upload_id).read_text())
    except (OSError, ValueError):
        raise _fail(404, "not_found", "Upload not found.") from None


def _save(user: str, session: dict) -> None:
    target = _file(user, session["conversation_id"], session["id"])
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(session))
    temporary.replace(target)


def _drop(user: str, session: dict) -> None:
    Path(session["part"]).unlink(missing_ok=True)
    _file(user, session["conversation_id"], session["id"]).unlink(missing_ok=True)


def _public(session: dict) -> dict:
    return {"id": session["id"], "received": session["received"], "size": session["size"],
            "chunk_size": CHUNK_SIZE, "filename": session["filename"]}


def _expire(user: str, conversation_id: str) -> list[dict]:
    """Remove abandoned uploads and return the live ones."""
    live = []
    for item in _dir(user, conversation_id).glob("*.json"):
        try: session = json.loads(item.read_text())
        except (OSError, ValueError): continue
        if time.time() - session.get("updated_at", 0) > TTL: _drop(user, session)
        else: live.append(session)
    return live


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    content_type: str = Field(default="application/octet-stream", max_length=100)
    last_modified: int = 0


async def start(user: str, conversation_id: str, body: Start, free_bytes=None) -> dict:
    try:
        await repo.get_conversation(conversation_id, user)
    except KeyError:
        raise _fail(404, "not_found", "Conversation not found.") from None
    name = Path(body.filename).name
    kind = kind_of(name)
    if kind is None:
        raise _fail(422, "unsupported_file", "Only supported video, image and audio files can be attached.")
    if body.size > MAX_RESUMABLE[kind]:
        raise _fail(413, "file_too_large", f"This {kind} file is larger than the allowed {MAX_RESUMABLE[kind] // 1024**3 or MAX_RESUMABLE[kind] // 1024**2} {'GB' if MAX_RESUMABLE[kind] >= 1024**3 else 'MB'}.")
    folder = attachment_folder(user, conversation_id)
    live = _expire(user, conversation_id)
    # The same file chosen again continues the unfinished upload instead of starting another.
    for session in live:
        if (session["filename"], session["size"], session.get("last_modified")) == (name, body.size, body.last_modified):
            return _public(session)
    if len(live) >= MAX_ACTIVE:
        raise _fail(429, "too_many_uploads", "Finish or cancel your other unfinished uploads first.")
    free = free_bytes if free_bytes is not None else shutil.disk_usage(folder).free
    if free < body.size + DISK_RESERVE:
        raise _fail(507, "no_space", "The server does not have enough free space for this file right now.")
    upload_id = uuid.uuid4().hex
    part = folder / f"resumable_{upload_id}{Path(name).suffix.lower()}"
    part.touch()
    session = {"id": upload_id, "conversation_id": conversation_id, "filename": name, "kind": kind, "size": body.size,
               "content_type": body.content_type, "last_modified": body.last_modified, "received": 0,
               "part": str(part), "created_at": time.time(), "updated_at": time.time()}
    _save(user, session)
    return _public(session)


async def append(user: str, conversation_id: str, upload_id: str, offset: int, length: int, chunks) -> dict:
    """Write one piece. `chunks` is an async iterator of bytes; only a completely received piece advances `received`."""
    lock = _locks.setdefault(upload_id, asyncio.Lock())
    async with lock:
        session = _load(user, conversation_id, upload_id)
        if offset != session["received"]:
            raise _fail(409, "offset_mismatch", "Resume from the server's position.", received=session["received"])
        if length <= 0 or length > MAX_CHUNK:
            raise _fail(413, "chunk_size", "Send pieces of at most 32 MB.")
        if offset + length > session["size"]:
            raise _fail(422, "past_end", "The piece goes beyond the declared file size.")
        part = Path(session["part"])
        os.truncate(part, offset)             # drop the tail of a piece that was cut off earlier
        written = 0
        with open(part, "ab") as out:
            async for block in chunks:
                written += len(block)
                if written > length:
                    raise _fail(422, "past_end", "The piece is longer than declared.")
                out.write(block)
        if written != length:
            raise _fail(400, "incomplete_chunk", "The piece did not arrive completely.", received=offset)
        session["received"] = offset + written
        session["updated_at"] = time.time()
        if session["received"] < session["size"]:
            _save(user, session)
            return {"done": False, **_public(session)}
        try:
            attachment = await finalize(user, conversation_id, part, session["filename"], session["kind"],
                                        session["content_type"], session["size"])
        except Exception:
            _drop(user, session)
            raise _fail(422, "invalid_media", "The file could not be validated. Check that it is a playable video, image or audio file.") from None
        _file(user, conversation_id, upload_id).unlink(missing_ok=True)
        _locks.pop(upload_id, None)
        return {"done": True, "attachment": {key: attachment[key] for key in ("id", "kind", "filename", "mime_type", "size_bytes")}}


@router.post("", status_code=201)
async def create(request: Request, conversation_id: str, body: Start):
    return await start(_user(request), conversation_id, body)


@router.get("/{upload_id}")
async def status(request: Request, conversation_id: str, upload_id: str):
    return _public(_load(_user(request), conversation_id, upload_id))


@router.put("/{upload_id}")
async def chunk(request: Request, conversation_id: str, upload_id: str, offset: int = Query(..., ge=0)):
    length = int(request.headers.get("content-length") or 0)
    return await append(_user(request), conversation_id, upload_id, offset, length, request.stream())


@router.delete("/{upload_id}", status_code=204)
async def cancel(request: Request, conversation_id: str, upload_id: str):
    user = _user(request)
    _drop(user, _load(user, conversation_id, upload_id))
