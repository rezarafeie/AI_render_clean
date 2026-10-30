"""Cloud media storage: browse a connected provider and import media into a conversation.

Provider access goes through the existing Composio session boundary in
hermes.services (per-user identity, reviewed read-tool allow-list). This module never
sees OAuth tokens. Bytes are streamed server-side from the temporary link Composio returns
and then pass through the same validation as a device upload (app.studio_ingest).
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import socket
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.config import settings
from app.studio_flags import conversation_dir
from app.studio_ingest import MAX_BYTES, attachment_folder, finalize, kind_of
from app.studio_store import repo, run

log = logging.getLogger(__name__)

DRIVE = "googledrive"
PROVIDERS = {DRIVE: {"name": "Google Drive", "toolkit": "googledrive",
                     "capabilities": {"browse": True, "search": True, "import": True, "export": False, "sync": False}}}
FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = ("id,name,mimeType,size,modifiedTime,md5Checksum,version,thumbnailLink,"
               "videoMediaMetadata(durationMillis,width,height)")
ACTIVE = {"queued", "connecting", "fetching_metadata", "downloading", "validating"}
FINAL = {"completed", "failed", "cancelled"}


class CloudError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _toolkit(provider: str) -> str:
    if provider not in PROVIDERS:
        raise CloudError("provider_unsupported", "This storage provider is not supported yet.", 404)
    return PROVIDERS[provider]["toolkit"]


async def _call(user: str, provider: str, slug: str, arguments: dict) -> dict:
    from fastapi import HTTPException
    from hermes.services.composio_read import execute
    try:
        result = await execute(user, _toolkit(provider), slug, arguments, max_chars=200_000)
    except HTTPException as exc:
        code = (exc.detail or {}).get("code", "") if isinstance(exc.detail, dict) else ""
        if code in {"COMPOSIO_TOOL_NOT_ALLOWED", "COMPOSIO_APPLICATION_NOT_ALLOWED"}:
            raise CloudError("provider_not_enabled", "Google Drive is not enabled on this server.", 503) from None
        if code in {"COMPOSIO_RATE_LIMITED", "COMPOSIO_BUSY"}:
            raise CloudError("rate_limited", "Google Drive is busy, try again in a moment.", 429) from None
        raise CloudError("provider_unavailable", "Google Drive could not be reached.", 502) from None
    data = result.get("data")
    # Composio wraps tool output as {data, successful, error}; accept both shapes.
    if isinstance(data, dict) and "successful" in data:
        if data.get("successful") is False:
            raise CloudError(_classify(str(data.get("error") or "")), _public_error(str(data.get("error") or "")), 422)
        data = data.get("data", {})
    return data if isinstance(data, dict) else {}


def _classify(error: str) -> str:
    text = error.lower()
    if "404" in text or "not found" in text: return "file_not_found"
    if "403" in text or "permission" in text or "forbidden" in text: return "permission_denied"
    if "401" in text or "expired" in text or "invalid_grant" in text or "not connected" in text: return "reconnect_required"
    if "429" in text or "rate" in text: return "rate_limited"
    return "provider_error"


def _public_error(error: str) -> str:
    return {"file_not_found": "The file was moved or deleted in Google Drive.",
            "permission_denied": "Your Google Drive account cannot access this file.",
            "reconnect_required": "Reconnect Google Drive to continue.",
            "rate_limited": "Google Drive is busy, try again in a moment."}.get(_classify(error), "Google Drive returned an error.")


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _file(item: dict) -> dict:
    mime = str(item.get("mimeType") or "")
    video = item.get("videoMediaMetadata") or {}
    name = str(item.get("name") or "")
    try: size = int(item.get("size")) if item.get("size") is not None else None
    except (TypeError, ValueError): size = None
    return {"id": str(item.get("id") or ""), "name": name, "mime_type": mime, "size": size,
            "is_folder": mime == FOLDER_MIME, "modified": item.get("modifiedTime"),
            "kind": kind_of(name), "native": mime.startswith("application/vnd.google-apps.") and mime != FOLDER_MIME,
            "thumbnail": item.get("thumbnailLink") if str(item.get("thumbnailLink") or "").startswith("https://") else None,
            "duration": (int(video["durationMillis"]) / 1000) if video.get("durationMillis") else None,
            "width": video.get("width"), "height": video.get("height"),
            "checksum": item.get("md5Checksum"), "version": str(item["version"]) if item.get("version") is not None else None}


async def list_files(user: str, provider: str, folder: str = "root", query: str = "", media: str = "",
                     page_token: str | None = None, page_size: int = 50, sort: str = "folder,name") -> dict:
    kinds = {"video": "video/", "audio": "audio/", "image": "image/"}
    parts = ["trashed = false"]
    if query.strip():
        parts.append(f"name contains '{_quote(query.strip()[:200])}'")
    else:
        parts.append(f"'{_quote(folder or 'root')}' in parents")
    mimes = [f"mimeType = '{FOLDER_MIME}'"] + [f"mimeType contains '{kinds[m]}'" for m in ([media] if media in kinds else kinds)]
    parts.append("(" + " or ".join(mimes) + ")")
    order = {"name": "folder,name", "size": "quotaBytesUsed desc", "modified": "modifiedTime desc"}.get(sort, "folder,name")
    args = {"q": " and ".join(parts), "fields": f"nextPageToken,files({FILE_FIELDS})", "orderBy": order,
            "pageSize": max(1, min(int(page_size), 100)), "supportsAllDrives": True, "corpora": "allDrives"}
    if page_token: args["pageToken"] = page_token
    data = await _call(user, provider, "GOOGLEDRIVE_FIND_FILE", args)
    return {"files": [_file(item) for item in data.get("files", []) if isinstance(item, dict) and item.get("id")],
            "next_page_token": data.get("nextPageToken") or None}


async def metadata(user: str, provider: str, file_id: str) -> dict:
    data = await _call(user, provider, "GOOGLEDRIVE_GET_FILE_METADATA",
                       {"fileId": file_id, "fields": FILE_FIELDS, "supportsAllDrives": True})
    if not data.get("id"):
        raise CloudError("file_not_found", "The file was moved or deleted in Google Drive.", 404)
    return _file(data)


# --- download link safety -------------------------------------------------------------

def allowed_hosts() -> tuple[str, ...]:
    return tuple(h.strip().lower() for h in settings.CLOUD_DOWNLOAD_HOSTS.split(",") if h.strip())


def safe_download_url(url: str) -> str:
    """Only https links to the configured hosts that resolve to public addresses."""
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password or parts.port not in (None, 443):
        raise CloudError("unsafe_link", "The download link was refused.", 502)
    if not any(host == h.lstrip(".") or host.endswith(h) for h in allowed_hosts()):
        raise CloudError("unsafe_link", "The download link was refused.", 502)
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError:
        raise CloudError("network", "The file could not be reached.", 502) from None
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise CloudError("unsafe_link", "The download link was refused.", 502)
    return url


# --- transfer records -----------------------------------------------------------------

def _dir(user: str, conversation_id: str) -> Path:
    path = conversation_dir(user, conversation_id) / "cloud"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(user: str, conversation_id: str, transfer_id: str) -> Path:
    if not transfer_id.isalnum():
        raise CloudError("not_found", "Transfer not found.", 404)
    return _dir(user, conversation_id) / f"{transfer_id}.json"


def _write(user: str, record: dict) -> dict:
    record["updated_at"] = time.time()
    target = _path(user, record["conversation_id"], record["id"])
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record))
    temporary.replace(target)
    return record


def get_transfer(user: str, conversation_id: str, transfer_id: str) -> dict:
    try:
        return json.loads(_path(user, conversation_id, transfer_id).read_text())
    except (OSError, ValueError):
        raise CloudError("not_found", "Transfer not found.", 404) from None


def list_transfers(user: str, conversation_id: str) -> list[dict]:
    items = []
    for file in _dir(user, conversation_id).glob("*.json"):
        try: items.append(json.loads(file.read_text()))
        except (OSError, ValueError): continue
    return sorted(items, key=lambda item: item.get("created_at", 0), reverse=True)


def public(record: dict) -> dict:
    keys = ("id", "state", "provider", "file_id", "filename", "kind", "size", "bytes", "error_code", "error",
            "attachment_id", "reused", "created_at", "updated_at", "retryable", "speed")
    return {key: record.get(key) for key in keys}


def _set(user: str, record: dict, **values) -> dict:
    record.update(values)
    _write(user, record)
    return record


async def _aset(user: str, record: dict, **values) -> dict:
    _set(user, record, **values)
    try:
        await repo.emit(record["conversation_id"], "cloud.progress", public(record))
    except Exception:   # progress is best effort; the record on disk is the truth
        log.debug("cloud progress event not delivered")
    return record


def _cancelled(user: str, record: dict) -> bool:
    return _path(user, record["conversation_id"], record["id"]).with_suffix(".cancel").exists()


async def begin_import(user: str, conversation_id: str, provider: str, file_id: str) -> dict:
    _toolkit(provider)
    if not file_id or len(file_id) > 200:
        raise CloudError("invalid_file", "Choose a file.")
    try:
        await repo.get_conversation(conversation_id, user)
    except KeyError:
        raise CloudError("not_found", "Conversation not found.", 404) from None
    info = await metadata(user, provider, file_id)
    if info["is_folder"]:
        raise CloudError("unsupported_file", "Choose a video, audio or image file, not a folder.")
    if info["native"]:
        raise CloudError("unsupported_file", "Google Docs, Sheets and Slides cannot be imported as media.")
    kind = kind_of(info["name"])
    if kind is None:
        raise CloudError("unsupported_file", "Only supported video, image and audio files can be imported.")
    if info["size"] is not None and info["size"] > MAX_BYTES[kind]:
        raise CloudError("file_too_large", f"This {kind} file is larger than the allowed size.", 413)
    # Reuse a finished import of the same file version instead of transferring it again.
    for old in list_transfers(user, conversation_id):
        if (old.get("provider") == provider and old.get("file_id") == file_id and old.get("state") == "completed"
                and old.get("version") == info["version"] and old.get("checksum") == info["checksum"]):
            try:
                await repo.get_attachments([old["attachment_id"]], conversation_id, user)
                return {**public(old), "reused": True}
            except (KeyError, IndexError):
                break
        if old.get("provider") == provider and old.get("file_id") == file_id and old.get("state") in ACTIVE:
            return public(old)
    record = {"id": uuid.uuid4().hex, "user": user, "conversation_id": conversation_id, "provider": provider,
              "file_id": file_id, "filename": info["name"], "kind": kind, "size": info["size"], "bytes": 0,
              "version": info["version"], "checksum": info["checksum"], "modified": info["modified"],
              "mime_type": info["mime_type"], "state": "queued", "created_at": time.time(), "attempts": 0}
    _write(user, record)
    dispatch(record["id"], user, conversation_id)
    return public(record)


def dispatch(transfer_id: str, user: str, conversation_id: str) -> None:
    from app.celery_app import CELERY_AVAILABLE
    if CELERY_AVAILABLE:
        from app.tasks import task_cloud_import
        from request_context import celery_request_headers
        task_cloud_import.apply_async(args=[transfer_id, user, conversation_id], headers=celery_request_headers())
    else:
        import contextvars
        import threading
        context = contextvars.copy_context()
        threading.Thread(target=context.run, args=(run_import, transfer_id, user, conversation_id),
                         daemon=True, name="cloud-import").start()


def cancel(user: str, conversation_id: str, transfer_id: str) -> dict:
    record = get_transfer(user, conversation_id, transfer_id)
    if record["state"] in FINAL:
        return public(record)
    _path(user, conversation_id, transfer_id).with_suffix(".cancel").touch()
    if record["state"] == "queued":
        record = _set(user, record, state="cancelled")
    return public(record)


def retry(user: str, conversation_id: str, transfer_id: str) -> dict:
    record = get_transfer(user, conversation_id, transfer_id)
    if record["state"] not in {"failed", "cancelled"}:
        return public(record)
    _path(user, conversation_id, transfer_id).with_suffix(".cancel").unlink(missing_ok=True)
    record = _set(user, record, state="queued", error=None, error_code=None, bytes=0, retryable=None)
    dispatch(transfer_id, user, conversation_id)
    return public(record)


def run_import(transfer_id: str, user: str, conversation_id: str) -> None:
    # One event loop for the whole import: the Hermes database engine is pooled and cannot be reused across loops.
    asyncio.run(_import(transfer_id, user, conversation_id))


async def _import(transfer_id: str, user: str, conversation_id: str) -> None:
    record = get_transfer(user, conversation_id, transfer_id)
    if record["state"] != "queued":
        return
    folder = attachment_folder(user, conversation_id)
    temporary = folder / f"cloud_{transfer_id}{Path(record['filename']).suffix.lower()}"
    try:
        record = await _aset(user, record, state="connecting", attempts=record.get("attempts", 0) + 1)
        info = await metadata(user, record["provider"], record["file_id"])
        record = await _aset(user, record, state="fetching_metadata", size=info["size"])
        downloaded = await _call(user, record["provider"], "GOOGLEDRIVE_DOWNLOAD_FILE", {"fileId": record["file_id"]})
        link = (downloaded.get("downloaded_file_content") or {}).get("s3url")
        if not link:
            raise CloudError("provider_error", "Google Drive did not return the file.", 502)
        safe = await asyncio.to_thread(safe_download_url, link)
        record = await _aset(user, record, state="downloading", bytes=0)
        size = await asyncio.to_thread(_stream, user, record, safe, temporary)
        record = await _aset(user, record, state="validating", bytes=size)
        attachment = await finalize(user, conversation_id, temporary, record["filename"], record["kind"],
                                    record["mime_type"], size,
                                    {"cloud": {"provider": record["provider"], "file_id": record["file_id"],
                                               "version": record["version"], "checksum": record["checksum"],
                                               "modified": record["modified"]}})
        await _aset(user, record, state="completed", attachment_id=attachment["id"], bytes=size, size=size)
    except CloudError as exc:
        temporary.unlink(missing_ok=True)
        if exc.code == "cancelled":
            await _aset(user, record, state="cancelled", error=None, error_code=None)
        else:
            await _aset(user, record, state="failed", error=exc.message, error_code=exc.code,
                        retryable=exc.code in {"network", "rate_limited", "provider_error", "provider_unavailable"})
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        log.warning("cloud import failed: %s", type(exc).__name__)
        await _aset(user, record, state="failed", error="The file could not be imported.", error_code="import_failed", retryable=True)


def _stream(user: str, record: dict, url: str, target: Path) -> int:
    """Stream to disk with bounded memory, a hard size limit, cancel checks and retry on network errors."""
    limit = MAX_BYTES[record["kind"]]
    last = time.monotonic(); started = last
    for attempt in range(3):
        offset = target.stat().st_size if target.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            with httpx.Client(timeout=httpx.Timeout(30, read=60), follow_redirects=False) as client:
                with client.stream("GET", url, headers=headers) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        raise CloudError("unsafe_link", "The download link was refused.", 502)
                    if offset and response.status_code == 200:
                        offset = 0; target.unlink(missing_ok=True)
                    elif response.status_code not in (200, 206):
                        raise CloudError("network" if response.status_code >= 500 else "file_not_found",
                                         "The file could not be downloaded.", 502)
                    total = offset
                    with open(target, "ab" if offset else "wb") as out:
                        for chunk in response.iter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > limit:
                                raise CloudError("file_too_large", "The file is larger than the allowed size.", 413)
                            out.write(chunk)
                            now = time.monotonic()
                            if now - last >= 1.0:
                                if _cancelled(user, record): raise CloudError("cancelled", "Cancelled.")
                                last = now
                                _set(user, record, bytes=total, speed=int(total / max(now - started, 0.001)))
                    if total == 0:
                        raise CloudError("corrupt_file", "The downloaded file is empty.", 422)
                    expected = record.get("size")
                    if expected and total != int(expected):
                        raise CloudError("network", "The download was incomplete.", 502)
                    return total
        except (httpx.TransportError, httpx.TimeoutException):
            if attempt == 2:
                raise CloudError("network", "The connection was interrupted.", 502) from None
            time.sleep(2 ** attempt)
    raise CloudError("network", "The connection was interrupted.", 502)
