"""Where music comes from besides the studio's own library: generation (ElevenLabs Eleven Music, Stability Stable Audio) and discovery (Jamendo, Epidemic Sound).

Each integration follows the provider's own published API (checked against the official references, see each class). Capabilities differ and are never assumed to match:

  ElevenLabs   POST /v1/music           prompt + music_length_ms (3000..600000), force_instrumental, model_id music_v1|music_v2|music_v2_5; audio bytes are the response.
                                        Goes through the existing Vercel relay (the server cannot reach the provider's own host directly); the key never leaves the server.
  Stability    POST /v2beta/audio/stable-audio-2/text-to-audio   multipart: prompt, duration (1..190 s), model stable-audio-2|stable-audio-2.5, steps, seed, output_format.
                                        Synchronous, 8 credits (2.5) or 17 + 0.06*steps (2.0); one credit is $0.01.
  Jamendo      GET /v3.0/tracks         client_id, search/tags, vocalinstrumental, speed, durationbetween, include=licenses+musicinfo. Free catalogue under Creative Commons licences.
  Epidemic     GET /v0/tracks/search + /v0/tracks/{id}/download   bearer API key + x-partner-user-id. The free plan has no commercial licence; a paid partner plan is required to publish.

Nothing here runs unless its credentials are configured; a missing key is reported, never silently replaced by something else. Results are cached by content-addressed
fingerprint in the job volume (one generation per identical request, concurrent identical requests wait for the first), costs are appended to a ledger, and a daily cap on
paid generations protects the account's quota. Rights are explicit: a track is only offered for rendering when `rights()` says the application and the user may use it.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

import httpx

log = logging.getLogger(__name__)

GENERATE_TIMEOUT = httpx.Timeout(290.0, connect=20.0)
SEARCH_TIMEOUT = httpx.Timeout(25.0, connect=10.0)
MAX_AUDIO_BYTES = 100_000_000
CREDIT_USD = 0.01                       # Stability: "1 credit = $0.01" (official llms.txt)
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class MusicError(RuntimeError):
    """A music request failed for a reason the caller can act on. `code` is stable: no_credentials, rate_limited, quota, provider_error, invalid, rights, daily_cap, empty."""

    def __init__(self, code: str, message: str, *, retryable: bool = False, retry_after: float | None = None):
        super().__init__(message)
        self.code, self.retryable, self.retry_after = code, retryable, retry_after


# ── store: cache, locks, costs ───────────────────────────────────────────────────────────────────────────────────
def store_root() -> Path:
    configured = os.environ.get("MUSIC_STORE", "").strip()
    if configured:
        root = Path(configured)
    else:
        from app.config import settings
        root = Path(settings.JOBS_DIR) / "_music"
    root.mkdir(parents=True, exist_ok=True)
    return root


def fingerprint(provider: str, params: dict) -> str:
    return hashlib.sha256(json.dumps({"p": provider, **params}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


@contextlib.contextmanager
def single_flight(key: str) -> Iterator[None]:
    """One identical request at a time, across threads and processes: a second caller waits and then finds the first one's result in the cache."""
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.Lock())
    with lock:
        handle = None
        try:
            import fcntl
            folder = store_root() / ".locks"
            folder.mkdir(exist_ok=True)
            handle = open(folder / f"{key}.lock", "w")
            fcntl.flock(handle, fcntl.LOCK_EX)
        except (ImportError, OSError):
            handle = None
        try:
            yield
        finally:
            if handle:
                handle.close()


def cached(key: str) -> dict | None:
    meta = store_root() / key / "meta.json"
    try:
        data = json.loads(meta.read_text())
        if Path(data["path"]).is_file():
            return data
    except (OSError, ValueError, KeyError):
        pass
    return None


