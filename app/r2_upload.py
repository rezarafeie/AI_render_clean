"""Direct, resumable video uploads to private object storage."""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app import media_archive
from app.config import settings
from app.resumable_upload import DISK_RESERVE, MAX_ACTIVE, MAX_RESUMABLE, Start, TTL, _fail
from app.studio_flags import conversation_dir
from app.studio_ingest import attachment_folder, finalize, kind_of, validate_media
from app.studio_store import repo

router = APIRouter(prefix="/studio/conversations/{conversation_id}/r2-uploads", tags=["uploads"])
PART_SIZE = 16 * 1024**2
COPY_SIZE = 128 * 1024**2
PART_URL_TTL = 3600


async def _owner(request: Request, conversation_id: str) -> tuple[str, Path]:
    if not settings.STUDIO_DIRECT_R2_UPLOAD:
        raise HTTPException(404, "Direct upload is unavailable")
    owner = str(request.state.user.id)
    try:
        await repo.get_conversation(conversation_id, owner, message_limit=1)
    except KeyError:
        raise HTTPException(404, "Conversation not found") from None
    folder = conversation_dir(owner, conversation_id) / "r2-uploads"
    folder.mkdir(parents=True, exist_ok=True)
    return owner, folder


@asynccontextmanager
async def _lock(path: Path):
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise _fail(409, "upload_busy", "The upload is already being prepared.") from None
        yield


def _save(path: Path, record: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record))
    temporary.replace(path)


def _record(folder: Path, upload_id: str) -> tuple[Path, dict]:
    if len(upload_id) != 32 or not all(char in "0123456789abcdef" for char in upload_id):
        raise _fail(404, "not_found", "Upload not found.")
    path = folder / f"{upload_id}.json"
    try:
        record = json.loads(path.read_text())
    except FileNotFoundError:
        raise _fail(404, "not_found", "Upload not found.") from None
    if record["expires_at"] <= time.time():
        raise _fail(410, "upload_expired", "The upload expired.")
    return path, record


def _remote_parts(store, record: dict) -> dict:
    response = store.client.list_parts(Bucket=store.bucket, Key=record["key"], UploadId=record["multipart_id"])
    return {part["PartNumber"]: part for part in response.get("Parts", [])}


def _part_sizes(size: int) -> dict[int, int]:
    return {index + 1: min(PART_SIZE, size - offset)
            for index, offset in enumerate(range(0, size, PART_SIZE))}


def _parts_status(store, record: dict, *, resume: bool) -> dict:
    if record.get("attachment"):
        return {"id": record["id"], "attachment": record["attachment"], "parts": []}
    # After provider completion, the normal finish call resumes verified import.
    if record.get("assembled"):
        return {"id": record["id"], "parts": []}
    remote = _remote_parts(store, record) if resume else {}
    sizes = _part_sizes(record["size"])
    parts = []
    for number, length in sizes.items():
        if remote.get(number, {}).get("Size") == length:
            continue
        url = store.client.generate_presigned_url("upload_part", Params={
            "Bucket": store.bucket, "Key": record["key"], "UploadId": record["multipart_id"],
            "PartNumber": number, "ContentLength": length,
        }, ExpiresIn=PART_URL_TTL)
        start = (number - 1) * PART_SIZE
        parts.append({"start": start, "end": start + length, "url": url})
    return {"id": record["id"], "parts": parts}


def _begin(store, folder: Path, owner: str, body: Start, name: str) -> dict:
    now = time.time()
    active = 0
    for path in folder.glob("*.json"):
        record = json.loads(path.read_text())
        if record["expires_at"] <= now:
            # The bucket lifecycle expires staging objects and incomplete multipart uploads.
            path.unlink(missing_ok=True)
            continue
        identity = (record["filename"], record["size"], record["last_modified"])
        if identity == (name, body.size, body.last_modified):
            return _parts_status(store, record, resume=True)
        active += not bool(record.get("attachment"))
    if active >= MAX_ACTIVE:
        raise _fail(429, "too_many_uploads", "Finish or cancel another upload first.")
    upload_id = uuid.uuid4().hex
    key = f"{store.prefix(owner)}studio-upload/{upload_id}{Path(name).suffix.lower()}"
    content_type = media_archive.VIDEO_TYPES[Path(name).suffix.lower()]
    remote = store.client.create_multipart_upload(Bucket=store.bucket, Key=key, ContentType=content_type)
    record = {"id": upload_id, "multipart_id": remote["UploadId"], "key": key, "filename": name,
              "size": body.size, "content_type": content_type, "last_modified": body.last_modified, "expires_at": now + TTL}
    _save(folder / f"{upload_id}.json", record)
    return _parts_status(store, record, resume=False)


