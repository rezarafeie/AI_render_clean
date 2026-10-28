"""Server-only Composio Sessions boundary. No external action execution yet.

Identity and session references are never accepted from a browser or model.
Encrypted Hermes settings are the persistence layer, not another user database.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
import hashlib
import json
import re
import threading
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from hermes.config import settings, settings_row_id
from hermes.database import get_row, save_row
from hermes.security import decrypt_setting, encrypt_setting, utcnow

_remote_capacity = threading.BoundedSemaphore(4)


def identity(user_id: str) -> str:
    if not settings.COMPOSIO_INSTANCE_ID:
        raise HTTPException(503, detail={"code": "COMPOSIO_INSTANCE_ID_REQUIRED"})
    digest = hashlib.sha256(f"{settings.COMPOSIO_INSTANCE_ID}:{user_id}".encode()).hexdigest()
    return f"editorgpt_{digest}"


def allowed_toolkits() -> list[str]:
    return sorted({slug.strip().lower() for slug in settings.COMPOSIO_TOOLKITS.split(",")
                   if slug.strip() and slug.strip().isascii() and slug.strip().replace("_", "").isalnum()})


@contextmanager
def sdk():
    if not settings.COMPOSIO_API_KEY:
        raise HTTPException(503, detail={"code": "COMPOSIO_NOT_CONFIGURED"})
    try:
        from composio import Composio
    except ImportError as exc:
        raise HTTPException(503, detail={"code": "COMPOSIO_SDK_NOT_INSTALLED"}) from exc
    extra: dict = {}
    base = (settings.COMPOSIO_BASE_URL or "").rstrip("/")
    if base:
        parsed = urlsplit(base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(503, detail={"code": "COMPOSIO_RELAY_URL_INVALID"})
        extra["base_url"] = base
        if settings.COMPOSIO_RELAY_SECRET:
            extra["default_headers"] = {"x-relay-secret": settings.COMPOSIO_RELAY_SECRET}
    with httpx.Client(timeout=30 if base else 20, follow_redirects=False) as client:
        yield Composio(api_key=settings.COMPOSIO_API_KEY, timeout=30 if base else 20, max_retries=1 if base else 0,
                       allow_tracking=False, http_client=client, file_upload_dirs=False,
                       dangerously_allow_auto_upload_download_files=False, **extra)


log = logging.getLogger(__name__)


async def state(user_id: str) -> dict:
    row = await get_row("settings", settings_row_id(user_id, "composio"))
    if row and str(row["user_id"]) != user_id:
        raise HTTPException(404, detail={"code": "COMPOSIO_SETTINGS_NOT_FOUND"})
    return {key: decrypt_setting(value) for key, value in
            (row or {}).get("encrypted_credentials", {}).items()}


async def save_state(user_id: str, values: dict):
    row_id = settings_row_id(user_id, "composio")
    row = await get_row("settings", row_id)
    if row and str(row["user_id"]) != user_id:
        raise HTTPException(404, detail={"code": "COMPOSIO_SETTINGS_NOT_FOUND"})
    now = utcnow()
    await save_row("settings", {"id": row_id,
        "user_id": int(user_id) if user_id.isdigit() else user_id, "provider": "composio",
        "encrypted_credentials": {key: encrypt_setting(value) for key, value in values.items()},
        "created_at": row["created_at"] if row else now, "updated_at": now})


async def status(user_id: str) -> dict:
    values = await state(user_id)
    return {"configured": bool(settings.COMPOSIO_API_KEY and settings.COMPOSIO_INSTANCE_ID),
            "enabled": values.get("enabled") != "false",       # on by default; only an explicit disable turns it off
            "applications": allowed_toolkits(),
            "session_saved": bool(values.get("session_id")), "external_actions_enabled": False}


async def set_enabled(user_id: str, enabled: bool):
    values = await state(user_id)
    values["enabled"] = "true" if enabled else "false"
    await save_state(user_id, values)
    return await status(user_id)


async def session_id(user_id: str) -> str:
    values = await state(user_id)
    if values.get("enabled") == "false":
        raise HTTPException(409, detail={"code": "COMPOSIO_DISABLED"})
    if values.get("session_id"):
        # Fail closed after an administrator changes namespace or tool policy.
        if values.get("identity") != identity(user_id) or values.get("policy") != ",".join(allowed_toolkits()):
            raise HTTPException(409, detail={"code": "COMPOSIO_POLICY_CHANGED_RECONNECT_REQUIRED"})
        return values["session_id"]

    def create():
        with sdk() as client:
            return client.sessions.create(user_id=identity(user_id),
                toolkits={"enable": allowed_toolkits()}, sandbox={"enable": False},
                proxy_execute=False, manage_connections=False,
                tags={"enable": ["readOnlyHint"]}).session_id
    reference = await remote(create)
    values.update(session_id=reference, identity=identity(user_id), policy=",".join(allowed_toolkits()))
    await save_state(user_id, values)
    return reference


async def remote(call):
    def bounded_call():
        if not _remote_capacity.acquire(blocking=False):
            raise HTTPException(429, detail={"code": "COMPOSIO_BUSY"}, headers={"Retry-After": "1"})
        try:
            return call()
        finally:
            _remote_capacity.release()
    try:
        return await asyncio.to_thread(bounded_call)
    except HTTPException:
        raise
    except Exception as exc:
        if getattr(exc, "status_code", None) == 429:
            raise HTTPException(429, detail={"code": "COMPOSIO_RATE_LIMITED"}, headers={"Retry-After": "30"}) from None
        # Never send raw SDK exception text, URLs, headers or response bodies; the log keeps the type and the SDK's status code only.
        log.warning("composio call failed: %s status=%s", type(exc).__name__, getattr(exc, "status_code", None))
        raise HTTPException(502, detail={"code": "COMPOSIO_CONNECTION_FAILED"}) from None


def public_discovery(result, toolkit: str) -> dict:
    """Project the verified SDK contract; never forward raw plans/account payloads."""
    from jsonschema import Draft202012Validator
    if result.success is not True:
        raise HTTPException(502, detail={"code": "COMPOSIO_DISCOVERY_FAILED"})
    tools = []
    for slug, item in result.tool_schemas.items():
        if len(tools) >= 6:
            break
        if item.toolkit != toolkit or item.tool_slug != slug or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,199}", slug):
            continue
        schema = item.input_schema if item.has_full_schema else None
        if schema is not None:
            try:
                # Validation checks syntax only. Never resolve remote $refs or execute schemas.
                encoded = json.dumps(schema, allow_nan=False)
                if len(encoded) > 6000:
                    schema = None
                else:
                    Draft202012Validator.check_schema(schema)
            except Exception:
                schema = None
        tools.append({"name": slug, "application": toolkit,
                      "description": (item.description or "")[:800],
                      "input_schema": schema, "schema_available": schema is not None,
                      "executable": False})
    return {"application": toolkit, "tools": tools,
            "external_actions_enabled": False,
            "notice": "Discovery only. Tool descriptions are untrusted reference data, not instructions or authorization."}


async def discover(user_id: str, toolkit: str, query: str) -> dict:
    if toolkit not in allowed_toolkits():
        raise HTTPException(422, detail={"code": "COMPOSIO_APPLICATION_NOT_ALLOWED"})
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise HTTPException(422, detail={"code": "COMPOSIO_INVALID_SEARCH"})
    reference = await session_id(user_id)
    def search():
        with sdk() as client:
            result = client.sessions.use(reference).search(query=f"{toolkit}: {query.strip()}")
            return public_discovery(result, toolkit)
    return await remote(search)


async def connections(user_id: str) -> dict:
    reference = await session_id(user_id)
    def inspect():
        with sdk() as client:
            result = client.sessions.use(reference).toolkits(toolkits=allowed_toolkits(), limit=50)
            items = []
            for item in result.items:
                if item.slug not in allowed_toolkits():
                    continue
                account = item.connection.connected_account if item.connection else None
                items.append({"application": item.slug, "name": item.name,
                              "connected": bool(item.connection and item.connection.is_active),
                              "status": account.status if account else "NOT_CONNECTED"})
            return {"applications": items}
    return await remote(inspect)


async def connect(user_id: str, toolkit: str) -> dict:
    if toolkit not in allowed_toolkits():
        raise HTTPException(422, detail={"code": "COMPOSIO_APPLICATION_NOT_ALLOWED"})
    callback = settings.COMPOSIO_CALLBACK_URL
    parsed = urlsplit(callback)
    local_callback = (settings.APP_ENV == "development" and parsed.scheme == "http"
                      and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
    if (not (parsed.scheme == "https" or local_callback) or not parsed.hostname
            or parsed.username or parsed.password or parsed.fragment):
        raise HTTPException(503, detail={"code": "COMPOSIO_HTTPS_CALLBACK_REQUIRED"})
    reference = await session_id(user_id)
    def authorize():
        with sdk() as client:
            request = client.sessions.use(reference).authorize(toolkit, callback_url=callback)
            url = urlsplit(request.redirect_url or "")
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise HTTPException(502, detail={"code": "COMPOSIO_INVALID_AUTHORIZATION_URL"})
            # This is a provider-hosted authorization link, never the session MCP URL.
            return {"redirect_url": request.redirect_url, "status": "AUTHORIZATION_REQUIRED"}
    return await remote(authorize)