def remember(key: str, audio: bytes | Path, ext: str, meta: dict) -> dict:
    folder = store_root() / key
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"audio.{ext}"
    if isinstance(audio, Path):
        target.write_bytes(audio.read_bytes())
    else:
        temporary = folder / f".{uuid.uuid4().hex}.part"
        temporary.write_bytes(audio)
        temporary.replace(target)
    data = {**meta, "key": key, "path": str(target), "bytes": target.stat().st_size, "created": time.time()}
    (folder / "meta.json").write_text(json.dumps(data, ensure_ascii=False))
    return data


def record_cost(entry: dict) -> None:
    line = json.dumps({"ts": time.time(), **entry}, ensure_ascii=False)
    with _LOCKS_GUARD, (store_root() / "costs.jsonl").open("a") as handle:
        handle.write(line + "\n")


def generations_today(provider: str | None = None) -> int:
    try:
        lines = (store_root() / "costs.jsonl").read_text().splitlines()
    except OSError:
        return 0
    start = time.time() - 86400
    count = 0
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("kind") == "generation" and row.get("ts", 0) >= start and (provider is None or row.get("provider") == provider):
            count += 1
    return count


def daily_cap() -> int:
    try:
        return max(0, int(os.environ.get("MUSIC_DAILY_GENERATIONS", "30")))
    except ValueError:
        return 30


# ── rights ───────────────────────────────────────────────────────────────────────────────────────────────────────
_CC = re.compile(r"creativecommons\.org/licenses/([a-z\-]+)/([\d.]+)", re.I)


def cc_terms(url: str | None) -> dict:
    """What a Creative Commons licence URL permits. Unknown or missing = nothing is assumed."""
    found = _CC.search(url or "")
    if not found:
        return {"code": None, "commercial": False, "derivatives": False, "attribution": True, "share_alike": False}
    parts = set(found.group(1).lower().split("-"))
    return {"code": "cc-" + found.group(1).lower(), "version": found.group(2), "commercial": "nc" not in parts, "derivatives": "nd" not in parts,
            "attribution": "by" in parts, "share_alike": "sa" in parts}


def confirmed_generators() -> set[str]:
    """Providers whose output the operator has confirmed may be used commercially under the plan in use (their terms differ by plan: confirm yours)."""
    raw = os.environ.get("MUSIC_RIGHTS_CONFIRMED", "elevenlabs,stability")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def rights(track: dict) -> dict:
    """May this track go into a rendered video that is published? {"ok": bool, "reason": str}. Library files and the person's own uploads are theirs to use."""
    source = str(track.get("source") or "")
    licence = track.get("license") or {}
    if source in {"upload", "attached", "library", "generated-cache"} and not track.get("provider"):
        return {"ok": True, "reason": "the person's own file or a studio library file"}
    provider = str(track.get("provider") or source).lower()
    if source == "generated":
        if provider in confirmed_generators():
            return {"ok": True, "reason": f"generated with {provider}; commercial use under the account's plan terms (confirmed by the operator)"}
        return {"ok": False, "reason": f"commercial rights for {provider} output are not confirmed (set MUSIC_RIGHTS_CONFIRMED)"}
    if provider == "jamendo":
        if track.get("download_allowed") is False:
            return {"ok": False, "reason": "the artist does not allow downloads of this track"}
        terms = licence.get("terms") or cc_terms(licence.get("url"))
        if not terms.get("commercial") and os.environ.get("MUSIC_NONCOMMERCIAL_USE") != "1":
            return {"ok": False, "reason": f"{terms.get('code') or 'unknown licence'} forbids commercial use"}
        if not terms.get("derivatives"):
            return {"ok": False, "reason": f"{terms.get('code') or 'unknown licence'} forbids derivative works (cutting or mixing into video)"}
        return {"ok": True, "reason": f"{terms.get('code')}: use is allowed with attribution" + (" (share-alike)" if terms.get("share_alike") else "")}
    if provider == "epidemic":
        if os.environ.get("EPIDEMIC_COMMERCIAL") == "1":
            return {"ok": True, "reason": "Epidemic Sound partner plan with a commercial licence (confirmed by the operator)"}
        return {"ok": False, "reason": "the free Epidemic Sound plan has no commercial licence (set EPIDEMIC_COMMERCIAL=1 on a paid plan)"}
    return {"ok": False, "reason": "unknown source: rights cannot be established"}