@router.post("", status_code=201)
async def start(request: Request, conversation_id: str, body: Start):
    owner, folder = await _owner(request, conversation_id)
    name = Path(body.filename).name
    if kind_of(name) != "video":
        raise HTTPException(404, "Direct upload is available for video")
    if body.size > MAX_RESUMABLE["video"]:
        raise _fail(413, "file_too_large", "The video is larger than 10 GB.")
    from app.studio_files import QuotaExceeded, ensure_room

    try:
        await ensure_room(owner, body.size)
    except QuotaExceeded as error:
        raise _fail(413, "quota_exceeded", str(error)) from None
    async with _lock(folder / ".start.lock"):
        try:
            store = media_archive._store()
            return await asyncio.to_thread(_begin, store, folder, owner, body, name)
        except HTTPException:
            raise
        except Exception:
            raise _fail(503, "r2_unavailable", "Direct video upload is temporarily unavailable.") from None


def _complete(store, path: Path, record: dict) -> None:
    from botocore.exceptions import ClientError

    args = {"Bucket": store.bucket, "Key": record["key"]}
    try:
        uploaded = store.client.head_object(**args)
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchKey", "NotFound"}:
            raise
        sizes = _part_sizes(record["size"])
        received = _remote_parts(store, record)
        if received.keys() != sizes.keys() or any(received[n]["Size"] != length for n, length in sizes.items()):
            raise _fail(409, "incomplete_upload", "Some video parts are missing.")
        parts = [{"PartNumber": n, "ETag": received[n]["ETag"]} for n in sizes]
        store.client.complete_multipart_upload(**args, UploadId=record["multipart_id"], MultipartUpload={"Parts": parts})
        uploaded = store.client.head_object(**args)
    if uploaded["ContentLength"] != record["size"]:
        raise _fail(422, "size_mismatch", "The stored video size did not match.")
    record["assembled"] = True
    _save(path, record)


def _download(store, record: dict, target: Path) -> str:
    if shutil.disk_usage(target.parent).free < record["size"] + DISK_RESERVE:
        raise _fail(507, "no_space", "There is temporarily no workspace to validate the video.")
    digest = hashlib.sha256()
    count = 0
    body = store.client.get_object(Bucket=store.bucket, Key=record["key"])["Body"]
    try:
        with target.open("wb") as file:
            for chunk in body.iter_chunks(chunk_size=1024**2):
                count += len(chunk)
                if count > record["size"]:
                    break
                file.write(chunk)
                digest.update(chunk)
    finally:
        body.close()
    if count != record["size"]:
        raise _fail(422, "size_mismatch", "The stored video size did not match.")
    return digest.hexdigest()


def _promote(store, record: dict, owner: str, digest: str) -> str:
    from botocore.exceptions import ClientError

    key = f"media-archive/v1/{hashlib.sha256(owner.encode()).hexdigest()}/{digest}{Path(record['filename']).suffix.lower()}"
    params = {"Bucket": store.bucket, "Key": key}
    source = {"Bucket": store.bucket, "Key": record["key"]}
    attributes = {"Metadata": {"sha256": digest}, "ContentType": record["content_type"]}
    try:
        head = store.client.head_object(**params)
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchKey", "NotFound"}:
            raise
        head = None
    if head is None:
        if record["size"] <= 4 * 1024**3:
            store.client.copy_object(**params, CopySource=source, MetadataDirective="REPLACE", **attributes)
        else:
            destination = store.client.create_multipart_upload(**params, **attributes)["UploadId"]
            try:
                parts = []
                for number, begin in enumerate(range(0, record["size"], COPY_SIZE), 1):
                    end = min(begin + COPY_SIZE, record["size"]) - 1
                    part = store.client.upload_part_copy(**params, CopySource=source, CopySourceRange=f"bytes={begin}-{end}",
                                                         PartNumber=number, UploadId=destination)
                    parts.append({"PartNumber": number, "ETag": part["CopyPartResult"]["ETag"]})
                store.client.complete_multipart_upload(**params, UploadId=destination, MultipartUpload={"Parts": parts})
            except Exception:
                with suppress(Exception):
                    store.client.abort_multipart_upload(**params, UploadId=destination)
                raise
        head = store.client.head_object(**params)
    if head["ContentLength"] != record["size"] or head.get("Metadata", {}).get("sha256") != digest:
        raise RuntimeError("Permanent archive metadata failed validation")
    return key


def _publish(target: Path, key: str, digest: str) -> None:
    source = target.stat()
    root = Path(settings.JOBS_DIR).resolve()
    marker = target.with_name(target.name + ".r2.json")
    _save(marker, {"path": target.resolve().relative_to(root).as_posix(), "key": key, "sha256": digest,
                   "mtime_ns": source.st_mtime_ns, "size": source.st_size, "category": "attachment"})


async def _registered(owner: str, conversation_id: str, record: dict) -> dict | None:
    if not record.get("registering"):
        return None
    for item in await repo.list_user_attachments(owner):
        if item["conversation_id"] != conversation_id or item["metadata"].get("direct_r2_upload") != record["id"]:
            continue
        target = Path(item["path"])
        if target.is_file() and not target.name.startswith(".r2-upload-"):
            return item
        if media_archive.receipt(target, owner):
            return item
    return None


