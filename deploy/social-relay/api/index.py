"""Social-media reference fetcher for the editor (runs on Vercel, outside the network that blocks these sites).

POST /api/index  {"url": "https://www.instagram.com/reel/..."}   header x-relay-secret: <RELAY_SECRET>
  Instagram links go through a downloader API (RapidAPI) when RAPIDAPI_KEY is set: Instagram asks datacenter IPs to log in, so yt-dlp
  alone needs cookies that expire. yt-dlp stays as the fallback and for every other site.
  -> the video file itself (progressive mp4, <= 80 MB, <= 180 s), streamed; metadata in x-* response headers.
GET  /api/index -> {"ok": true, "yt_dlp": "<version>"}

The secret is required, only a fixed list of hosts is allowed, and nothing is stored: the file lives in /tmp for the length of
one request. Optional environment: YTDLP_COOKIES_B64 (base64 Netscape cookies for networks that need a login), YTDLP_PROXY, and for Instagram
RAPIDAPI_KEY (+ RAPIDAPI_HOST, RAPIDAPI_PATH, RAPIDAPI_URL_PARAM when the provider's endpoint differs from the defaults). The key never leaves Vercel.
"""
from __future__ import annotations

import base64
import hmac
import os
import shutil
import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

HOSTS = {"instagram.com", "youtube.com", "youtu.be", "tiktok.com", "vimeo.com", "x.com", "twitter.com", "facebook.com", "fb.watch"}
MAX_BYTES = 80 * 1024 * 1024
MAX_SECONDS = 180
CHUNK = 1024 * 1024

RAPIDAPI_HOST = "instagram-post-reels-stories-downloader-api.p.rapidapi.com"
RAPIDAPI_PATH = "/instagram/"
_IMAGE_KEYS = ("thumb", "image", "cover", "poster", "profile", "avatar", "display", "preview", "pic")
_VIDEO_KEYS = ("video_url", "download_url", "video", "downloadurl", "download", "url", "link", "src", "media")

app = FastAPI(title="editor social relay", docs_url=None, redoc_url=None, openapi_url=None)


class Fetch(BaseModel):
    url: str


def _allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return parts.scheme == "https" and not parts.username and not parts.password and any(host == h or host.endswith("." + h) for h in HOSTS)


def _authorized(supplied: str | None) -> bool:
    expected = os.environ.get("RELAY_SECRET", "")
    return len(expected) >= 32 and isinstance(supplied, str) and hmac.compare_digest(supplied.encode(), expected.encode())