def ensure_rights(track: dict) -> dict:
    verdict = rights(track)
    if not verdict["ok"]:
        raise MusicError("rights", verdict["reason"])
    return verdict


# ── HTTP with bounded retries ───────────────────────────────────────────────────────────────────────────────────
def _send(call, *, attempts: int = 3, sleep=time.sleep) -> httpx.Response:
    """Run `call()` (returns an httpx.Response). Retries rate limits, 5xx and timeouts with the provider's Retry-After (else a growing wait); anything else fails at once."""
    last: MusicError | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = call()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = MusicError("provider_error", f"the music service could not be reached ({type(exc).__name__})", retryable=True)
        else:
            if response.status_code < 400:
                return response
            retry_after = None
            try:
                retry_after = float(response.headers.get("retry-after", ""))
            except ValueError:
                pass
            body = (response.text or "")[:240]
            if response.status_code == 429:
                last = MusicError("rate_limited", "the music service is rate limiting this account", retryable=True, retry_after=retry_after)
            elif response.status_code >= 500:
                last = MusicError("provider_error", f"the music service failed (HTTP {response.status_code})", retryable=True, retry_after=retry_after)
            elif response.status_code in (401, 402, 403):
                code = "quota" if response.status_code == 402 or "quota" in body.lower() or "credit" in body.lower() else "no_credentials"
                raise MusicError(code, f"the music service refused the request (HTTP {response.status_code}): {body}")
            else:
                raise MusicError("invalid", f"the music service rejected the request (HTTP {response.status_code}): {body}")
        if attempt < attempts:
            sleep(min(60.0, last.retry_after if last and last.retry_after else 5.0 * attempt * attempt))
    raise last or MusicError("provider_error", "the music request failed")


def _audio(response: httpx.Response, what: str) -> tuple[bytes, str]:
    kind = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    data = response.content
    if not data or (not kind.startswith("audio/") and kind not in {"application/octet-stream", "binary/octet-stream"}):
        raise MusicError("provider_error", f"{what} did not return audio ({kind or 'no content type'})")
    if len(data) > MAX_AUDIO_BYTES:
        raise MusicError("provider_error", f"{what} returned an unreasonably large file")
    return data, ("wav" if "wav" in kind else "mp3")


# ── generators ───────────────────────────────────────────────────────────────────────────────────────────────────
class ElevenMusic:
    """Eleven Music (https://elevenlabs.io/docs/api-reference/music/compose): POST /v1/music, the audio is the response body (through the relay's music function)."""
    name, kind = "elevenlabs", "generate"
    MIN_MS, MAX_MS = 3000, 600000
    MODELS = ("music_v1", "music_v2", "music_v2_5")

    def available(self) -> tuple[bool, str]:
        from brain import elevenlabs_transport as transport
        if not transport.api_key():
            return False, "ELEVENLABS_API_KEY is not set"
        if not transport.relay_ready():
            return False, "ELEVENLABS_PROXY_URL (the relay) is not set"
        return True, ""

    def estimate(self, seconds: float) -> dict:
        return {"usd": None, "basis": "ElevenLabs bills music from the plan's credits and does not report a per-request price"}

    def generate(self, prompt: str, seconds: float, *, instrumental: bool = True, model_id: str | None = None, seed: int | None = None,
                 client: httpx.Client | None = None, sleep=time.sleep) -> tuple[bytes, str, dict]:
        ok, why = self.available()
        if not ok:
            raise MusicError("no_credentials", why)
        from brain.elevenlabs_transport import api_key, music_url
        model = model_id or os.environ.get("MUSIC_ELEVEN_MODEL", "music_v1")
        if model not in self.MODELS:
            raise MusicError("invalid", f"unknown Eleven Music model {model!r} (known: {', '.join(self.MODELS)})")
        length = int(round(float(seconds) * 1000))
        if not self.MIN_MS <= length <= self.MAX_MS:
            raise MusicError("invalid", f"Eleven Music makes 3 to 600 seconds per track (asked for {seconds:g})")
        body: dict[str, Any] = {"prompt": prompt[:4000], "music_length_ms": length, "model_id": model, "force_instrumental": bool(instrumental)}
        if seed is not None:
            body["seed"] = int(seed)
        headers = {"xi-api-key": api_key(), "accept": "audio/mpeg"}
        own = client or httpx.Client(timeout=GENERATE_TIMEOUT)
        try:
            response = _send(lambda: own.post(music_url() + "?output_format=mp3_44100_128", headers=headers, json=body), sleep=sleep)
        finally:
            if client is None:
                own.close()
        data, ext = _audio(response, "Eleven Music")
        return data, ext, {"model": model, "song_id": response.headers.get("song-id"), "usd": None, "credits": None}


