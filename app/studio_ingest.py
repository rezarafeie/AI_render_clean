"""Validate a file already on disk and register it as a conversation attachment.

Shared by device uploads and cloud imports so both pass the same checks.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from app.config import settings
from app import studio_store
from app.studio_store import repo

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
MAX_BYTES = {"video": 2 * 1024**3, "image": 25 * 1024**2, "audio": 100 * 1024**2}


class IngestError(ValueError):
    pass


def kind_of(filename: str) -> str | None:
    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_EXTENSIONS: return "video"
    if suffix in IMAGE_EXTENSIONS: return "image"
    if suffix in AUDIO_EXTENSIONS: return "audio"
    return None


def attachment_folder(user_key: str, conversation_id: str) -> Path:
    folder = studio_store.ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", user_key) / conversation_id / "attachments"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


async def finalize(user_key: str, conversation_id: str, temporary: Path, original: str, kind: str,
                   content_type: str, size: int, metadata: dict | None = None) -> dict:
    """Probe the written file, create the attachment row and move the file to its final path."""
    suffix = Path(original).suffix.lower()
    folder = temporary.parent
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
            raise IngestError("file has no video stream")
        if kind == "audio" and not any(item.get("codec_type") == "audio" for item in streams):
            raise IngestError("file has no audio stream")
    attachment = await repo.create_attachment(conversation_id, user_key, kind=kind,
        filename=original[:255], path=str(temporary), mime_type=(content_type or "application/octet-stream")[:100],
        size_bytes=size, metadata=metadata or {})
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
    return attachment
