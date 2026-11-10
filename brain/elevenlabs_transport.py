"""Shared routing helpers for direct or Vercel-relayed ElevenLabs calls."""
from __future__ import annotations

import os

DIRECT_BASE_URL = "https://api.elevenlabs.io"


def base_url() -> str:
    """Require the configured HTTPS relay; never bypass it on failures."""
    proxy = os.environ.get("ELEVENLABS_PROXY_URL", "").strip().rstrip("/")
    if not proxy or proxy == DIRECT_BASE_URL or not proxy.startswith("https://"):
        raise RuntimeError("ELEVENLABS_PROXY_URL must configure the HTTPS Vercel relay")
    return proxy


def url(path: str) -> str:
    return f"{base_url()}/{path.lstrip('/')}"


def api_key() -> str:
    """The server-side ElevenLabs key ("" when not configured). The key lives here, with the relay's address, and never leaves the server."""
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def relay_ready() -> bool:
    return bool(api_key() and os.environ.get("ELEVENLABS_PROXY_URL", "").strip().startswith("https://"))


def _origin() -> str:
    base = base_url()
    return base[: -len("/api/elevenlabs")] if base.endswith("/api/elevenlabs") else base.rsplit("/api/", 1)[0] if "/api/" in base else base


def music_url() -> str:
    """The relay's separate music function (a sibling of the shared speech route): <relay origin>/api/elevenlabs-music."""
    return f"{_origin()}/api/elevenlabs-music"


def jamendo_url() -> str:
    """The relay's Jamendo function (search and audio download; the server cannot reach jamendo.com directly): <relay origin>/api/jamendo."""
    return f"{_origin()}/api/jamendo"


def clone_url() -> str:
    """The relay's separate voice-cloning function (a sibling of the shared speech route): <relay origin>/api/elevenlabs-clone."""
    base = base_url()
    root = base[: -len("/api/elevenlabs")] if base.endswith("/api/elevenlabs") else base.rsplit("/api/", 1)[0] if "/api/" in base else base
    return f"{root}/api/elevenlabs-clone"