async def _finish(owner: str, conversation_id: str, folder: Path, upload_id: str):
    path, _ = _record(folder, upload_id)
    async with _lock(path.with_suffix(".lock")):
        _, record = _record(folder, upload_id)
        if record.get("attachment"):
            return record["attachment"]
        target = attachment_folder(owner, conversation_id) / f".r2-upload-{upload_id}{Path(record['filename']).suffix.lower()}"
        try:
            store = media_archive._store()
            attachment = await _registered(owner, conversation_id, record)
            if not attachment:
                if not record.get("assembled"):
                    await asyncio.to_thread(_complete, store, path, record)
                digest = await asyncio.to_thread(_download, store, record, target)
                try:
                    await validate_media(target, "video")
                except (OSError, ValueError):
                    raise _fail(422, "invalid_media", "The video could not be validated.") from None
                key = await asyncio.to_thread(_promote, store, record, owner, digest)
                record.update(registering=True, archive_key=key, sha256=digest)
                _save(path, record)
                attachment = await finalize(owner, conversation_id, target, record["filename"], "video",
                                            record["content_type"], record["size"], {"direct_r2_upload": upload_id},
                                            validated=True)
            original = Path(attachment["path"])
            if original.is_file():
                await asyncio.to_thread(_publish, original, record["archive_key"], record["sha256"])
            result = {field: attachment[field] for field in ("id", "kind", "filename", "mime_type", "size_bytes")}
            record["attachment"] = result
            record.pop("failure", None)
            _save(path, record)
            original.unlink(missing_ok=True)
            with suppress(Exception):
                await asyncio.to_thread(store.client.delete_object, Bucket=store.bucket, Key=record["key"])
            return result
        except HTTPException:
            raise
        except Exception:
            raise _fail(503, "upload_finalize_failed", "The video could not be attached yet. Try again.") from None
        finally:
            target.unlink(missing_ok=True)


async def _finish_in_background(owner: str, conversation_id: str, folder: Path, upload_id: str) -> None:
    try:
        await _finish(owner, conversation_id, folder, upload_id)
    except HTTPException as error:
        if isinstance(error.detail, dict) and error.detail.get("code") == "upload_busy":
            return
        with suppress(HTTPException):
            path, _ = _record(folder, upload_id)
            async with _lock(path.with_suffix(".lock")):
                _, record = _record(folder, upload_id)
                if not record.get("attachment"):
                    record["failure"] = {"status": error.status_code, "detail": error.detail}
                    _save(path, record)


@router.post("/{upload_id}/complete", status_code=202)
async def complete(request: Request, conversation_id: str, upload_id: str, background: BackgroundTasks):
    owner, folder = await _owner(request, conversation_id)
    path, record = _record(folder, upload_id)
    if record.get("attachment"):
        return {"attachment": record["attachment"]}
    try:
        async with _lock(path.with_suffix(".lock")):
            record.pop("failure", None)
            record["finish_requested_at"] = time.time()
            _save(path, record)
            background.add_task(_finish_in_background, owner, conversation_id, folder, upload_id)
    except HTTPException as error:
        if not isinstance(error.detail, dict) or error.detail.get("code") != "upload_busy":
            raise
    return {"state": "validating"}


@router.get("/{upload_id}")
async def status(request: Request, conversation_id: str, upload_id: str):
    _, folder = await _owner(request, conversation_id)
    path, record = _record(folder, upload_id)
    if record.get("attachment"):
        return {"attachment": record["attachment"]}
    if failure := record.get("failure"):
        raise HTTPException(failure["status"], detail=failure["detail"])
    if time.time() - record.get("finish_requested_at", 0) > 30:
        try:
            async with _lock(path.with_suffix(".lock")):
                raise _fail(409, "upload_interrupted", "Video validation was interrupted. Retry the upload to continue.")
        except HTTPException as error:
            if not isinstance(error.detail, dict) or error.detail.get("code") != "upload_busy":
                raise
    return {"state": "validating"}


@router.delete("/{upload_id}", status_code=204)
async def cancel(request: Request, conversation_id: str, upload_id: str):
    owner, folder = await _owner(request, conversation_id)
    path, _ = _record(folder, upload_id)
    async with _lock(path.with_suffix(".lock")):
        _, record = _record(folder, upload_id)
        if record.get("attachment"):
            return
        store = media_archive._store()
        params = {"Bucket": store.bucket, "Key": record["key"]}
        with suppress(Exception):
            if not record.get("assembled"):
                await asyncio.to_thread(store.client.abort_multipart_upload, **params, UploadId=record["multipart_id"])
            await asyncio.to_thread(store.client.delete_object, **params)
        path.unlink(missing_ok=True)