class StableAudio:
    """Stable Audio 2.x (https://docs.stability.ai/api-reference/stable-audio-2/text-to-audio): multipart POST, `accept: audio/*`, synchronous."""
    name, kind = "stability", "generate"
    MAX_SECONDS = 190
    ENDPOINT = "/v2beta/audio/stable-audio-2/text-to-audio"

    def available(self) -> tuple[bool, str]:
        return (True, "") if os.environ.get("STABILITY_API_KEY", "").strip() else (False, "STABILITY_API_KEY is not set")

    @staticmethod
    def credits(model: str, steps: int) -> float:
        return 8.0 if model == "stable-audio-2.5" else round(17 + 0.06 * steps, 2)          # the formula and the flat rate from the official page

    def estimate(self, seconds: float, model: str = "stable-audio-2.5") -> dict:
        steps = 8 if model == "stable-audio-2.5" else 50
        return {"usd": round(self.credits(model, steps) * CREDIT_USD, 3), "credits": self.credits(model, steps), "basis": "official per-generation credits, $0.01 each"}

    def generate(self, prompt: str, seconds: float, *, model: str | None = None, steps: int | None = None, seed: int | None = None,
                 client: httpx.Client | None = None, sleep=time.sleep) -> tuple[bytes, str, dict]:
        ok, why = self.available()
        if not ok:
            raise MusicError("no_credentials", why)
        model = model or os.environ.get("MUSIC_STABLE_MODEL", "stable-audio-2.5")
        if model not in {"stable-audio-2.5", "stable-audio-2"}:
            raise MusicError("invalid", f"unknown Stable Audio model {model!r}")
        low, high = (4, 8) if model == "stable-audio-2.5" else (30, 100)
        steps = int(steps if steps is not None else (8 if model == "stable-audio-2.5" else 50))
        if not low <= steps <= high:
            raise MusicError("invalid", f"{model} accepts {low}..{high} steps")
        duration = min(float(seconds), float(self.MAX_SECONDS))
        if duration < 1:
            raise MusicError("invalid", "Stable Audio makes at least 1 second")
        fields = {"prompt": (None, prompt[:10000]), "duration": (None, f"{duration:.1f}"), "model": (None, model), "steps": (None, str(steps)), "output_format": (None, "mp3")}
        if seed is not None:
            fields["seed"] = (None, str(int(seed)))
        base = os.environ.get("STABILITY_API_BASE", "https://api.stability.ai").rstrip("/")
        headers = {"authorization": f"Bearer {os.environ['STABILITY_API_KEY'].strip()}", "accept": "audio/*"}
        own = client or httpx.Client(timeout=GENERATE_TIMEOUT)
        try:
            response = _send(lambda: own.post(base + self.ENDPOINT, headers=headers, files=fields), sleep=sleep)
        finally:
            if client is None:
                own.close()
        data, ext = _audio(response, "Stable Audio")
        credits = self.credits(model, steps)
        return data, ext, {"model": model, "steps": steps, "seconds": duration, "credits": credits, "usd": round(credits * CREDIT_USD, 3), "capped": duration < float(seconds)}


GENERATORS = {"elevenlabs": ElevenMusic(), "stability": StableAudio()}


