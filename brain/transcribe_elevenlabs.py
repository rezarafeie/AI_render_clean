"""ElevenLabs Scribe v2 transcription engine."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger(__name__)

SCRIBE_MODEL = "scribe_v2"
SCRIBE_FALLBACK_MODEL = "scribe_v1"
# $0.40 per hour  →  per-second cost
COST_PER_SECOND = 0.40 / 3600
_CONNECT_TIMEOUT = int(os.environ.get("ELEVENLABS_SCRIBE_CONNECT_TIMEOUT", "10"))
_READ_TIMEOUT = max(200,int(os.environ.get("ELEVENLABS_SCRIBE_READ_TIMEOUT", "200")))

# Markers of errors that will fail identically on an immediate retry: an
# exhausted quota, or a rejected/forbidden key. These are surfaced right away
# so the caller can fall back to the local Whisper engine without delay.
CHUNK_SECONDS = 540          # a single request for an hour of audio outlasts the 200 s read limit and the relay's request limit: long audio goes in pieces
_PERMANENT_ERROR_MARKERS = ("quota_exceeded", "quota", "status_code: 401", "status_code: 403")


def _is_permanent_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in (401, 403):
        return True
    return any(marker in text for marker in _PERMANENT_ERROR_MARKERS)


def _normalize_persian(text: str) -> str:
    return (
        text
        .replace("ي", "ی")  # Arabic ي → Persian ی
        .replace("ى", "ی")  # Arabic alef maqsura → ی
        .replace("ك", "ک")  # Arabic ك → Persian ک
    )


def _extract_audio(video: Path, out_dir: Path) -> Path:
    # A compact mono MP3 keeps longer uploads below Vercel's request limit.
    audio = out_dir / "audio_elevenlabs.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vn", "-acodec", "libmp3lame",
         "-b:a", "32k", "-ar", "16000", "-ac", "1", str(audio)],
        capture_output=True, check=True,
    )
    return audio


def _cache_key(file_digest: str, language: Optional[str], model_id: str,
               keyterms: Optional[list[str]] = None) -> str:
    settings = {
        "engine": "elevenlabs",
        "file_hash": file_digest,
        "model_id": model_id,
        "language": language,
        "keyterms": sorted(keyterms or []),
    }
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]


def _map_response(resp, file_digest: str, key: str, language: Optional[str],
                  duration_secs: float) -> dict:
    words: list[dict] = []
    sentences: list[dict] = []
    current_sentence: list[dict] = []

    for w in (resp.words or []):
        if w.type != "word":
            continue
        cleaned = _normalize_persian(w.text.strip())
        if not cleaned:
            continue
        prob = round(math.exp(w.logprob), 3) if w.logprob is not None else 0.5
        entry = {
            "w": cleaned,
            "start": round(w.start, 3),
            "end": round(w.end, 3),
            "prob": prob,
        }
        words.append(entry)
        current_sentence.append(entry)

        ends_sentence = cleaned.endswith((".", "!", "?", "؟", "。"))
        if ends_sentence and current_sentence:
            sentences.append({
                "text": " ".join(e["w"] for e in current_sentence),
                "start": current_sentence[0]["start"],
                "end": current_sentence[-1]["end"],
            })
            current_sentence = []

    if current_sentence:
        sentences.append({
            "text": " ".join(e["w"] for e in current_sentence),
            "start": current_sentence[0]["start"],
            "end": current_sentence[-1]["end"],
        })

    return {
        "file_hash": file_digest,
        "cache_key": key,
        "engine": "elevenlabs",
        "model_id": SCRIBE_MODEL,
        "requested_language": language,
        "language": resp.language_code or language or "unknown",
        "duration": round(duration_secs, 3),
        "words": words,
        "sentences": sentences,
    }


def transcribe_elevenlabs(
    video: Path,
    out_dir: Path,
    *,
    language: Optional[str] = None,
    file_digest: str,
    keyterms: Optional[list[str]] = None,
) -> tuple[dict, float]:
    """Transcribe using ElevenLabs Scribe. Returns (transcript_dict, cost_usd).

    Raises RuntimeError on API failure (caller should fall back to Whisper).
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    key = _cache_key(file_digest, language, SCRIBE_MODEL, keyterms)

    archive = out_dir / "transcripts" / f"{key}.json"
    if archive.exists():
        cached = json.loads(archive.read_text())
        cost = None if cached.get('engine')=='lm_gateway_stt' else cached.get("duration", 0) * COST_PER_SECOND
        log.info("elevenlabs cache hit for %s (%s)", video.name, key)
        return cached, round(cost, 6) if cost is not None else None

    wav = _extract_audio(video, out_dir)
    try:
        from engine.probe import probe_duration
        total = probe_duration(wav)
    except Exception:
        total = 0.0
    if total > CHUNK_SECONDS * 1.5:
        try:
            return _transcribe_in_chunks(wav, total, out_dir, key, file_digest, language, keyterms, api_key)
        finally:
            wav.unlink(missing_ok=True)
    try:
        import httpx as _httpx
        from elevenlabs import ElevenLabs
        from brain.elevenlabs_transport import base_url

        client = ElevenLabs(
            api_key=api_key,
            base_url=base_url(),
            timeout=_httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
        )

        kwargs: dict = {
            "model_id": SCRIBE_MODEL,
            "language_code": language or "fa",
            "tag_audio_events": False,
            "diarize": False,
            "timestamps_granularity": "word",
        }
        if keyterms:
            kwargs["keyterms"] = keyterms[:1000]

        t0 = time.monotonic()
        with open(wav, "rb") as f:
            try:
                resp = client.speech_to_text.convert(file=f, request_options={'max_retries':0}, **kwargs)
            except Exception as first_err:
                # Quota/auth failures are permanent for this request; retrying
                # only burns another request cycle before the inevitable
                # fallback to Whisper. Fail fast so the fallback engine starts
                # sooner and the job does not sit in "generating plan" for
                # minutes on a request that can never succeed.
                if _is_permanent_error(first_err):
                    raise RuntimeError(
                        f"ElevenLabs API unavailable: {first_err}"
                    ) from first_err
                raise RuntimeError('ElevenLabs STT failed; no paid retry, use local Whisper') from first_err
        elapsed = time.monotonic() - t0

        duration = resp.audio_duration_secs if hasattr(resp, "audio_duration_secs") and resp.audio_duration_secs else 0.0
        cost = round(duration * COST_PER_SECOND, 6)
        if keyterms:
            cost = round(cost * 1.2, 6)

        transcript = _map_response(resp, file_digest, key, language, duration)

        log.info("elevenlabs: %d words, %.1fs audio, $%.4f, %.1fs elapsed",
                 len(transcript["words"]), duration, cost, elapsed)

        archive.parent.mkdir(exist_ok=True)
        archive.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))

        return transcript, cost

    finally:
        wav.unlink(missing_ok=True)


