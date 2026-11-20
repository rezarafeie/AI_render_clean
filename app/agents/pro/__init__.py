"""EditorGPT Pro: a Claude Agent SDK session per request, in its own container (spec: docs/PRO_AGENT_PLAN.md).

Shared by the app (proxy, internal tool endpoints) and the agent worker (daemon, runner):
    token(run_id, user, cid) / verify(token)    a short-lived HMAC run token; the only credential the agent container ever holds
    RUNS                                        the shared volume with every run's working folder (/runs/<run_id>/work)
No provider key, database URL or storage secret is needed on the agent side.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

RUNS = Path(os.environ.get("PRO_RUNS_DIR", "/runs"))
MODEL = os.environ.get("PRO_MODEL", "claude-opus-5-5")
BUDGET_CREDITS = int(os.environ.get("PRO_BUDGET_CREDITS", "3000000"))          # no longer a ceiling (a run may use the person's credit; see agent_proxy.messages); kept for old readers
TOKEN_HOURS = 6
ALLOWED_MODELS = ("claude-opus-", "claude-sonnet-", "claude-haiku-")


def _secret() -> bytes:
    value = os.environ.get("PRO_WORKER_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("PRO_WORKER_SECRET is not configured")
    return hashlib.sha256(b"editorgpt-pro-token:" + value.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def token(run_id: str, user: str, cid: str, hours: float = TOKEN_HOURS) -> str:
    body = _b64(json.dumps({"run": run_id, "user": str(user), "cid": cid, "exp": int(time.time() + hours * 3600)}, separators=(",", ":")).encode())
    return body + "." + _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())


def verify(value: str) -> dict:
    """The token's claims, or ValueError (bad signature, expired, malformed)."""
    try:
        body, sig = value.strip().split(".", 1)
        good = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(good, sig):
            raise ValueError("bad signature")
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("malformed token") from exc
    if int(claims.get("exp", 0)) < time.time():
        raise ValueError("expired")
    return claims


def workdir(key: str) -> Path:
    """The working folder of a chat (one per conversation, so a follow-up message continues the same project and agent session)."""
    if not key.isalnum():
        raise ValueError("bad key")
    return RUNS / key / "work"


def inside(key: str, relative: str) -> Path:
    """A path of the chat's working folder given by the agent (relative or absolute), refused when it leaves the folder."""
    root = workdir(key).resolve()
    path = Path(relative)
    path = (path if path.is_absolute() else root / path).resolve()
    if path != root and root not in path.parents:
        raise ValueError("the path is outside this run's folder")
    return path