def generate(prompt: str, seconds: float, *, provider: str | None = None, instrumental: bool = True, user: str = "", seed: int | None = None,
             client: httpx.Client | None = None, sleep=time.sleep, order: tuple[str, ...] | None = None) -> dict:
    """One track of generated music as a track dict (local file included), through the cache. Tries the providers in order (ElevenLabs first, then Stability) and
    reports what each one said when none works. Identical requests are generated once; the daily cap on paid generations is enforced before any call."""
    prompt = re.sub(r"\s+", " ", prompt).strip()
    if not prompt:
        raise MusicError("invalid", "a music description is required")
    names = [provider] if provider else list(order or ("elevenlabs", "stability"))
    failures: list[str] = []
    for name in names:
        engine = GENERATORS.get(name)
        if engine is None:
            raise MusicError("invalid", f"unknown music provider {name!r}")
        ok, why = engine.available()
        if not ok:
            failures.append(f"{name}: {why}")
            continue
        key = fingerprint(name, {"prompt": prompt, "seconds": round(float(seconds)), "instrumental": instrumental, "seed": seed})
        with single_flight(key):
            hit = cached(key)
            if hit:
                return _track_from_cache(hit, cache_hit=True)
            if generations_today() >= daily_cap():
                raise MusicError("daily_cap", f"the daily limit of {daily_cap()} generated tracks is reached (MUSIC_DAILY_GENERATIONS)")
            try:
                if name == "elevenlabs":
                    audio, ext, meta = engine.generate(prompt, seconds, instrumental=instrumental, seed=seed, client=client, sleep=sleep)
                else:
                    audio, ext, meta = engine.generate(prompt, seconds, seed=seed, client=client, sleep=sleep)
            except MusicError as exc:
                failures.append(f"{name}: {exc}")
                if exc.code in {"invalid", "daily_cap"}:
                    raise
                continue
            saved = remember(key, audio, ext, {"provider": name, "source": "generated", "prompt": prompt, "seconds": float(seconds), "instrumental": instrumental,
                                               "title": prompt[:60], "model": meta.get("model"), "capped": meta.get("capped", False)})
            record_cost({"kind": "generation", "provider": name, "key": key, "user": user, "usd": meta.get("usd"), "credits": meta.get("credits"), "model": meta.get("model"),
                         "seconds": float(seconds)})
            return _track_from_cache(saved, cache_hit=False, cost={"usd": meta.get("usd"), "credits": meta.get("credits")})
    raise MusicError("no_credentials" if all("not set" in f for f in failures) else "provider_error", "; ".join(failures) or "no music generator is configured")


def _track_from_cache(data: dict, *, cache_hit: bool, cost: dict | None = None) -> dict:
    provider = data.get("provider") or "generated"
    track = {"id": f"generated:{data['key']}", "source": "generated", "provider": provider, "title": data.get("title") or "Generated music", "artist": provider,
             "path": data["path"], "duration_s": data.get("seconds"), "instrumental": data.get("instrumental"), "prompt": data.get("prompt"), "cache_hit": cache_hit,
             "license": {"name": f"{provider} generated music", "url": None, "attribution": None}, "cost": cost or {"usd": 0.0, "note": "cached"}}
    track["rights"] = rights(track)
    return track