def _transcribe_in_chunks(wav: Path, total: float, out_dir: Path, key: str, file_digest: str, language: Optional[str],
                          keyterms: Optional[list[str]], api_key: str) -> tuple[dict, float]:
    """Scribe on consecutive pieces of the audio, their word times moved to the whole recording's clock. Any piece that fails fails the whole attempt
    (the caller then tries the next provider): a transcript with a hole in it would cut and caption the wrong places."""
    import httpx as _httpx
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from elevenlabs import ElevenLabs
    from brain.elevenlabs_transport import base_url

    pieces = [(i, start) for i, start in enumerate(range(0, int(total) + 1, CHUNK_SECONDS)) if start < total]
    folder = out_dir / "asr_chunks"
    folder.mkdir(exist_ok=True)
    kwargs: dict = {"model_id": SCRIBE_MODEL, "language_code": language or "fa", "tag_audio_events": False, "diarize": False, "timestamps_granularity": "word"}
    if keyterms:
        kwargs["keyterms"] = keyterms[:1000]

    def one(piece: tuple[int, int]):
        index, start = piece
        part = folder / f"part{index:03d}.mp3"
        try:
            subprocess.run(["ffmpeg", "-y", "-ss", str(start), "-t", str(CHUNK_SECONDS), "-i", str(wav), "-c", "copy", str(part)],
                           capture_output=True, check=True, timeout=300)
            client = ElevenLabs(api_key=api_key, base_url=base_url(), timeout=_httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT))
            with open(part, "rb") as handle:
                try:
                    resp = client.speech_to_text.convert(file=handle, request_options={'max_retries': 0}, **kwargs)
                except Exception as err:
                    raise RuntimeError(f"ElevenLabs STT failed on part {index + 1} of {len(pieces)}") from err
            return start, resp
        finally:
            part.unlink(missing_ok=True)

    log.info("elevenlabs: %.0f s of audio in %d pieces", total, len(pieces))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(one, pieces))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    words = []
    language_code = None
    for start, resp in results:
        language_code = language_code or getattr(resp, "language_code", None)
        for w in (resp.words or []):
            words.append(SimpleNamespace(type=w.type, text=w.text, logprob=getattr(w, "logprob", None), start=w.start + start, end=w.end + start))
    transcript = _map_response(SimpleNamespace(words=words, language_code=language_code), file_digest, key, language, total)
    cost = round(total * COST_PER_SECOND * (1.2 if keyterms else 1), 6)
    archive = out_dir / "transcripts" / f"{key}.json"
    archive.parent.mkdir(exist_ok=True)
    archive.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))
    return transcript, cost


def transcribe_gateway(video, out_dir, *, provider, language, file_digest):
    """One provider-pinned gateway STT attempt; no guessed model IDs."""
    from brain import lm_gateway
    from types import SimpleNamespace
    wav=_extract_audio(video,out_dir)
    try:
        data=lm_gateway.transcription(wav,language,provider=provider)
        entries=[SimpleNamespace(type='word',text=w.get('text',w.get('word','')),
            start=w['start'],end=w['end'],logprob=None) for w in data.get('words',[]) if 'start' in w and 'end' in w]
        if not entries:raise RuntimeError('STT returned no word timestamps')
        duration=float(data.get('duration') or entries[-1].end)
        key=_cache_key(file_digest,language,str(data.get('model','')))
        transcript=_map_response(SimpleNamespace(words=entries,language_code=data.get('language',language)),file_digest,key,language,duration)
        transcript.update(engine='elevenlabs_'+provider,model_id=data.get('model',''))
        archive=out_dir/'transcripts'/f'{key}.json';archive.parent.mkdir(exist_ok=True)
        archive.write_text(json.dumps(transcript,ensure_ascii=False))
        return transcript,None
    finally:wav.unlink(missing_ok=True)
