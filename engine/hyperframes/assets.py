"""Pinned third-party runtime assets for HyperFrames compositions.

A composition used to load GSAP from a CDN at render time. A failed script load surfaced only
after every frame had been encoded (a real job lost two minutes at frame 1347/1347). GSAP is
now fetched once from the npm registry, integrity-checked against the registry's own sha512,
cached on disk, and copied into each project so rendering never depends on the network.
It is deliberately not committed to the repository (GreenSock's licence).
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import tarfile
import threading
from pathlib import Path

GSAP_VERSION = "3.14.2"
_REGISTRY = "https://registry.npmjs.org/gsap"
_lock = threading.Lock()


class AssetError(RuntimeError):
    pass


def cache_dir() -> Path:
    from app.config import settings
    return Path(settings.JOBS_DIR).expanduser() / ".cache" / "hyperframes"


def _download(url: str, timeout: float = 30.0) -> bytes:
    import httpx
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        return response.content
    except Exception as exc:
        raise AssetError(f"Could not download {url.rsplit('/', 1)[-1]}: {type(exc).__name__}") from exc


def verify_integrity(data: bytes, integrity: str) -> bool:
    """`integrity` is an SRI string such as ``sha512-<base64>``."""
    algorithm, _, expected = integrity.partition("-")
    if algorithm not in {"sha512", "sha384", "sha256"} or not expected:
        return False
    digest = hashlib.new(algorithm, data).digest()
    return base64.b64encode(digest).decode() == expected


def extract_member(tarball: bytes, member: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
        item = archive.extractfile(member)
        if item is None:
            raise AssetError(f"{member} missing from the package")
        return item.read()


def ensure_gsap(directory: Path | None = None) -> Path:
    """Return a local ``gsap.min.js`` (downloading and verifying it on first use)."""
    shipped = os.environ.get("HYPERFRAMES_GSAP")          # a cloud worker has no network: the server ships the verified copy with the job
    if shipped and Path(shipped).is_file() and Path(shipped).stat().st_size > 50_000:
        return Path(shipped)
    target = (directory or cache_dir()) / f"gsap-{GSAP_VERSION}.min.js"
    with _lock:
        if target.is_file() and target.stat().st_size > 50_000:
            return target
        import json
        meta = json.loads(_download(f"{_REGISTRY}/{GSAP_VERSION}"))
        dist = meta.get("dist") or {}
        tarball = _download(dist.get("tarball") or f"{_REGISTRY}/-/gsap-{GSAP_VERSION}.tgz", timeout=60.0)
        if not verify_integrity(tarball, dist.get("integrity", "")):
            raise AssetError("GSAP package failed its integrity check")
        script = extract_member(tarball, "package/dist/gsap.min.js")
        if f"GSAP {GSAP_VERSION}" not in script[:400].decode("utf-8", "ignore"):
            raise AssetError("Unexpected GSAP build")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(script)
        temporary.replace(target)
        return target