# ── discovery ────────────────────────────────────────────────────────────────────────────────────────────────────
class Jamendo:
    """Jamendo catalogue (https://developer.jamendo.com/v3.0/tracks). Streams and downloads are only offered where the artist allows them and the licence permits video use."""
    name, kind = "jamendo", "search"
    SPEED = [(0.0, 0.25, "verylow"), (0.25, 0.45, "low"), (0.45, 0.65, "medium"), (0.65, 0.85, "high"), (0.85, 1.01, "veryhigh")]

    def available(self) -> tuple[bool, str]:
        return (True, "") if os.environ.get("JAMENDO_CLIENT_ID", "").strip() else (False, "JAMENDO_CLIENT_ID is not set")

    def search(self, query: str = "", *, tags: list[str] | None = None, instrumental: bool | None = True, energy: float | None = None,
               min_s: float | None = None, max_s: float | None = None, limit: int = 12, client: httpx.Client | None = None, sleep=time.sleep) -> list[dict]:
        ok, why = self.available()
        if not ok:
            raise MusicError("no_credentials", why)
        url, headers = self._endpoint()
        params: dict[str, Any] = {"client_id": os.environ["JAMENDO_CLIENT_ID"].strip(), "format": "json", "limit": max(1, min(50, limit)),
                                  "include": "licenses+musicinfo", "audioformat": "mp32", "audiodlformat": "mp32"}
        if query.strip():
            params["search"] = query.strip()[:200]
        if tags:
            params["fuzzytags"] = "+".join(re.sub(r"[^\w\-]", "", t) for t in tags[:6] if t)
        if instrumental is True:
            params["vocalinstrumental"] = "instrumental"
        if energy is not None:
            params["speed"] = next(name for low, high, name in self.SPEED if low <= float(energy) < high)
        if min_s or max_s:
            params["durationbetween"] = f"{int(min_s or 0)}_{int(max_s or 600)}"
        own = client or httpx.Client(timeout=SEARCH_TIMEOUT)
        try:
            response = _send(lambda: own.get(url, params=params, headers=headers), sleep=sleep)
        finally:
            if client is None:
                own.close()
        try:
            rows = (response.json() or {}).get("results") or []
        except ValueError:
            raise MusicError("provider_error", "Jamendo returned an unreadable answer")
        return [self._track(row) for row in rows if row.get("id")]

    @staticmethod
    def _endpoint() -> tuple[str, dict]:
        """Direct when JAMENDO_API_BASE says so; otherwise through the relay (the server cannot reach jamendo.com), authenticated with the same shared key."""
        explicit = os.environ.get("JAMENDO_API_BASE", "").strip().rstrip("/")
        if explicit:
            return explicit + "/tracks/", {}
        from brain import elevenlabs_transport as transport
        if transport.relay_ready():
            return transport.jamendo_url(), {"xi-api-key": transport.api_key()}
        return "https://api.jamendo.com/v3.0/tracks/", {}

    @staticmethod
    def _track(row: dict) -> dict:
        info = (row.get("musicinfo") or {})
        tags = info.get("tags") or {}
        licence_url = row.get("license_ccurl") or ""
        terms = cc_terms(licence_url)
        track = {"id": f"jamendo:{row['id']}", "source": "search", "provider": "jamendo", "title": row.get("name") or "", "artist": row.get("artist_name") or "",
                 "duration_s": float(row.get("duration") or 0) or None, "preview_url": row.get("audio") or None, "download_url": row.get("audiodownload") or None,
                 "download_allowed": bool(row.get("audiodownload_allowed", bool(row.get("audiodownload")))), "page_url": row.get("shareurl"),
                 "instrumental": info.get("vocalinstrumental") == "instrumental" if info.get("vocalinstrumental") else None,
                 "tags": [*(tags.get("genres") or []), *(tags.get("instruments") or []), *(tags.get("vartags") or [])][:12], "speed": info.get("speed"),
                 "license": {"name": terms["code"] or "unknown", "url": licence_url or None, "terms": terms,
                             "attribution": f"“{row.get('name', '')}” by {row.get('artist_name', '')} (Jamendo), {licence_url}" if terms["attribution"] else None}}
        track["rights"] = rights(track)
        return track