def _instagram(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return host == "instagram.com" or host.endswith(".instagram.com")


def _find_video_url(data) -> str | None:
    """The media URL in a downloader API's JSON, whatever its exact shape: walk it and take the best video-looking https link
    (keys like video_url / download_url, ``.mp4``), never a thumbnail or profile picture."""
    found: list[tuple[int, str]] = []

    def visit(value, key: str = "", video_context: bool = False):
        if isinstance(value, dict):
            kind = str(value.get("type") or value.get("media_type") or value.get("mime_type") or "").lower()
            is_video = video_context or "video" in kind or value.get("is_video") is True
            for k, v in value.items():
                visit(v, str(k).lower(), is_video)
        elif isinstance(value, list):
            for item in value:
                visit(item, key, video_context)
        elif isinstance(value, str) and value.startswith("https://"):
            lowered = value.lower().split("?")[0]
            if any(word in key for word in _IMAGE_KEYS) or lowered.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic")):
                return
            score = 0
            if ".mp4" in lowered or ".mov" in lowered or ".m4v" in lowered:
                score += 4
            if "video" in key:
                score += 3
            if any(word == key or key.endswith(word) for word in _VIDEO_KEYS):
                score += 1
            if video_context:
                score += 2
            if score >= 3:
                found.append((score, value))

    visit(data)
    return max(found, key=lambda item: item[0])[1] if found else None


def _rapid_call(url: str) -> dict:
    host = os.environ.get("RAPIDAPI_HOST") or RAPIDAPI_HOST
    path = os.environ.get("RAPIDAPI_PATH") or RAPIDAPI_PATH
    param = os.environ.get("RAPIDAPI_URL_PARAM") or "url"
    request = urllib.request.Request(f"https://{host}{path}?{urllib.parse.urlencode({param: url})}",
                                     headers={"x-rapidapi-key": os.environ["RAPIDAPI_KEY"], "x-rapidapi-host": host, "accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read(2_000_000).decode("utf-8", "replace"))


def _rapid_download(url: str, work: Path) -> Path | None:
    """Instagram through the downloader API: ask for the media link, then fetch the file (<= MAX_BYTES). None when it cannot."""
    if not os.environ.get("RAPIDAPI_KEY"):
        return None
    try:
        media = _find_video_url(_rapid_call(url))
        if not media:
            return None
        target = work / "video.mp4"
        size = 0
        with urllib.request.urlopen(urllib.request.Request(media, headers={"user-agent": "Mozilla/5.0"}), timeout=40) as response, open(target, "wb") as out:
            while chunk := response.read(CHUNK):
                size += len(chunk)
                if size > MAX_BYTES:
                    return None
                out.write(chunk)
        return target if size > 2000 else None
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


@app.get("/api/index")
@app.get("/api")
@app.get("/")
def health():
    import yt_dlp
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__, "rapidapi": bool(os.environ.get("RAPIDAPI_KEY"))}


@app.post("/api/index")
@app.post("/api")
@app.post("/")
def fetch(body: Fetch, x_relay_secret: str | None = Header(default=None)):
    if not _authorized(x_relay_secret):
        raise HTTPException(401, "unauthorized")
    if not _allowed(body.url):
        raise HTTPException(403, "host_not_allowed")
    work = Path(tempfile.mkdtemp(prefix="relay-", dir="/tmp"))
    info: dict = {}
    path = _rapid_download(body.url, work) if _instagram(body.url) else None
    if path is not None:
        info = {"extractor_key": "rapidapi"}
    else:
        import yt_dlp
        options = {"outtmpl": str(work / "video.%(ext)s"), "quiet": True, "no_warnings": True, "noplaylist": True, "max_filesize": MAX_BYTES,
                   "format": "best[ext=mp4][height<=720]/best[height<=720]/best", "socket_timeout": 25, "retries": 2,
                   "match_filter": yt_dlp.utils.match_filter_func(f"duration <=? {MAX_SECONDS}"), "cachedir": False}
        if os.environ.get("YTDLP_PROXY"):
            options["proxy"] = os.environ["YTDLP_PROXY"]
        cookies = os.environ.get("YTDLP_COOKIES_B64", "")
        if cookies:
            (work / "cookies.txt").write_bytes(base64.b64decode(cookies))
            options["cookiefile"] = str(work / "cookies.txt")
        try:
            with yt_dlp.YoutubeDL(options) as client:
                info = client.extract_info(body.url, download=True) or {}
        except Exception as exc:
            shutil.rmtree(work, ignore_errors=True)
            return JSONResponse({"error": "download_failed", "message": str(exc)[:500]}, status_code=502)
        files = sorted(p for p in work.glob("video.*") if p.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv", ".m4v"})
        if not files:
            shutil.rmtree(work, ignore_errors=True)
            return JSONResponse({"error": "no_file", "message": "nothing was downloaded (too long, too large, or not a video)"}, status_code=502)
        path = files[0]
    size = path.stat().st_size

    def stream():
        try:
            with open(path, "rb") as handle:
                while chunk := handle.read(CHUNK):
                    yield chunk
        finally:
            shutil.rmtree(work, ignore_errors=True)

    media = {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime", "mkv": "video/x-matroska", "m4v": "video/mp4"}
    headers = {"content-length": str(size), "x-source-title": urllib.parse.quote(str(info.get("title") or "")[:200]),
               "x-source-duration": str(info.get("duration") or ""), "x-source-extractor": str(info.get("extractor_key") or ""),
               "x-source-ext": path.suffix.lstrip(".")}
    return StreamingResponse(stream(), media_type=media.get(path.suffix.lstrip(".").lower(), "application/octet-stream"), headers=headers)
