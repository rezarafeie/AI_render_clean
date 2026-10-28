"""An Instagram account connected through Composio, shown to Hermes as an account (read-only).

The person authorizes on Composio's page; no Meta developer app is involved. The account is listed with its public profile and counts, read with the
reviewed read-only tools only. Publishing and messaging are not part of this connection (see docs/hermes-integration.md)."""
import time

from fastapi import HTTPException

from hermes.config import settings
from hermes.services import composio_read as read, composio_sessions as sessions

VIRTUAL_ID = "composio-instagram"
PROFILE_TOOL, MEDIA_TOOL = "INSTAGRAM_GET_USER_INFO", "INSTAGRAM_GET_IG_USER_MEDIA"
_cache: dict[str, tuple[float, dict | None]] = {}
TTL = 90.0


def _find(value, key):
    """The first value stored under `key` anywhere in the (cleaned) tool result."""
    if isinstance(value, dict):
        if key in value and not isinstance(value[key], (dict, list)):
            return value[key]
        for child in value.values():
            found = _find(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find(child, key)
            if found is not None:
                return found
    return None


async def profile(user_id: str) -> dict | None:
    result = await read.execute(user_id, "instagram", PROFILE_TOOL, {"ig_user_id": "me"})
    data = result.get("data")
    return {"username": _find(data, "username"), "followers_count": _find(data, "followers_count"), "follows_count": _find(data, "follows_count"),
            "media_count": _find(data, "media_count"), "ig_user_id": _find(data, "id") or _find(data, "user_id")}


async def account(user_id: str, fresh: bool = False) -> dict | None:
    """The Composio Instagram connection of this user as an account row, or None (not configured, not enabled, not connected)."""
    now = time.monotonic()
    hit = None if fresh else _cache.get(user_id)
    if hit and now - hit[0] < TTL:
        return hit[1]
    row = None
    try:
        status = await sessions.status(user_id)
        if status["configured"] and status["enabled"] and "instagram" in status["applications"]:
            apps = (await sessions.connections(user_id))["applications"]
            if any(item["application"] == "instagram" and item["connected"] for item in apps):
                info = {}
                if PROFILE_TOOL in read.permitted_slugs():
                    try:
                        info = await profile(user_id) or {}
                    except HTTPException:
                        info = {}
                row = {"id": VIRTUAL_ID, "user_id": user_id, "source": "composio", "username": info.get("username") or "instagram",
                       "ig_user_id": info.get("ig_user_id"), "followers": info.get("followers_count"), "follows": info.get("follows_count"),
                       "media_count": info.get("media_count"), "token_expires_at": None}
    except HTTPException:
        row = None
    _cache[user_id] = (now, row)
    return row


def forget(user_id: str) -> None:
    _cache.pop(user_id, None)


async def insights(user_id: str) -> dict:
    row = await account(user_id)
    if not row:
        raise HTTPException(404, detail={"code": "ACCOUNT_NOT_FOUND"})
    return {"account_id": VIRTUAL_ID, "followers": row["followers"], "follows": row["follows"], "media_count": row["media_count"], "source": "composio"}


async def posts(user_id: str, strict: bool = False) -> list:
    if MEDIA_TOOL not in read.permitted_slugs():
        return []
    try:
        result = await read.execute(user_id, "instagram", MEDIA_TOOL, {"ig_user_id": "me", "limit": 25}, max_chars=400_000)   # a page of posts is large; only a few fields are kept below
    except HTTPException:                                   # the page still works with the profile numbers
        if strict:
            raise
        return []
    items = (result.get("data") or {}).get("data") if isinstance(result.get("data"), dict) else None
    items = items if isinstance(items, list) else _find_list(result.get("data"))
    return [{"id": str(m.get("id")), "ig_post_id": str(m.get("id")), "likes": m.get("like_count"), "comments": m.get("comments_count"),
             "caption": (m.get("caption") or "")[:200], "permalink": m.get("permalink"), "timestamp": m.get("timestamp"), "source": "composio"}
            for m in (items or []) if isinstance(m, dict)]


def _find_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for child in value.values():
            found = _find_list(child)
            if found is not None:
                return found
    return None