class Epidemic:
    """Epidemic Sound Partner API (https://developers.epidemicsound.com/docs/api-reference/): bearer API key plus x-partner-user-id. Written from the published reference;
    it has not been run against the live service (it needs a partner key), so response fields are read defensively."""
    name, kind = "epidemic", "search"
    BASE = "https://api.epidemicsound.com"

    def available(self) -> tuple[bool, str]:
        return (True, "") if os.environ.get("EPIDEMIC_SOUND_API_KEY", "").strip() else (False, "EPIDEMIC_SOUND_API_KEY is not set (partner access is arranged with Epidemic Sound)")

    def _headers(self) -> dict:
        return {"authorization": f"Bearer {os.environ['EPIDEMIC_SOUND_API_KEY'].strip()}", "x-partner-user-id": os.environ.get("EPIDEMIC_PARTNER_USER_ID", "editorgpt"),
                "accept": "application/json"}

    def search(self, query: str = "", *, instrumental: bool | None = True, bpm_min: int | None = None, bpm_max: int | None = None, limit: int = 12,
               client: httpx.Client | None = None, sleep=time.sleep) -> list[dict]:
        ok, why = self.available()
        if not ok:
            raise MusicError("no_credentials", why)
        params: dict[str, Any] = {"term": query.strip()[:200], "limit": max(1, min(60, limit))}
        if instrumental is True:
            params["vocalType"] = "NONE"
        if bpm_min:
            params["bpmMin"] = int(bpm_min)
        if bpm_max:
            params["bpmMax"] = int(bpm_max)
        own = client or httpx.Client(timeout=SEARCH_TIMEOUT)
        try:
            response = _send(lambda: own.get(os.environ.get("EPIDEMIC_API_BASE", self.BASE).rstrip("/") + "/v0/tracks/search", params=params, headers=self._headers()), sleep=sleep)
        finally:
            if client is None:
                own.close()
        try:
            data = response.json() or {}
        except ValueError:
            raise MusicError("provider_error", "Epidemic Sound returned an unreadable answer")
        rows = data.get("tracks") or data.get("items") or data.get("results") or []
        out = []
        for row in rows:
            ident = row.get("id") or row.get("trackId")
            if not ident:
                continue
            artists = row.get("mainArtists") or row.get("artists") or []
            artist = ", ".join(a.get("name", "") if isinstance(a, dict) else str(a) for a in artists)
            track = {"id": f"epidemic:{ident}", "source": "search", "provider": "epidemic", "title": row.get("title") or row.get("name") or "", "artist": artist,
                     "duration_s": (row.get("length") or row.get("durationInSeconds") or 0) or None, "bpm": row.get("bpm"), "preview_only": bool(row.get("isPreviewOnly")),
                     "tags": [m.get("name", str(m)) if isinstance(m, dict) else str(m) for m in (row.get("moods") or [])][:8], "instrumental": instrumental is True or None,
                     "license": {"name": "Epidemic Sound partner licence", "url": "https://developers.epidemicsound.com/docs/overview", "attribution": None}}
            track["rights"] = rights(track)
            out.append(track)
        return out

    def download_url(self, track_id: str, client: httpx.Client | None = None, sleep=time.sleep) -> str:
        own = client or httpx.Client(timeout=SEARCH_TIMEOUT)
        try:
            response = _send(lambda: own.get(os.environ.get("EPIDEMIC_API_BASE", self.BASE).rstrip("/") + f"/v0/tracks/{track_id}/download", headers=self._headers(),
                                             params={"quality": "normal"}), sleep=sleep)
        finally:
            if client is None:
                own.close()
        link = (response.json() or {}).get("url")
        if not link:
            raise MusicError("provider_error", "Epidemic Sound returned no download link")
        return link


SEARCHERS = {"jamendo": Jamendo(), "epidemic": Epidemic()}


def providers_status() -> list[dict]:
    """What is configured, for the UI and the agent: never a key, only whether one exists."""
    rows = []
    for name, engine in {**GENERATORS, **SEARCHERS}.items():
        ok, why = engine.available()
        rows.append({"provider": name, "kind": engine.kind, "available": ok, "reason": why})
    return rows


