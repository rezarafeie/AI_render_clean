"""Voice cloning: an instant voice made from the person's own recording (read aloud in the app) or from a file (audio or video, 30 s to 2 h).

The sample is prepared here (audio extracted, the clearest stretch of speech chosen, silences squeezed, loudness levelled), sent through the same HTTPS relay as all
other ElevenLabs calls to create an Instant Voice Clone, and the new voice id is kept in a small registry so narration can use it exactly like a catalogue voice
(`brain.localize.narrator_ids` includes the clones). Nothing is cloned without the person confirming the voice is theirs or used with permission.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

MIN_SECONDS = 30.0                 # the shortest usable sample
MAX_SOURCE_SECONDS = 2 * 3600 + 60         # a two hour file is accepted
SAMPLE_SECONDS = 150.0             # the part of a long file that is sent (clean speech of this length clones well; more does not help)
MAX_SAMPLE_BYTES = 3_500_000       # the relay carries the sample in one request
_LOCK = threading.Lock()


def root() -> Path:
    """Where cloned voices are registered: inside the persistent media volume (JOBS_DIR). A folder next to it lives in the container and is lost at every deploy."""
    base = os.environ.get("VOICE_CLONE_DIR")
    if base:
        return Path(base)
    from app.config import settings
    return Path(settings.JOBS_DIR).expanduser() / "_voice_clones"


def _registry() -> Path:
    return root() / "voices.json"


def _load() -> list[dict]:
    try:
        data = json.loads(_registry().read_text())
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(rows: list[dict]) -> None:
    root().mkdir(parents=True, exist_ok=True)
    temporary = _registry().with_suffix(".part")
    temporary.write_text(json.dumps(rows, ensure_ascii=False))
    temporary.replace(_registry())


def list_clones(user: str | None = None) -> list[dict]:
    """The cloned voices (of one person when `user` is given)."""
    return [row for row in _load() if user is None or str(row.get("user")) == str(user)]


def clone_ids() -> set[str]:
    return {row["id"] for row in _load() if row.get("id")}


def name_of(voice_id: str) -> str:
    return next((row.get("name", "") for row in _load() if row.get("id") == voice_id), "")


def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:40]
    return name or "صدای من"


# ── preparing the sample ────────────────────────────────────────────────────────────────────────────────────────
def probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60).stdout.strip()
    try:
        return float(out)
    except ValueError:
        raise ValueError("این فایل صدا یا ویدیوی قابل‌خواندن نیست")


def _speech_profile(path: Path) -> tuple[list[float], float]:
    """Loudness per half second of the whole file (decoded at 8 kHz, mono) and the step in seconds."""
    import numpy as np
    step = 0.5
    process = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True, timeout=1800)
    if process.returncode != 0 or not process.stdout:
        raise ValueError("از این فایل صدایی استخراج نشد")
    samples = np.frombuffer(process.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    window = int(8000 * step)
    count = len(samples) // window
    if count == 0:
        raise ValueError("فایل خیلی کوتاه است")
    frames = samples[: count * window].reshape(count, window)
    return list(np.sqrt((frames ** 2).mean(axis=1))), step


def best_window(levels: list[float], step: float, length: float) -> tuple[float, float]:
    """The stretch of `length` seconds with the most speech (frames well above the file's noise floor), preferring steady loudness over bursts of music or noise.
    Returns (start, end) in seconds."""
    import numpy as np
    values = np.asarray(levels, dtype=np.float32)
    if len(values) == 0:
        return 0.0, 0.0
    floor = float(np.percentile(values, 20))
    peak = float(np.percentile(values, 95))
    gate = max(floor * 2.0, peak * 0.12, 0.004)
    speech = (values > gate).astype(np.float32)
    span = max(1, int(length / step))
    if span >= len(values):
        return 0.0, len(values) * step
    best, where = -1.0, 0
    kernel = np.ones(span, dtype=np.float32)
    density = np.convolve(speech, kernel, mode="valid")
    # steadiness: the spread of loudness among the speech frames of the window (a lecture is steady; a music bed or shouting is not)
    for start in range(0, len(density), max(1, int(15 / step))):
        chunk = values[start:start + span]
        voiced = chunk[chunk > gate]
        steady = 1.0 / (1.0 + (float(voiced.std() / (voiced.mean() + 1e-6)) if len(voiced) > 3 else 1.0))
        score = float(density[start]) * (0.6 + 0.4 * steady)
        if score > best:
            best, where = score, start
    return where * step, min(len(values), where + span) * step


def prepare_sample(source: Path, out: Path) -> dict:
    """Make the file that is sent: mono mp3 of the clearest speech, silences squeezed, loudness levelled. Returns {"path", "seconds", "from", "source_seconds"}."""
    total = probe_seconds(source)
    if total < MIN_SECONDS:
        raise ValueError(f"نمونه خیلی کوتاه است ({total:.0f} ثانیه)؛ دست‌کم {MIN_SECONDS:.0f} ثانیه صحبت لازم است")
    if total > MAX_SOURCE_SECONDS:
        raise ValueError("فایل از ۲ ساعت بیشتر است")
    start = 0.0
    length = total
    if total > SAMPLE_SECONDS * 1.3:
        levels, step = _speech_profile(source)
        start, end = best_window(levels, step, SAMPLE_SECONDS)
        length = max(MIN_SECONDS, end - start)
    out.parent.mkdir(parents=True, exist_ok=True)
    chain = ("highpass=f=70,lowpass=f=12000,"
             "silenceremove=start_periods=1:start_threshold=-45dB:stop_periods=-1:stop_duration=0.8:stop_threshold=-45dB:stop_silence=0.35,"
             "loudnorm=I=-19:TP=-2:LRA=9")
    for bitrate in ("64k", "48k", "32k"):                    # the relay carries the sample in one request: lower the bitrate until it fits
        run = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", str(source), "-vn", "-ac", "1", "-ar", "24000",
                              "-af", chain, "-b:a", bitrate, str(out)], capture_output=True, timeout=900)
        if run.returncode != 0 or not out.is_file():
            raise ValueError("آماده‌سازی نمونهٔ صدا ناموفق بود")
        if out.stat().st_size <= MAX_SAMPLE_BYTES:
            break
    seconds = probe_seconds(out)
    if seconds < MIN_SECONDS * 0.8:
        raise ValueError(f"بعد از حذف سکوت‌ها فقط {seconds:.0f} ثانیه صحبت باقی ماند؛ نمونهٔ طولانی‌تری بدهید")
    return {"path": out, "seconds": round(seconds, 1), "from": round(start, 1), "source_seconds": round(total, 1)}


# ── ElevenLabs ──────────────────────────────────────────────────────────────────────────────────────────────────
def _create_remote(name: str, sample: Path, description: str) -> str:
    import httpx
    from brain.elevenlabs_transport import clone_url
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("کلید ElevenLabs تنظیم نشده است")
    with sample.open("rb") as handle:
        response = httpx.post(clone_url(), headers={"xi-api-key": key},
                              data={"name": name, "description": description[:400], "remove_background_noise": "true"},
                              files=[("files", (sample.name, handle, "audio/mpeg"))], timeout=httpx.Timeout(300.0, connect=20.0))
    if response.status_code == 403:
        raise RuntimeError("ElevenLabs درخواست را رد کرد (۴۰۳)؛ شبکه یا رله را بررسی کنید")
    if response.status_code in (401, 402) or "can_not_use_instant_voice_cloning" in response.text:
        raise RuntimeError("پلن ElevenLabs شما کلون صدای فوری را پشتیبانی نمی‌کند یا اعتبارش کافی نیست")
    if response.status_code == 400 and "voice_limit" in response.text:
        raise RuntimeError("سقف تعداد صداهای سفارشی در حساب ElevenLabs پر شده؛ یک صدای قدیمی را حذف کنید")
    if response.status_code >= 400:
        raise RuntimeError(f"ساخت صدا در ElevenLabs ناموفق بود (HTTP {response.status_code}): {response.text[:200]}")
    voice_id = (response.json() or {}).get("voice_id")
    if not voice_id:
        raise RuntimeError("ElevenLabs شناسهٔ صدا را برنگرداند")
    return str(voice_id)


def _delete_remote(voice_id: str) -> None:       # not used: the relay does not allow deleting voices; kept for a relay that does
    import httpx
    from brain.elevenlabs_transport import url
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    response = httpx.delete(url(f"v1/voices/{voice_id}"), headers={"xi-api-key": key}, timeout=60)
    if response.status_code not in (200, 404):
        raise RuntimeError(f"حذف صدا در ElevenLabs ناموفق بود (HTTP {response.status_code})")


def create(user: str, name: str, source: Path, kind: str) -> dict:
    """Prepare the sample, create the voice, and register it. `kind` is "recording" or "file". Raises ValueError (a problem with the sample) or RuntimeError (the provider)."""
    name = _clean_name(name)
    work = root() / "work" / uuid.uuid4().hex[:12]
    try:
        sample = prepare_sample(source, work / "sample.mp3")
        voice_id = _create_remote(name, sample["path"], f"Cloned in EditorGPT from a {kind}")
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    row = {"id": voice_id, "name": name, "user": str(user), "source": kind, "seconds": sample["seconds"], "created": time.time()}
    with _LOCK:
        rows = [r for r in _load() if r.get("id") != voice_id]
        rows.append(row)
        _save(rows)
    return row


def rename(user: str, voice_id: str, name: str) -> dict | None:
    """Give a cloned voice another name (in the app; the person's own voices only)."""
    with _LOCK:
        rows = _load()
        row = next((r for r in rows if r.get("id") == voice_id and str(r.get("user")) == str(user)), None)
        if not row:
            return None
        row["name"] = _clean_name(name)
        _save(rows)
        return row


def owns(user: str, voice_id: str) -> bool:
    return any(r.get("id") == voice_id and str(r.get("user")) == str(user) for r in _load())


def remove(user: str, voice_id: str, admin: bool = False) -> bool:
    with _LOCK:
        rows = _load()
        row = next((r for r in rows if r.get("id") == voice_id), None)
        if not row or (not admin and str(row.get("user")) != str(user)):
            return False
        _save([r for r in rows if r.get("id") != voice_id])
    return True


# ── background jobs (a long file takes a minute or two to analyse); the state lives in a file so any server process can answer the poll ────────────
def _job_file(job: str) -> Path:
    return root() / "jobs" / f"{job}.json"


def _set(job: str, **changes) -> None:
    path = _job_file(job)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {}
    state.update(changes)
    temporary = path.with_suffix(".part")
    temporary.write_text(json.dumps(state, ensure_ascii=False))
    temporary.replace(path)


def start(user: str, name: str, source: Path, kind: str) -> str:
    job = uuid.uuid4().hex[:12]
    _set(job, id=job, user=str(user), status="working", message="دارم نمونهٔ صدا را آماده می‌کنم", voice=None, error=None, at=time.time())

    def run() -> None:
        try:
            row = create(user, name, source, kind)
            _set(job, status="done", voice=row, message="صدا ساخته شد")
        except (ValueError, RuntimeError) as exc:
            _set(job, status="failed", error=str(exc)[:300], message="ساخت صدا ناموفق بود")
        except Exception as exc:                                  # never lose the reason
            log.exception("voice cloning failed")
            _set(job, status="failed", error=f"{type(exc).__name__}: {str(exc)[:200]}", message="ساخت صدا ناموفق بود")
        finally:
            try:
                source.unlink()
            except OSError:
                pass

    threading.Thread(target=run, name=f"voice-clone-{job}", daemon=True).start()
    return job


def job_state(job: str, user: str) -> dict | None:
    if not re.fullmatch(r"[a-f0-9]{12}", job or ""):
        return None
    try:
        state = json.loads(_job_file(job).read_text())
    except (OSError, ValueError):
        return None
    if state.get("user") != str(user):
        return None
    if state.get("status") == "working" and time.time() - float(state.get("at") or 0) > 3600:
        return {**{k: v for k, v in state.items() if k != "user"}, "status": "failed", "error": "ساخت صدا نیمه‌کاره ماند؛ دوباره امتحان کنید"}
    return {k: v for k, v in state.items() if k != "user"}
