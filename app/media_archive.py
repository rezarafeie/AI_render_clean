"""Read verified private R2 copies from the same owned media URLs."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.config import settings

VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
}


@lru_cache(maxsize=1)
def _store():
    from app.render_cloud.settings import CloudSettings, object_store

    return object_store(CloudSettings())


def receipt(path: Path, owner: str) -> dict | None:
    """A trusted migration receipt, scoped to the owner and original media path."""
    if not owner or path.suffix.lower() not in VIDEO_TYPES:
        return None
    try:
        path = path.resolve()
        relative = path.relative_to(Path(settings.JOBS_DIR).resolve()).as_posix()
        data = json.loads(path.with_name(path.name + ".r2.json").read_text())
        digest = data["sha256"]
        if (data["path"] != relative or type(data["size"]) is not int or data["size"] < 1
                or type(data["mtime_ns"]) is not int):
            return None
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            return None
        expected = f"media-archive/v1/{sha256(str(owner).encode()).hexdigest()}/{digest}{path.suffix.lower()}"
        if data["key"] == expected:
            return data
    except (OSError, KeyError, TypeError, ValueError):
        pass
    return None


def _range(header: str, size: int) -> tuple[int, int] | None:
    if not header:
        return None
    matched = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if matched:
        first, last = matched.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        elif last and int(last) > 0:
            start, end = max(0, size - int(last)), size - 1
        else:
            start, end = size, -1
        if 0 <= start <= end < size:
            return start, end
    raise HTTPException(416, "Invalid byte range", headers={"Content-Range": f"bytes */{size}"})


def serve(request: Request, path: Path, owner: str, *, filename: str | None = None, media_type: str | None = None):
    if path.is_file():
        return FileResponse(path, filename=filename, media_type=media_type)
    record = receipt(path, owner)
    if record is None:
        raise HTTPException(404, "Media not found")
    size = record["size"]
    params = {"Bucket": _store().bucket, "Key": record["key"]}
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
    status = 200
    requested = _range(request.headers.get("range", ""), size)
    if requested:
        start, end = requested
        params["Range"] = f"bytes={start}-{end}"
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        size = end - start + 1
        status = 206
    headers["Content-Length"] = str(size)
    if filename:
        from urllib.parse import quote

        headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(filename, safe="")
    content_type = media_type or VIDEO_TYPES[path.suffix.lower()]
    if request.method == "HEAD":
        return Response(status_code=status, media_type=content_type, headers=headers)
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        result = _store().client.get_object(**params)
    except (BotoCoreError, ClientError) as error:
        raise HTTPException(503, "Archived media is temporarily unavailable") from error
    body = result["Body"]
    if result["ContentLength"] != size or (requested and result.get("ContentRange") != headers["Content-Range"]):
        body.close()
        raise HTTPException(503, "Unexpected archived media response")

    def chunks():
        try:
            yield from body.iter_chunks(chunk_size=256 * 1024)
        finally:
            body.close()

    return StreamingResponse(chunks(), status_code=status, media_type=content_type, headers=headers)


def available(path: Path, owner: str) -> bool:
    return path.is_file() or receipt(path, owner) is not None


def media_paths(directory: Path, pattern: str, owner: str):
    """Keep archived versions visible in listings and version-number allocation."""
    paths = set(directory.glob(pattern))
    for sidecar in directory.glob(pattern + ".r2.json"):
        original = sidecar.with_name(sidecar.name.removesuffix(".r2.json"))
        if original not in paths and receipt(original, owner):
            paths.add(original)
    return paths


def media_size_time(path: Path, owner: str) -> tuple[int, float]:
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime
    except FileNotFoundError:
        archived = receipt(path, owner)
        if archived is None:
            raise
        return archived["size"], archived["mtime_ns"] / 1e9


def materialize(path: Path, owner: str) -> Path:
    """Restore the exact original path when a local editing tool needs a file."""
    if path.is_file():
        return path
    archived = receipt(path, owner)
    if archived is None:
        return path

    import fcntl
    import hashlib
    import os
    import shutil
    import tempfile

    with path.with_name(path.name + ".r2.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.is_file():
            return path
        if shutil.disk_usage(path.parent).free < archived["size"] + 1024**3:
            raise OSError("Insufficient workspace to restore archived media")
        store = _store()
        response = store.client.get_object(Bucket=store.bucket, Key=archived["key"])
        body = response["Body"]
        temporary = None
        try:
            digest = hashlib.sha256()
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".media-restore-", delete=False) as target:
                temporary = Path(target.name)
                total = 0
                for chunk in body.iter_chunks(chunk_size=1024**2):
                    total += len(chunk)
                    if total > archived["size"]:
                        raise OSError("Archived file exceeded its verified size")
                    digest.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            if total != archived["size"] or digest.hexdigest() != archived["sha256"]:
                raise OSError("Archived file failed checksum verification")
            os.utime(temporary, ns=(archived["mtime_ns"], archived["mtime_ns"]))
            temporary.replace(path)
        finally:
            body.close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return path