def search(query: str = "", *, tags: list[str] | None = None, instrumental: bool | None = True, energy: float | None = None, bpm: tuple[int, int] | None = None,
           min_s: float | None = None, max_s: float | None = None, limit: int = 12, providers: tuple[str, ...] | None = None, clients: dict | None = None,
           sleep=time.sleep) -> dict:
    """Every configured search provider, merged. A provider that is down or has no key is reported in `skipped`; the others still answer."""
    found: list[dict] = []
    skipped: list[dict] = []
    for name in providers or tuple(SEARCHERS):
        engine = SEARCHERS.get(name)
        if engine is None:
            continue
        ok, why = engine.available()
        if not ok:
            skipped.append({"provider": name, "reason": why})
            continue
        try:
            client = (clients or {}).get(name)
            if name == "jamendo":
                found += engine.search(query, tags=tags, instrumental=instrumental, energy=energy, min_s=min_s, max_s=max_s, limit=limit, client=client, sleep=sleep)
            else:
                found += engine.search(query, instrumental=instrumental, bpm_min=bpm[0] if bpm else None, bpm_max=bpm[1] if bpm else None, limit=limit, client=client, sleep=sleep)
        except MusicError as exc:
            skipped.append({"provider": name, "reason": f"{exc.code}: {exc}"})
    return {"tracks": found, "skipped": skipped}


def _relay_for_jamendo() -> bool:
    from brain import elevenlabs_transport as transport
    return not os.environ.get("JAMENDO_API_BASE", "").strip() and transport.relay_ready()


def _download_direct(url: str, folder: Path) -> Path:
    from brain.music import fetch_music_url               # SSRF-guarded (public https hosts only), size-capped
    return Path(fetch_music_url(url, folder))


def _download_via_relay(url: str, folder: Path, client: httpx.Client | None) -> Path:
    """An audio file through the relay's Jamendo function (jamendo.com hosts only), streamed to disk with a size cap."""
    from brain.elevenlabs_transport import api_key, jamendo_url
    target = folder / "audio.mp3"
    own = client or httpx.Client(timeout=httpx.Timeout(120.0, connect=20.0))
    try:
        with own.stream("GET", jamendo_url(), params={"download": url}, headers={"xi-api-key": api_key()}) as response:
            if response.status_code >= 400:
                raise MusicError("provider_error", f"the relay refused the download (HTTP {response.status_code})")
            if not (response.headers.get("content-type") or "").lower().startswith("audio/"):
                raise MusicError("provider_error", "the relay did not return audio")
            size = 0
            with target.open("wb") as handle:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_AUDIO_BYTES:
                        raise MusicError("provider_error", "the track is unreasonably large")
                    handle.write(chunk)
    finally:
        if client is None:
            own.close()
    if not target.stat().st_size:
        raise MusicError("provider_error", "the downloaded track is empty")
    return target


def fetch(track: dict, *, client: httpx.Client | None = None) -> dict:
    """Make a discovered track a local file in the cache (only when its rights allow it); the SSRF-guarded fetcher of brain.music does the download."""
    ensure_rights(track)
    key = fingerprint("fetch", {"id": track["id"]})
    with single_flight(key):
        hit = cached(key)
        if hit:
            return {**track, "path": hit["path"], "cache_hit": True}
        url = track.get("download_url")
        if track.get("provider") == "epidemic":
            url = Epidemic().download_url(track["id"].split(":", 1)[1], client=client)
        if not url:
            raise MusicError("rights", "this track has no download link for the application")
        folder = store_root() / "downloads" / key
        folder.mkdir(parents=True, exist_ok=True)
        try:
            path = _download_via_relay(url, folder, client) if track.get("provider") == "jamendo" and _relay_for_jamendo() else _download_direct(url, folder)
        except MusicError:
            raise
        except Exception as exc:                              # the fetchers raise ValueError/RuntimeError with a person-readable reason
            raise MusicError("provider_error", f"the track could not be downloaded: {str(exc)[:160]}")
        saved = remember(key, Path(path), Path(path).suffix.lstrip(".") or "mp3", {"provider": track.get("provider"), "source": "search", "title": track.get("title"), "license": track.get("license")})
        record_cost({"kind": "download", "provider": track.get("provider"), "key": key, "usd": 0.0, "id": track["id"]})
        return {**track, "path": saved["path"], "cache_hit": False}
