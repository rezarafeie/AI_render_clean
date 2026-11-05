"""Chunked, resumable local transcription for long videos (faster-whisper, CPU friendly).

The audio is extracted once, split at real pauses (never mid-word), and each chunk is transcribed and written to disk on its
own. A crash or restart resumes from the first missing chunk; finished chunks are never transcribed again. Segments are
published as soon as a chunk produces them (``on_segments``), so a UI can show real text while later chunks still run.

Layout under ``work``:  audio.wav, plan.json, chunks/0000.json …, raw.json (merged, versioned by the settings that made it).
Speaker diarization is not available without an extra model; ``speaker`` stays None rather than being guessed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
TARGET_CHUNK_S = 300.0
SNAP_WINDOW_S = 25.0            # a chunk edge may move this far to land inside a pause
MIN_PAUSE_S = 0.35
_MODEL_LOCK = threading.Lock()
_MODELS: dict[tuple, object] = {}
_RUN_LOCK = threading.Semaphore(int(os.environ.get("LONGVIDEO_TRANSCRIBE_CONCURRENCY", "1")))   # one at a time: CPU and RAM are shared
_SILENCE = re.compile(r"silence_(start|end): (-?[0-9.]+)")
# measured seconds of CPU time per second of audio (int8): used for the first estimate, then replaced by what this machine really does
DEFAULT_RTF = {"tiny": 0.08, "base": 0.15, "small": 0.35, "medium": 0.9}


class Stopped(RuntimeError):
    """The caller asked the run to stop (cancellation)."""


def cpu_threads() -> int:
    """Whisper uses half the cores by default: the web app and the renders share this machine. ``LONGVIDEO_CPU_THREADS`` overrides."""
    forced = os.environ.get("LONGVIDEO_CPU_THREADS", "").strip()
    if forced.isdigit() and int(forced) > 0:
        return int(forced)
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def _lower_priority() -> None:
    """Make this worker thread yield to the API and the renders (Linux per-thread nice; ignored elsewhere)."""
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
    except (AttributeError, OSError):
        pass


def choose_model(duration_s: float, cpu_count: Optional[int] = None) -> str:
    """The model that fits this machine and this video. ``LONGVIDEO_WHISPER_MODEL`` overrides everything."""
    forced = os.environ.get("LONGVIDEO_WHISPER_MODEL", "").strip()
    if forced:
        return forced
    cpus = cpu_count or os.cpu_count() or 2
    if cpus >= 4 and duration_s <= 5400:
        return "small"                         # Persian needs at least "small"; "base" misspells too much
    return "base"


def extract_audio(video: Path, wav_path: Path) -> float:
    """16 kHz mono PCM, written once. Returns the duration in seconds."""
    if not wav_path.is_file() or wav_path.stat().st_size < 1000:
        temporary = wav_path.with_suffix(".part.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(temporary)],
                       check=True, capture_output=True, timeout=3600)
        temporary.replace(wav_path)
    with wave.open(str(wav_path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def detect_silences(wav_path: Path, noise_db: int = -35, min_s: float = MIN_PAUSE_S) -> list[tuple[float, float]]:
    """(start, end) of every pause in the audio."""
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav_path), "-af", f"silencedetect=noise={noise_db}dB:d={min_s}",
                             "-f", "null", "-"], capture_output=True, text=True, timeout=1800)
    silences, start = [], None
    for kind, value in _SILENCE.findall(result.stderr):
        if kind == "start":
            start = max(0.0, float(value))
        elif start is not None:
            silences.append((start, float(value)))
            start = None
    return silences


def plan_chunks(duration_s: float, silences: list[tuple[float, float]], target: float = TARGET_CHUNK_S, window: float = SNAP_WINDOW_S) -> list[tuple[float, float]]:
    """Chunk boundaries of about ``target`` seconds, each moved into the longest pause within ``window`` seconds, so no chunk starts
    or ends in the middle of a word."""
    bounds, cursor = [0.0], 0.0
    while duration_s - cursor > target * 1.4:
        goal = cursor + target
        near = [(e - s, (s + e) / 2) for s, e in silences if goal - window <= (s + e) / 2 <= goal + window and (s + e) / 2 > cursor + target / 2]
        cursor = max(near)[1] if near else goal
        bounds.append(round(cursor, 3))
    bounds.append(round(duration_s, 3))
    return list(zip(bounds, bounds[1:]))


def _model(name: str, device: str, compute: str):
    with _MODEL_LOCK:
        key = (name, device, compute)
        if key not in _MODELS:
            from faster_whisper import WhisperModel
            root = Path(os.environ.get("WHISPER_LOCAL_MODELS_DIR", "/root/.cache/editor-whisper")) / name
            threads = cpu_threads()
            if (root / "model.bin").is_file():
                _MODELS[key] = WhisperModel(str(root), device=device, compute_type=compute, cpu_threads=threads)
            else:
                try:                                   # a cached model must not wait on the network (the hub can be unreachable)
                    _MODELS[key] = WhisperModel(name, device=device, compute_type=compute, cpu_threads=threads, local_files_only=True)
                except Exception:
                    _MODELS[key] = WhisperModel(name, device=device, compute_type=compute, cpu_threads=threads)
        return _MODELS[key]


def settings_signature(model: str, language: Optional[str], compute: str) -> str:
    return hashlib.sha256(json.dumps({"model": model, "language": language, "compute": compute, "vad": True, "words": True, "v": 2}, sort_keys=True).encode()).hexdigest()[:12]


def _read_wave(path: Path, start: float, end: float):
    import numpy as np
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        handle.setpos(int(start * rate))
        raw = handle.readframes(int((end - start) * rate))
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0


def _normalize(text: str) -> str:
    return text.replace("ي", "ی").replace("ك", "ک").replace("ى", "ی")


def transcribe_chunk(wav_path: Path, index: int, span: tuple[float, float], *, model_name: str, language: Optional[str], device: str, compute: str,
                     beam_size: int, model=None, on_segment: Optional[Callable[[dict], None]] = None, should_stop: Optional[Callable[[], bool]] = None) -> dict:
    """Transcribe one chunk; times are absolute (offset by the chunk start). ``model`` is injectable for tests."""
    model = model or _model(model_name, device, compute)
    audio = _read_wave(wav_path, *span)
    started = time.monotonic()
    segments, info = model.transcribe(audio, language=language, vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
                                      word_timestamps=True, beam_size=beam_size, condition_on_previous_text=False)
    out = []
    for position, seg in enumerate(segments):
        if should_stop and should_stop():                  # Stop is honoured between segments, not only between 5-minute pieces (one piece can take most of an hour on a busy server)
            raise Stopped("transcription stopped")
        words = [{"w": _normalize(w.word.strip()), "start": round(span[0] + w.start, 3), "end": round(span[0] + w.end, 3), "prob": round(float(w.probability), 3)}
                 for w in (seg.words or []) if w.word.strip()]
        if not words:
            continue
        item = {"id": f"{index:04d}-{position:03d}", "start": words[0]["start"], "end": words[-1]["end"], "text": _normalize(seg.text.strip()),
                "words": words, "confidence": round(float(max(0.0, min(1.0, 1 + (seg.avg_logprob or -1) / 2))), 3),
                "no_speech": round(float(seg.no_speech_prob or 0), 3), "language": info.language, "speaker": None}
        out.append(item)
        if on_segment:
            on_segment(item)
    return {"index": index, "span": list(span), "language": info.language, "language_probability": round(float(info.language_probability or 0), 3),
            "segments": out, "elapsed_s": round(time.monotonic() - started, 2), "audio_s": round(span[1] - span[0], 2)}


def transcribe_long(video: Path, work: Path, *, language: Optional[str] = None, model_name: Optional[str] = None, device: str = "cpu",
                    compute: str = "int8", beam_size: int = 1, on_event: Optional[Callable[[str, dict], None]] = None,
                    should_stop: Optional[Callable[[], bool]] = None, model=None) -> dict:
    """Run (or resume) the whole transcription. Returns the merged raw transcript. Events: transcription.started,
    transcription.chunk.started, transcription.segment.completed (batches), transcription.chunk.completed, transcription.progress,
    transcription.completed."""
    emit = on_event or (lambda kind, data: None)
    work.mkdir(parents=True, exist_ok=True)
    (work / "chunks").mkdir(exist_ok=True)
    duration = extract_audio(video, work / "audio.wav")
    if duration < 1:
        raise RuntimeError("no audio in the video")
    name = model_name or choose_model(duration)
    signature = settings_signature(name, language, compute)
    plan_path = work / "plan.json"
    plan = json.loads(plan_path.read_text()) if plan_path.is_file() else None
    if not plan or plan.get("signature") != signature or abs(plan.get("duration", 0) - duration) > 0.5:
        silences = detect_silences(work / "audio.wav")
        plan = {"signature": signature, "duration": round(duration, 3), "model": name, "chunks": plan_chunks(duration, silences), "created_at": time.time()}
        for old in (work / "chunks").glob("*.json"):      # a different model/language invalidates earlier chunks
            old.unlink()
        plan_path.write_text(json.dumps(plan))
    chunks = [tuple(c) for c in plan["chunks"]]
    done_audio = 0.0
    language_hint = language
    emit("transcription.started", {"duration_s": duration, "chunks": len(chunks), "model": name, "resumed": any((work / "chunks" / f"{i:04d}.json").is_file() for i in range(len(chunks)))})
    with _RUN_LOCK:
        _lower_priority()
        for index, span in enumerate(chunks):
            if should_stop and should_stop():
                raise Stopped("transcription stopped")
            path = work / "chunks" / f"{index:04d}.json"
            if path.is_file():
                saved = json.loads(path.read_text())
                if saved.get("signature") == signature:
                    done_audio += span[1] - span[0]
                    language_hint = language_hint or (saved["language"] if saved.get("language_probability", 0) >= 0.8 else None)
                    emit("transcription.chunk.completed", {"index": index, "chunks": len(chunks), "cached": True, "segments": len(saved["segments"]),
                                                           "processed_s": done_audio, "language": saved.get("language")})
                    continue
            emit("transcription.chunk.started", {"index": index, "chunks": len(chunks), "start": span[0], "end": span[1]})
            batch: list[dict] = []
            last_flush = time.monotonic()

            def flush(force=False):
                nonlocal batch, last_flush
                if batch and (force or len(batch) >= 3 or time.monotonic() - last_flush > 4):
                    emit("transcription.segment.completed", {"segments": [{"id": s["id"], "start": s["start"], "end": s["end"], "text": s["text"]} for s in batch]})
                    batch, last_flush = [], time.monotonic()

            def collect(segment):
                batch.append(segment)
                flush()

            result = transcribe_chunk(work / "audio.wav", index, span, model_name=name, language=language_hint, device=device, compute=compute,
                                      beam_size=beam_size, model=model, on_segment=collect, should_stop=should_stop)
            flush(True)
            result["signature"] = signature
            temporary = path.with_suffix(".part")
            temporary.write_text(json.dumps(result, ensure_ascii=False))
            temporary.replace(path)
            done_audio += span[1] - span[0]
            language_hint = language_hint or (result["language"] if result["language_probability"] >= 0.8 else None)
            rtf = result["elapsed_s"] / max(1.0, result["audio_s"])
            emit("transcription.chunk.completed", {"index": index, "chunks": len(chunks), "cached": False, "segments": len(result["segments"]), "processed_s": done_audio,
                                                   "language": result["language"], "rtf": round(rtf, 3)})
            remaining = max(0.0, duration - done_audio)
            emit("transcription.progress", {"processed_s": round(done_audio, 1), "duration_s": round(duration, 1), "percent": round(100 * done_audio / duration, 1),
                                            "eta_s": round(remaining * rtf), "language": result["language"], "stage": "گوش دادن و تبدیل گفتار به متن"})
    raw = merge_chunks(work, chunks, signature, duration, name)
    emit("transcription.completed", {"segments": len(raw["segments"]), "language": raw["language"], "duration_s": duration})
    return raw


def merge_chunks(work: Path, chunks: list, signature: str, duration: float, model_name: str) -> dict:
    segments, languages = [], {}
    for index in range(len(chunks)):
        saved = json.loads((work / "chunks" / f"{index:04d}.json").read_text())
        segments.extend(saved["segments"])
        for seg in saved["segments"]:
            languages[seg["language"]] = languages.get(seg["language"], 0) + (seg["end"] - seg["start"])
    segments.sort(key=lambda s: s["start"])
    raw = {"version": signature, "engine": "faster-whisper", "model": model_name, "duration": round(duration, 3), "segments": segments,
           "language": max(languages, key=languages.get) if languages else "unknown", "languages": {k: round(v, 1) for k, v in languages.items()},
           "word_count": sum(len(s["words"]) for s in segments)}
    temporary = work / "raw.json.part"
    temporary.write_text(json.dumps(raw, ensure_ascii=False))
    temporary.replace(work / "raw.json")
    return raw


def estimate_seconds(duration_s: float, model_name: str, measured_rtf: Optional[float] = None) -> float:
    return duration_s * (measured_rtf or DEFAULT_RTF.get(model_name, 0.35))
